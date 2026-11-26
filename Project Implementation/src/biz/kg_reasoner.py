"""Business layer (optional tool): check the ontology with an OWL 2 DL reasoner.

Loads the ontology plus a slice of the knowledge graph (the first 400 events plus all
shots and assisting passes of the showcase match, its squads, teams and the players they mention) and runs HermiT
through owlready2. Needs Java and `pip install owlready2`. Virtuoso itself does not
reason with OWL by default, which is why the business layer and the ASK checks
enforce the constraints; this tool shows the ontology's axioms are satisfiable and
that the data is consistent with them.
"""
import tempfile
from pathlib import Path

from src.cmn.config import KG_SAMPLE_PATH, NS, ONTOLOGY_PATH, SHOWCASE_SB_MATCH_ID


def slice_kg(n_events=400) -> Path:
    from rdflib import Graph, URIRef
    g = Graph().parse(str(KG_SAMPLE_PATH), format="xml")
    L = lambda x: URIRef(NS + x)
    m = L(f"match_{SHOWCASE_SB_MATCH_ID}")
    from rdflib.namespace import RDF
    in_match = set(g.subjects(L("inMatch"), m))
    shots = {e for e in in_match if (e, RDF.type, L("Shot")) in g}
    events = set(sorted(in_match)[:n_events]) | shots | {p for p in in_match if (p, L("assists"), None) in g}
    keep = set(events) | {m} | set(g.objects(m, None)) | set(g.subjects(L("appearanceIn"), m))
    for s in list(keep):
        keep |= {o for o in g.objects(s, None) if str(o).startswith(NS + "player_")}
    out = Graph()
    for s in keep:
        for t in g.triples((s, None, None)):
            if not (t[1] == L("assists") and t[2] not in keep):
                out.add(t)
    path = Path(tempfile.mkdtemp()) / "kg_slice.rdf"
    out.serialize(destination=str(path), format="xml")
    return path


def check_consistency() -> str:
    try:
        import owlready2
        from owlready2 import World, sync_reasoner
    except ImportError:
        return "skipped: pip install owlready2 (and install Java) to run HermiT"
    owlready2.reasoning.JAVA_MEMORY = 4000
    w = World()
    onto = w.get_ontology(ONTOLOGY_PATH.resolve().as_uri()).load()
    w.get_ontology(slice_kg().resolve().as_uri()).load()
    try:
        with onto:
            sync_reasoner(w, infer_property_values=False, debug=0)
    except owlready2.OwlReadyInconsistentOntologyError:
        return "INCONSISTENT: the data violates an axiom of the ontology"
    goals = len(list(onto.get_namespace(NS).Goal.instances()))
    return f"consistent (HermiT); lev:Goal individuals in the slice after reasoning: {goals}"
