"""Business layer: StatsBomb JSON  ->  RDF individuals (ABox), written as RDF/XML.

Same mapping decisions as the relational ETL (src/biz/etl.py), so both databases
describe the same facts:
  * only player-attributed events; a Pass with no outcome is stored as 'Complete'
  * pass.recipient        -> lev:intendedFor  (intended target, not a receipt)
  * pass.assisted_shot_id -> lev:assists      (only if the shot is in the data, never inferred)
  * individual IRIs come from the source keys, so a rebuild gives the same IRIs:
      lev:team_<id>, lev:player_<id>, lev:match_<id>, lev:event_<uuid>, lev:appearance_<match>_<player>
  * lev:Goal is the defined class "Shot with outcome Goal". Virtuoso does not run an OWL
    reasoner by default, so the ETL materialises that inference (adds rdf:type lev:Goal).

Scopes
  sample (default, committed to the repo): every team, player, match and appearance,
      every Shot, every Pass that assists a shot, and every event of the showcase match
      (SHOWCASE_SB_MATCH_ID). Season-level goal / assist queries are therefore complete.
  full: all 137k events (about 1.2M triples, written to data/preprocessed/).
"""
import json
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from src.biz.etl import event_outcome
from src.biz.kg_ontology import event_class_name
from src.cmn.config import DATA_RAW, KG_FULL_PATH, KG_SAMPLE_PATH, NS, SEASON_ID, SHOWCASE_SB_MATCH_ID

LEV = Namespace(NS)


def iri(kind: str, key) -> "URIRef":
    return LEV[f"{kind}_{key}"]


def _load(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_kg(full: bool = False, raw_dir: Path = DATA_RAW) -> tuple[Graph, dict]:
    g = Graph()
    g.bind("lev", LEV)
    stats = {"warnings": []}
    add = g.add
    teams, players, appeared = set(), set(), set()

    def team(sb_id, name):
        t = iri("team", sb_id)
        if sb_id not in teams:
            teams.add(sb_id)
            add((t, RDF.type, LEV.Team)); add((t, LEV.sbTeamId, Literal(sb_id)))
            add((t, LEV.name, Literal(name)))
        return t

    def player(sb_id, name):
        p = iri("player", sb_id)
        if sb_id not in players:
            players.add(sb_id)
            add((p, RDF.type, LEV.Player)); add((p, LEV.sbPlayerId, Literal(sb_id)))
            add((p, LEV.name, Literal(name)))
        return p

    def appearance(sb_match, sb_team, sb_player):
        a = iri("appearance", f"{sb_match}_{sb_player}")
        if (sb_match, sb_player) not in appeared:
            appeared.add((sb_match, sb_player))
            add((a, RDF.type, LEV.Appearance)); add((a, LEV.appearanceIn, iri("match", sb_match)))
            add((a, LEV.appearanceFor, iri("team", sb_team))); add((a, LEV.appearanceOf, iri("player", sb_player)))
        return a

    # --- Match, Team, plays in (homeTeam / awayTeam) ------------------------------------
    matches = _load(raw_dir / "matches" / f"{SEASON_ID}.json")
    for m in matches:
        mi = iri("match", m["match_id"])
        add((mi, RDF.type, LEV.Match)); add((mi, LEV.sbMatchId, Literal(m["match_id"])))
        add((mi, LEV.kickOff, Literal(f"{m['match_date']}T{m['kick_off'][:8]}", datatype=XSD.dateTime)))
        for side in ("home", "away"):
            t = team(m[f"{side}_team"][f"{side}_team_id"], m[f"{side}_team"][f"{side}_team_name"])
            add((mi, LEV[f"{side}Team"], t)); add((mi, LEV.hasTeam, t))   # hasTeam materialised (sub-property)

    # --- Appearance (lineups) -------------------------------------------------------------
    for m in matches:
        for side in _load(raw_dir / "lineups" / f"{m['match_id']}.json"):
            for p in side["lineup"]:
                player(p["player_id"], p["player_name"])
                appearance(m["match_id"], side["team_id"], p["player_id"])

    # --- MatchEvent ------------------------------------------------------------------------
    n_events, n_links = 0, 0
    for m in matches:
        sb_match = m["match_id"]
        events = [e for e in _load(raw_dir / "events" / f"{sb_match}.json") if "player" in e]
        shot_ids = {e["id"] for e in events if e["type"]["name"] == "Shot"}
        for ev in events:
            p = ev.get("pass") or {}
            t = ev["type"]["name"]
            keep = (full or sb_match == SHOWCASE_SB_MATCH_ID or t == "Shot"
                    or (t == "Pass" and p.get("assisted_shot_id")))
            if not keep:
                continue
            pl = player(ev["player"]["id"], ev["player"]["name"])
            if (sb_match, ev["player"]["id"]) not in appeared:
                appearance(sb_match, ev["team"]["id"], ev["player"]["id"])
                stats["warnings"].append(f"{ev['player']['name']} not in lineup of {sb_match}; added")
            e = iri("event", ev["id"])
            cls = LEV[event_class_name(t)]
            add((e, RDF.type, cls))
            add((e, LEV.sbEventUuid, Literal(ev["id"])))
            add((e, LEV.inMatch, iri("match", sb_match)))
            add((e, LEV.performedBy, pl))
            add((e, LEV.period, Literal(ev["period"])))
            add((e, LEV.minute, Literal(ev["minute"])))   # xsd:integer, value within the range xsd:nonNegativeInteger
            add((e, LEV.second, Literal(ev["second"])))
            out = event_outcome(ev)
            if out is not None:
                add((e, LEV.outcome, Literal(out)))
                if t == "Shot" and out == "Goal":
                    add((e, RDF.type, LEV.Goal))
            if p.get("recipient"):
                add((e, LEV.intendedFor, player(p["recipient"]["id"], p["recipient"]["name"])))
            if p.get("assisted_shot_id"):
                if p["assisted_shot_id"] in shot_ids:
                    add((e, LEV.assists, iri("event", p["assisted_shot_id"])))
                    n_links += 1
                else:
                    stats["warnings"].append(f"assisted shot {p['assisted_shot_id']} not found; not linked")
            n_events += 1

    stats.update(Team=len(teams), Player=len(players), Match=len(matches), Appearance=len(appeared),
                 MatchEvent=n_events, assists=n_links, triples=len(g))
    return g, stats


def write_kg(full: bool = False) -> tuple[Path, dict]:
    g, stats = build_kg(full)
    path = KG_FULL_PATH if full else KG_SAMPLE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    # plain "xml" (not pretty-xml): streams fast for 1M+ triples and is valid RDF/XML
    g.serialize(destination=str(path), format="xml")
    return path, stats
