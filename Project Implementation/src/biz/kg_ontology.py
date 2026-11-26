"""Business layer: build the project ontology (TBox) and write it as RDF/XML (.owl).

ER / relational model  ->  RDFS + OWL 2 (manual section 5.1):
  entity set            -> owl:Class            Team, Player, Match, MatchEvent
  IS-A                  -> rdfs:subClassOf      Pass, Shot, Carry, ... < MatchEvent; Goal < Shot
  attribute             -> owl:DatatypeProperty name, kickOff, period, minute, second, outcome, ...
  relationship          -> owl:ObjectProperty   inMatch, performedBy, intendedFor, assists, homeTeam, ...
  ternary "appears for" -> association class     Appearance (+ appearanceOf / appearanceFor / appearanceIn)
  "plays in" + HomeOrAway -> two sub-properties homeTeam / awayTeam of hasTeam
  cardinality           -> owl:Restriction       (owl:cardinality / owl:maxCardinality, qualified)
  PK / UNIQUE           -> owl:hasKey            sbTeamId, sbPlayerId, sbMatchId, sbEventUuid, (match, player)
  CHECK                 -> datatype restrictions xsd:integer[1..5] for period, [0..59] for second

The file is plain OWL 2 in RDF/XML, so it opens and can be edited in Protégé.
Run:  python main.py kg-ontology
"""
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, XSD

from src.cmn.config import NS, ONTOLOGY_IRI, ONTOLOGY_PATH

LEV = Namespace(NS)

# StatsBomb event type (as in the data) -> OWL class local name
EVENT_CLASSES = {
    "Pass": "Pass", "Ball Receipt*": "BallReceipt", "Carry": "Carry", "Pressure": "Pressure",
    "Ball Recovery": "BallRecovery", "Duel": "Duel", "Block": "Block", "Clearance": "Clearance",
    "Goal Keeper": "GoalKeeperAction", "Shot": "Shot", "Dribble": "Dribble",
    "Miscontrol": "Miscontrol", "Dispossessed": "Dispossessed", "Foul Committed": "FoulCommitted",
    "Interception": "Interception", "Foul Won": "FoulWon", "Dribbled Past": "DribbledPast",
    "Substitution": "Substitution", "50/50": "FiftyFifty", "Injury Stoppage": "InjuryStoppage",
    "Shield": "Shield", "Bad Behaviour": "BadBehaviour", "Player Off": "PlayerOff",
    "Player On": "PlayerOn", "Error": "Error", "Offside": "Offside",
    "Own Goal Against": "OwnGoalAgainst",
}
CLASS_TO_TYPE = {v: k for k, v in EVENT_CLASSES.items()}


def event_class_name(sb_type: str) -> str:
    """Unknown future StatsBomb types map to a CamelCase name (they are added on the fly)."""
    return EVENT_CLASSES.get(sb_type) or "".join(w.capitalize() for w in
                                                  sb_type.replace("*", "").replace("/", " ").split())


def _list(g, items):
    head = BNode()
    Collection(g, head, list(items))
    return head


def _restriction(g, cls, prop, kind, n, on_class=None, on_range=None):
    """cls rdfs:subClassOf [ a owl:Restriction ; owl:onProperty prop ; kind n (; owl:onClass) ]"""
    r = BNode()
    g.add((r, RDF.type, OWL.Restriction))
    g.add((r, OWL.onProperty, prop))
    g.add((r, kind, Literal(n, datatype=XSD.nonNegativeInteger)))
    if on_class is not None:
        g.add((r, OWL.onClass, on_class))
    if on_range is not None:
        g.add((r, OWL.onDataRange, on_range))
    g.add((cls, RDFS.subClassOf, r))


def _int_range(g, lo, hi):
    """xsd:integer[>= lo, <= hi] as an OWL 2 datatype restriction."""
    dt = BNode()
    g.add((dt, RDF.type, RDFS.Datatype))
    g.add((dt, OWL.onDatatype, XSD.integer))
    facets = []
    for facet, v in ((XSD.minInclusive, lo), (XSD.maxInclusive, hi)):
        f = BNode()
        g.add((f, facet, Literal(v, datatype=XSD.integer)))
        facets.append(f)
    g.add((dt, OWL.withRestrictions, _list(g, facets)))
    return dt


def build_ontology() -> Graph:
    g = Graph()
    g.bind("lev", LEV); g.bind("owl", OWL); g.bind("dcterms", DCTERMS)
    onto = URIRef(ONTOLOGY_IRI)
    g.add((onto, RDF.type, OWL.Ontology))
    g.add((onto, RDFS.label, Literal("Beyond the Scoresheet: Bayer Leverkusen 2023/24 ontology", lang="en")))
    g.add((onto, DCTERMS.creator, Literal("Meet Hemang Shah; Sakshi Pinkeshkumar Patel; Ayush Bharatbhai Patel")))
    g.add((onto, DCTERMS.source, URIRef("https://github.com/statsbomb/open-data")))
    g.add((onto, OWL.versionInfo, Literal("1.0 (CSC 501 Milestone 5, Semantic Web)")))
    g.add((onto, RDFS.comment, Literal(
        "Matches, teams, squads and timestamped player events of Bayer Leverkusen's 2023/24 Bundesliga "
        "season. Keeps the recorded player-event links explicit: performedBy, intendedFor (the pass's "
        "named target, not a guaranteed receipt) and assists (pass -> shot).", lang="en")))

    def cls(name, label, comment, parent=None):
        c = LEV[name]
        g.add((c, RDF.type, OWL.Class))
        g.add((c, RDFS.label, Literal(label, lang="en")))
        g.add((c, RDFS.comment, Literal(comment, lang="en")))
        if parent is not None:
            g.add((c, RDFS.subClassOf, parent))
        return c

    def obj(name, label, domain, rng, comment, *chars):
        p = LEV[name]
        g.add((p, RDF.type, OWL.ObjectProperty))
        for ch in chars:
            g.add((p, RDF.type, ch))
        g.add((p, RDFS.label, Literal(label, lang="en")))
        g.add((p, RDFS.comment, Literal(comment, lang="en")))
        if domain is not None:
            g.add((p, RDFS.domain, domain))
        if rng is not None:
            g.add((p, RDFS.range, rng))
        return p

    def data(name, label, domain, rng, comment, functional=True):
        p = LEV[name]
        g.add((p, RDF.type, OWL.DatatypeProperty))
        if functional:
            g.add((p, RDF.type, OWL.FunctionalProperty))
        g.add((p, RDFS.label, Literal(label, lang="en")))
        g.add((p, RDFS.comment, Literal(comment, lang="en")))
        if domain is not None:
            g.add((p, RDFS.domain, domain))
        g.add((p, RDFS.range, rng))
        return p

    # ---------------------------------------------------------------- classes (entity sets)
    Team = cls("Team", "Team", "A football club (entity set Team).")
    Player = cls("Player", "Player", "A football player (entity set Player).")
    Match = cls("Match", "Match", "A Bundesliga match of the 2023/24 season (entity set Match).")
    Appearance = cls("Appearance", "Appearance",
                     "Association class for the ternary relationship 'appears for': a player appears "
                     "for a team in a match (relational table AppearsFor).")
    Event = cls("MatchEvent", "Match event",
                "A timestamped on-ball or off-ball action performed by one player in one match "
                "(entity set MatchEvent). Specialised by event type (IS-A).")
    for sb_type, local in EVENT_CLASSES.items():
        cls(local, sb_type.replace("*", ""), f"StatsBomb event type '{sb_type}'.", Event)
    Pass, Shot = LEV.Pass, LEV.Shot
    Goal = cls("Goal", "Goal", "A shot whose outcome is 'Goal' (defined class).", Shot)
    # Goal == Shot and (outcome value "Goal")   -- a reasoner can classify goals from data
    hv = BNode()
    g.add((hv, RDF.type, OWL.Restriction)); g.add((hv, OWL.onProperty, LEV.outcome))
    g.add((hv, OWL.hasValue, Literal("Goal", datatype=XSD.string)))
    eq = BNode()
    g.add((eq, RDF.type, OWL.Class)); g.add((eq, OWL.intersectionOf, _list(g, [Shot, hv])))
    g.add((Goal, OWL.equivalentClass, eq))

    # Disjointness: an individual is one kind of thing only (no Player is a Team, etc.)
    for members in ([Team, Player, Match, Appearance, Event],
                    [LEV[c] for c in EVENT_CLASSES.values()]):
        d = BNode()
        g.add((d, RDF.type, OWL.AllDisjointClasses))
        g.add((d, OWL.members, _list(g, members)))

    # ---------------------------------------------------------------- object properties
    hasTeam = obj("hasTeam", "has team", Match, Team,
                  "Relationship 'plays in' seen from the match (Team M:N Match).")
    playsIn = obj("playsIn", "plays in", Team, Match, "Inverse of hasTeam.")
    g.add((playsIn, OWL.inverseOf, hasTeam))
    for side in ("home", "away"):
        p = obj(f"{side}Team", f"{side} team", Match, Team,
                f"The {side} side; replaces the relationship attribute HomeOrAway = '{side.capitalize()}'.",
                OWL.FunctionalProperty)
        g.add((p, RDFS.subPropertyOf, hasTeam))
    g.add((LEV.homeTeam, OWL.propertyDisjointWith, LEV.awayTeam))

    appearanceOf = obj("appearanceOf", "appearance of", Appearance, Player,
                       "The player of an appearance.", OWL.FunctionalProperty)
    appearanceFor = obj("appearanceFor", "appearance for", Appearance, Team,
                        "The team the player appeared for.", OWL.FunctionalProperty)
    appearanceIn = obj("appearanceIn", "appearance in", Appearance, Match,
                       "The match of the appearance.", OWL.FunctionalProperty)

    inMatch = obj("inMatch", "in match", Event, Match,
                  "Relationship 'contains' (Match 1 : 1..N MatchEvent).", OWL.FunctionalProperty)
    performedBy = obj("performedBy", "performed by", Event, Player,
                      "Relationship 'performed by' (Player 1 : 0..N MatchEvent).", OWL.FunctionalProperty)
    performed = obj("performed", "performed", Player, Event, "Inverse of performedBy.")
    g.add((performed, OWL.inverseOf, performedBy))
    intendedFor = obj("intendedFor", "intended for", Pass, Player,
                      "The pass's named target (StatsBomb pass.recipient). An intended target, not a "
                      "guaranteed receipt: incomplete passes keep it too.", OWL.FunctionalProperty)
    assists = obj("assists", "assists", Pass, Shot,
                  "Relationship 'assists' (pass 0..1 : shot 0..1). Functional and inverse functional: "
                  "a pass assists at most one shot and a shot is assisted by at most one pass.",
                  OWL.FunctionalProperty, OWL.InverseFunctionalProperty, OWL.AsymmetricProperty,
                  OWL.IrreflexiveProperty)
    assistedBy = obj("assistedBy", "assisted by", Shot, Pass, "Inverse of assists.")
    g.add((assistedBy, OWL.inverseOf, assists))

    # ---------------------------------------------------------------- datatype properties
    team_or_player = BNode()
    g.add((team_or_player, RDF.type, OWL.Class))
    g.add((team_or_player, OWL.unionOf, _list(g, [Team, Player])))
    name = data("name", "name", team_or_player, XSD.string, "Name of a team or player.")
    sbTeam = data("sbTeamId", "StatsBomb team id", Team, XSD.integer, "Source key (UK_SbTeamId).")
    sbPlayer = data("sbPlayerId", "StatsBomb player id", Player, XSD.integer, "Source key (UK_SbPlayerId).")
    sbMatch = data("sbMatchId", "StatsBomb match id", Match, XSD.integer, "Source key (UK_SbMatchId).")
    sbEvent = data("sbEventUuid", "StatsBomb event uuid", Event, XSD.string, "Source key (UK_SbEventUuid).")
    kickOff = data("kickOff", "kick-off", Match, XSD.dateTime,
                   "Kick-off date and time as given by StatsBomb (relational MatchDate plus kick-off time). "
                   "xsd:dateTime instead of xsd:date because xsd:date is not in the OWL 2 datatype map.")
    period_rng, second_rng = _int_range(g, 1, 5), _int_range(g, 0, 59)
    period = data("period", "period", Event, period_rng,
                  "Part of the composite attribute 'match time': 1-2 halves, 3-4 extra time, 5 penalties "
                  "(CK_MatchEvent_Period).")
    minute = data("minute", "minute", Event, XSD.nonNegativeInteger,
                  "Part of 'match time': minute on the match clock (CK_MatchEvent_Minute).")
    second = data("second", "second", Event, second_rng,
                  "Part of 'match time': second within the minute (CK_MatchEvent_Second).")
    outcome = data("outcome", "outcome", Event, XSD.string,
                   "Event outcome, e.g. Complete, Incomplete, Goal, Saved. Optional (many types have none).")

    # ---------------------------------------------------------------- cardinality restrictions
    one = OWL.qualifiedCardinality
    for c, p, n, kind, oc in (
            (Match, LEV.homeTeam, 1, one, Team), (Match, LEV.awayTeam, 1, one, Team),
            (Match, hasTeam, 2, one, Team),                       # plays in: exactly 2 teams
            (Match, sbMatch, 1, OWL.cardinality, None), (Match, kickOff, 1, OWL.cardinality, None),
            (Team, sbTeam, 1, OWL.cardinality, None), (Team, name, 1, OWL.cardinality, None),
            (Player, sbPlayer, 1, OWL.cardinality, None), (Player, name, 1, OWL.cardinality, None),
            (Appearance, appearanceOf, 1, one, Player), (Appearance, appearanceFor, 1, one, Team),
            (Appearance, appearanceIn, 1, one, Match),
            (Event, inMatch, 1, one, Match), (Event, performedBy, 1, one, Player),
            (Event, sbEvent, 1, OWL.cardinality, None), (Event, period, 1, OWL.cardinality, None),
            (Event, minute, 1, OWL.cardinality, None), (Event, second, 1, OWL.cardinality, None),
            (Event, outcome, 1, OWL.maxCardinality, None),
            (Pass, intendedFor, 1, OWL.maxQualifiedCardinality, Player),
            (Pass, assists, 1, OWL.maxQualifiedCardinality, Shot),
            (Shot, assistedBy, 1, OWL.maxQualifiedCardinality, Pass)):
        _restriction(g, c, p, kind, n, on_class=oc)
    # every match contains at least one event (contains 1..N)
    r = BNode()
    g.add((r, RDF.type, OWL.Restriction)); g.add((r, OWL.onProperty, LEV.hasEvent))
    g.add((r, OWL.someValuesFrom, Event)); g.add((Match, RDFS.subClassOf, r))
    hasEvent = obj("hasEvent", "has event", Match, Event, "Inverse of inMatch (relationship 'contains').")
    g.add((hasEvent, OWL.inverseOf, inMatch))

    # ---------------------------------------------------------------- keys (PK / UNIQUE)
    for c, props in ((Team, [sbTeam]), (Player, [sbPlayer]), (Match, [sbMatch]), (Event, [sbEvent]),
                     (Appearance, [appearanceIn, appearanceOf])):        # UK_AppearsFor_MatchId_PlayerId
        g.add((c, OWL.hasKey, _list(g, props)))
    return g


def write_ontology(path=ONTOLOGY_PATH) -> int:
    g = build_ontology()
    path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(path), format="xml")
    return len(g)
