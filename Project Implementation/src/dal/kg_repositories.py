"""Data layer: every SPARQL statement used by the knowledge-graph web UI.

Functions take a store (src/dal/kg_store.py) and return lists of dicts. Values from
users never reach a statement unescaped: strings go through lit(), numbers through
int(), and individual IRIs are built only from validated keys (see kg_services).
Individuals are addressed by their source keys:
    match   lev:match_<sbMatchId>     player  lev:player_<sbPlayerId>
    team    lev:team_<sbTeamId>       event   lev:event_<sbEventUuid>
"""
import re

from src.cmn.config import GRAPH_IRI, NS

P = f"PREFIX lev: <{NS}>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n" \
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
G = f"<{GRAPH_IRI}>"
OWN_TEAM = "Bayer Leverkusen"
_SAFE_KEY = re.compile(r"^[A-Za-z0-9-]+$")


def lit(s: str) -> str:
    """A string as a SPARQL literal (escapes \\ " and line breaks)."""
    return '"' + (str(s).replace("\\", "\\\\").replace('"', '\\"')
                  .replace("\n", "\\n").replace("\r", "\\r")) + '"'


def ind(kind: str, key) -> str:
    """IRI of an individual from its key; rejects anything that is not a plain id."""
    key = str(key)
    if not _SAFE_KEY.match(key):
        raise ValueError(f"invalid key {key!r}")
    return f"lev:{kind}_{key}"


def _rows(store, sparql):
    cols, rows = store.select(P + sparql)
    return [dict(zip(cols, r)) for r in rows]


def _local(iri):
    return str(iri).split("#")[-1] if iri else iri


# ------------------------------------------------------------------ dashboard
def counts(store):
    rows = _rows(store, f"""
        SELECT ?class (COUNT(?x) AS ?n) WHERE {{ GRAPH {G} {{
          VALUES ?class {{ lev:Team lev:Player lev:Match lev:Appearance lev:Pass lev:Shot lev:Goal }}
          ?x a ?class }} }} GROUP BY ?class""")
    by = {_local(r["class"]): r["n"] for r in rows}
    ev = _rows(store, f"""SELECT (COUNT(?e) AS ?n) WHERE {{ GRAPH {G} {{
                         ?e lev:inMatch ?m }} }}""")[0]["n"]
    tr = _rows(store, f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH {G} {{ ?s ?p ?o }} }}")[0]["n"]
    order = ["Team", "Player", "Match", "Appearance"]
    out = {k: by.get(k, 0) for k in order}
    out.update({"MatchEvent": ev, "Shot": by.get("Shot", 0), "Goal": by.get("Goal", 0), "triples": tr})
    return out


# ------------------------------------------------------------------ matches / teams
def list_matches(store):
    return _rows(store, f"""
        SELECT ?sbMatchId ?kickOff ?opponent ?venue WHERE {{ GRAPH {G} {{
          ?own lev:name {lit(OWN_TEAM)} .
          ?m lev:sbMatchId ?sbMatchId ; lev:kickOff ?kickOff ; lev:hasTeam ?opp .
          FILTER(?opp != ?own) ?opp lev:name ?opponent .
          {{ ?m lev:homeTeam ?own BIND("Home" AS ?venue) }} UNION {{ ?m lev:awayTeam ?own BIND("Away" AS ?venue) }}
        }} }} ORDER BY ?kickOff""")


def match_teams(store, sb_match):
    return _rows(store, f"""
        SELECT ?sbTeamId ?name ?side WHERE {{ GRAPH {G} {{
          {{ {ind('match', sb_match)} lev:homeTeam ?t BIND("Home" AS ?side) }}
          UNION {{ {ind('match', sb_match)} lev:awayTeam ?t BIND("Away" AS ?side) }}
          ?t lev:sbTeamId ?sbTeamId ; lev:name ?name }} }} ORDER BY ?side""")


def players_in_match(store, sb_match):
    return _rows(store, f"""
        SELECT ?sbPlayerId ?name ?team WHERE {{ GRAPH {G} {{
          ?a lev:appearanceIn {ind('match', sb_match)} ; lev:appearanceOf ?p ; lev:appearanceFor/lev:name ?team .
          ?p lev:sbPlayerId ?sbPlayerId ; lev:name ?name }} }} ORDER BY ?team ?name""")


def event_classes(store):
    """Event classes from the TBox (rdfs:subClassOf lev:MatchEvent); Goal is derived, not offered."""
    return [r["c"].split("#")[-1] for r in _rows(store, f"""
        SELECT ?c WHERE {{ GRAPH {G} {{ ?c rdfs:subClassOf lev:MatchEvent }} }} ORDER BY ?c""")]


# ------------------------------------------------------------------ players
def search_players(store, q="", limit=200):
    flt = f"FILTER(CONTAINS(LCASE(?name), LCASE({lit(q)})))" if q else ""
    return _rows(store, f"""
        SELECT ?sbPlayerId ?name (COALESCE(?na, 0) AS ?appearances) (COALESCE(?ne, 0) AS ?events)
        WHERE {{ GRAPH {G} {{
          ?p a lev:Player ; lev:sbPlayerId ?sbPlayerId ; lev:name ?name . {flt}
          OPTIONAL {{ SELECT ?p (COUNT(?a) AS ?na) WHERE {{ ?a lev:appearanceOf ?p }} GROUP BY ?p }}
          OPTIONAL {{ SELECT ?p (COUNT(?e) AS ?ne) WHERE {{ ?e lev:performedBy ?p }} GROUP BY ?p }} }} }}
        ORDER BY ?name LIMIT {int(limit)}""")


def get_player(store, sb_player):
    r = _rows(store, f"""SELECT ?name ?sbPlayerId WHERE {{ GRAPH {G} {{
        {ind('player', sb_player)} lev:name ?name ; lev:sbPlayerId ?sbPlayerId }} }}""")
    return r[0] if r else None


def find_player_by_name(store, name):
    r = _rows(store, f"""SELECT ?sbPlayerId WHERE {{ GRAPH {G} {{
        ?p a lev:Player ; lev:sbPlayerId ?sbPlayerId ; lev:name ?n .
        FILTER(LCASE(?n) = LCASE({lit(name)})) }} }} LIMIT 1""")
    return r[0]["sbPlayerId"] if r else None


def player_exists(store, sb_player):
    return store.ask(P + f"ASK {{ GRAPH {G} {{ ?p lev:sbPlayerId {int(sb_player)} }} }}")


def has_appearance(store, sb_match, sb_player):
    return store.ask(P + f"""ASK {{ GRAPH {G} {{ ?a lev:appearanceIn {ind('match', sb_match)} ;
                                                 lev:appearanceOf {ind('player', sb_player)} }} }}""")


def next_manual_player_id(store):
    r = _rows(store, f"SELECT (MAX(?id) AS ?mx) WHERE {{ GRAPH {G} {{ ?p lev:sbPlayerId ?id }} }}")
    return max(r[0]["mx"] or 0, 8999999) + 1


def player_references(store, sb_player):
    r = _rows(store, f"""SELECT (COUNT(?e) AS ?n) WHERE {{ GRAPH {G} {{
        {{ ?e lev:performedBy {ind('player', sb_player)} }} UNION {{ ?e lev:intendedFor {ind('player', sb_player)} }} }} }}""")
    return r[0]["n"]


def insert_player(store, sb_player, name):
    store.update(P + f"""INSERT DATA {{ GRAPH {G} {{
        {ind('player', sb_player)} a lev:Player ; lev:sbPlayerId {int(sb_player)} ; lev:name {lit(name)} }} }}""")


def insert_appearance(store, sb_match, sb_team, sb_player):
    store.update(P + f"""INSERT DATA {{ GRAPH {G} {{
        lev:appearance_{int(sb_match)}_{int(sb_player)} a lev:Appearance ;
            lev:appearanceIn {ind('match', sb_match)} ; lev:appearanceFor {ind('team', sb_team)} ;
            lev:appearanceOf {ind('player', sb_player)} }} }}""")


def rename_player(store, sb_player, name):
    store.update(P + f"""
        DELETE {{ GRAPH {G} {{ ?p lev:name ?old }} }}
        INSERT {{ GRAPH {G} {{ ?p lev:name {lit(name)} }} }}
        WHERE  {{ GRAPH {G} {{ BIND({ind('player', sb_player)} AS ?p) ?p lev:name ?old }} }}""")


def delete_player(store, sb_player):
    """Removes the player and his appearances in ONE request, guarded: nothing happens if
    any event still references him (the WHERE clause plays the role of ON DELETE RESTRICT)."""
    p = ind("player", sb_player)
    store.update(P + f"""
        DELETE {{ GRAPH {G} {{ ?a ?ap ?ao . {p} ?x ?y }} }}
        WHERE  {{ GRAPH {G} {{
          {p} ?x ?y .
          OPTIONAL {{ ?a lev:appearanceOf {p} ; ?ap ?ao }}
          FILTER NOT EXISTS {{ ?e lev:performedBy {p} }}
          FILTER NOT EXISTS {{ ?e2 lev:intendedFor {p} }} }} }}""")


# ------------------------------------------------------------------ events
_EVENT_FIELDS = """?uuid ?class ?sbMatchId ?kickOff ?player ?sbPlayerId ?period ?minute ?second ?outcome
                   ?intendedFor ?assistedShooter ?assistedOutcome"""


def _event_pattern(where=""):
    return f"""
      ?e lev:sbEventUuid ?uuid ; a ?class ; lev:inMatch ?m ; lev:performedBy ?p ;
         lev:period ?period ; lev:minute ?minute ; lev:second ?second .
      ?class rdfs:subClassOf lev:MatchEvent .
      ?m lev:sbMatchId ?sbMatchId ; lev:kickOff ?kickOff .
      ?p lev:name ?player ; lev:sbPlayerId ?sbPlayerId .
      {where}
      OPTIONAL {{ ?e lev:outcome ?outcome }}
      OPTIONAL {{ ?e lev:intendedFor/lev:name ?intendedFor }}
      OPTIONAL {{ ?e lev:assists ?shot . ?shot lev:performedBy/lev:name ?assistedShooter .
                 OPTIONAL {{ ?shot lev:outcome ?assistedOutcome }} }}"""


def search_events(store, date_from="", date_to="", minute_from=None, minute_to=None, player_q="",
                  event_class="", outcome="", sb_match=None, assists_only=False, limit=25, offset=0):
    f = []
    for d in (date_from, date_to):
        if d and not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            raise ValueError("dates must be YYYY-MM-DD")
    if date_from:
        f.append(f'FILTER(?kickOff >= "{date_from}T00:00:00"^^xsd:dateTime)')
    if date_to:
        f.append(f'FILTER(?kickOff <= "{date_to}T23:59:59"^^xsd:dateTime)')
    if minute_from is not None:
        f.append(f"FILTER(?minute >= {int(minute_from)})")
    if minute_to is not None:
        f.append(f"FILTER(?minute <= {int(minute_to)})")
    if player_q:
        f.append(f"FILTER(CONTAINS(LCASE(?player), LCASE({lit(player_q)})))")
    if event_class:
        if not re.match(r"^[A-Za-z]+$", event_class):
            raise ValueError("invalid event class")
        f.append(f"?e a lev:{event_class} .")
    if outcome:
        f.append(f"?e lev:outcome {lit(outcome)} .")
    if sb_match:
        f.append(f"FILTER(?m = {ind('match', sb_match)})")
    if assists_only:
        f.append("?e lev:assists ?anyShot .")
    where = "\n      ".join(f)
    total = _rows(store, f"""SELECT (COUNT(DISTINCT ?e) AS ?n) WHERE {{ GRAPH {G} {{
        ?e lev:inMatch ?m ; lev:performedBy ?p ; lev:minute ?minute ; a ?class .
        ?class rdfs:subClassOf lev:MatchEvent .
        ?m lev:kickOff ?kickOff . ?p lev:name ?player . {where} }} }}""")[0]["n"]
    rows = _rows(store, f"""SELECT {_EVENT_FIELDS} WHERE {{ GRAPH {G} {{ {_event_pattern(where)} }} }}
        ORDER BY ?kickOff ?period ?minute ?second ?uuid LIMIT {int(limit)} OFFSET {int(offset)}""")
    for r in rows:
        r["class"] = _local(r["class"])
    return total, rows


def get_event(store, uuid):
    rows = _rows(store, f"""SELECT {_EVENT_FIELDS} WHERE {{ GRAPH {G} {{
        {_event_pattern(f'FILTER(?e = {ind("event", uuid)})')} }} }}""")
    for r in rows:
        r["class"] = _local(r["class"])
    return rows[0] if rows else None


def event_exists(store, uuid):
    return store.ask(P + f"ASK {{ GRAPH {G} {{ ?e lev:sbEventUuid {lit(uuid)} }} }}")


def event_is_assisted(store, uuid):
    return store.ask(P + f"ASK {{ GRAPH {G} {{ ?pass lev:assists {ind('event', uuid)} }} }}")


def shots_in_match(store, sb_match):
    return _rows(store, f"""SELECT ?uuid ?player ?period ?minute ?second ?outcome WHERE {{ GRAPH {G} {{
        ?s a lev:Shot ; lev:sbEventUuid ?uuid ; lev:inMatch {ind('match', sb_match)} ;
           lev:performedBy/lev:name ?player ; lev:period ?period ; lev:minute ?minute ; lev:second ?second .
        OPTIONAL {{ ?s lev:outcome ?outcome }}
        FILTER NOT EXISTS {{ ?anyPass lev:assists ?s }} }} }} ORDER BY ?period ?minute ?second""")


def insert_event(store, uuid, event_class, sb_match, sb_player, period, minute, second,
                 outcome=None, intended_for=None, assists_uuid=None):
    e = ind("event", uuid)
    types = f"lev:{event_class}" + (" , lev:Goal" if event_class == "Shot" and outcome == "Goal" else "")
    extra = ""
    if outcome:
        extra += f" ; lev:outcome {lit(outcome)}"
    if intended_for:
        extra += f" ; lev:intendedFor {ind('player', intended_for)}"
    if assists_uuid:
        extra += f" ; lev:assists {ind('event', assists_uuid)}"
    store.update(P + f"""INSERT DATA {{ GRAPH {G} {{
        {e} a {types} ; lev:sbEventUuid {lit(uuid)} ; lev:inMatch {ind('match', sb_match)} ;
            lev:performedBy {ind('player', sb_player)} ;
            lev:period {int(period)} ; lev:minute {int(minute)} ; lev:second {int(second)}{extra} }} }}""")


def update_event(store, uuid, period, minute, second, outcome):
    """DELETE the old time/outcome (and the derived lev:Goal type), INSERT the new values."""
    e = ind("event", uuid)
    new = f"?e lev:period {int(period)} ; lev:minute {int(minute)} ; lev:second {int(second)} ."
    if outcome:
        new += f" ?e lev:outcome {lit(outcome)} ."
    store.update(P + f"""
        DELETE {{ GRAPH {G} {{ ?e lev:period ?p ; lev:minute ?m ; lev:second ?s . ?e lev:outcome ?o . ?e a lev:Goal }} }}
        INSERT {{ GRAPH {G} {{ {new} }} }}
        WHERE  {{ GRAPH {G} {{ BIND({e} AS ?e) ?e lev:period ?p ; lev:minute ?m ; lev:second ?s .
                              OPTIONAL {{ ?e lev:outcome ?o }} }} }}""")
    if outcome == "Goal":     # keep the materialised inference Goal == Shot and outcome "Goal"
        store.update(P + f"""INSERT {{ GRAPH {G} {{ {e} a lev:Goal }} }}
                             WHERE {{ GRAPH {G} {{ {e} a lev:Shot }} }}""")


def delete_event(store, uuid):
    """Guarded: deletes all triples of the event only if no other triple points at it."""
    e = ind("event", uuid)
    store.update(P + f"""DELETE {{ GRAPH {G} {{ {e} ?p ?o }} }}
                         WHERE  {{ GRAPH {G} {{ {e} ?p ?o . FILTER NOT EXISTS {{ ?x ?y {e} }} }} }}""")
