"""Business layer: StatsBomb JSON  ->  relational tables.

Decisions (documented in the report / README):
  * Only player-attributed events are modelled (events without `player`,
    e.g. Starting XI, Half Start, are skipped).
  * Players/teams come from the match list and lineup files; any player seen
    only in events (rare) is added so foreign keys stay valid.
  * Outcome = <event>.outcome.name; a Pass with no outcome is a completed
    pass in StatsBomb, stored as 'Complete'.
  * pass.recipient.id   -> MatchEvent.IntendedForPlayerId  (an *intended*
    target, not a guaranteed receipt)
  * pass.assisted_shot_id -> MatchEvent.AssistedShotEventId. Links are stored
    only if the shot is in the loaded data; missing links stay NULL
    (never inferred from proximity).
"""
import json
import sqlite3
from pathlib import Path

from src.cmn.config import DATA_RAW


def _load(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _key(type_name: str) -> str:
    """StatsBomb event type -> name of its detail object ('Goal Keeper' -> 'goalkeeper')."""
    k = type_name.lower().replace("*", "").replace("/", "_").replace(" ", "_")
    return "goalkeeper" if k == "goal_keeper" else k


def event_outcome(ev: dict) -> str | None:
    detail = ev.get(_key(ev["type"]["name"]), {})
    outcome = (detail.get("outcome") or {}).get("name") if isinstance(detail, dict) else None
    if outcome is None and ev["type"]["name"] == "Pass":
        return "Complete"
    return outcome


def load_all(conn: sqlite3.Connection, raw_dir: Path = DATA_RAW) -> dict:
    """Populate an (empty, schema-created) database. Returns row counts."""
    matches = _load(raw_dir / "matches" / "281.json")
    stats = {"warnings": []}
    cur = conn.cursor()
    conn.execute("BEGIN")

    team_pk, player_pk, match_pk, event_pk = {}, {}, {}, {}   # Sb id -> Id

    def get_team(sb_id, name):
        if sb_id not in team_pk:
            cur.execute("INSERT INTO Team(SbTeamId, Name) VALUES (?, ?)", (sb_id, name))
            team_pk[sb_id] = cur.lastrowid
        return team_pk[sb_id]

    def get_player(sb_id, name):
        if sb_id not in player_pk:
            cur.execute("INSERT INTO Player(SbPlayerId, Name) VALUES (?, ?)", (sb_id, name))
            player_pk[sb_id] = cur.lastrowid
        return player_pk[sb_id]

    # --- Match, Team, MatchTeam ------------------------------------------------
    for m in sorted(matches, key=lambda x: x["match_date"]):
        cur.execute("INSERT INTO Match(SbMatchId, MatchDate) VALUES (?, ?)",
                    (m["match_id"], m["match_date"]))
        mid = match_pk[m["match_id"]] = cur.lastrowid
        for side, label in (("home", "Home"), ("away", "Away")):
            tid = get_team(m[f"{side}_team"][f"{side}_team_id"], m[f"{side}_team"][f"{side}_team_name"])
            cur.execute("INSERT INTO MatchTeam(MatchId, TeamId, HomeOrAway) VALUES (?, ?, ?)",
                        (mid, tid, label))

    # --- AppearsFor (lineups) --------------------------------------------------
    appeared = set()
    for sb_match, mid in match_pk.items():
        for side in _load(raw_dir / "lineups" / f"{sb_match}.json"):
            tid = team_pk[side["team_id"]]
            for p in side["lineup"]:
                pid = get_player(p["player_id"], p["player_name"])
                cur.execute("INSERT INTO AppearsFor(MatchId, TeamId, PlayerId) VALUES (?, ?, ?)",
                            (mid, tid, pid))
                appeared.add((mid, pid))

    # --- MatchEvent (pass 1: all player events) --------------------------------
    pending_links = []   # (event row id, assisted shot uuid)
    skipped = 0
    for sb_match, mid in match_pk.items():
        for ev in _load(raw_dir / "events" / f"{sb_match}.json"):
            if "player" not in ev:
                skipped += 1
                continue
            pid = get_player(ev["player"]["id"], ev["player"]["name"])
            if (mid, pid) not in appeared:      # player missing from lineup file
                tid = team_pk[ev["team"]["id"]]
                cur.execute("INSERT INTO AppearsFor(MatchId, TeamId, PlayerId) VALUES (?, ?, ?)",
                            (mid, tid, pid))
                appeared.add((mid, pid))
                stats["warnings"].append(f"{ev['player']['name']} not in lineup of {sb_match}; added")
            intended = None
            p = ev.get("pass") or {}
            if p.get("recipient"):
                intended = get_player(p["recipient"]["id"], p["recipient"]["name"])
            cur.execute(
                """INSERT INTO MatchEvent(SbEventUuid, MatchId, PlayerId, EventType, Period,
                                          Minute, Second, Outcome, IntendedForPlayerId)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ev["id"], mid, pid, ev["type"]["name"], ev["period"], ev["minute"],
                 ev["second"], event_outcome(ev), intended))
            event_pk[ev["id"]] = cur.lastrowid
            if p.get("assisted_shot_id"):
                pending_links.append((cur.lastrowid, p["assisted_shot_id"]))

    # --- MatchEvent (pass 2: pass -> assisted shot links) ------------------------
    linked = 0
    for row_id, shot_uuid in pending_links:
        shot_id = event_pk.get(shot_uuid)
        if shot_id is None:
            stats["warnings"].append(f"assisted shot {shot_uuid} not found; link left NULL")
            continue
        cur.execute("UPDATE MatchEvent SET AssistedShotEventId = ? WHERE Id = ?", (shot_id, row_id))
        linked += 1

    conn.commit()
    stats.update(skipped_events_without_player=skipped, assist_links=linked)
    for t in ("Team", "Player", "Match", "MatchTeam", "AppearsFor", "MatchEvent"):
        stats[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return stats
