"""Data layer: the triple-store driver.

Two interchangeable back ends with the same three methods:

    select(sparql) -> (columns, rows)      SELECT queries, rows of plain Python values
    ask(sparql)    -> bool                 ASK queries
    triples(sparql)-> rdflib.Graph         CONSTRUCT / DESCRIBE queries
    update(sparql) -> None                 INSERT / DELETE / CLEAR (SPARQL 1.1 Update)

VirtuosoStore  server-based: talks to Virtuoso's SPARQL endpoint over HTTP
               (default http://localhost:8890/sparql; the SPARQL account needs the
               SPARQL_SELECT and SPARQL_UPDATE roles, manual 5.2.3).
LocalStore     embedded: an in-process rdflib Dataset. No server needed; used when
               KG_BACKEND=local (tests, machines without Virtuoso). Changes live in
               memory only and are lost when the process stops.

Choose with the environment variable KG_BACKEND=virtuoso|local.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from src.cmn.config import GRAPH_IRI, KG_BACKEND, KG_SAMPLE_PATH, ONTOLOGY_PATH, VIRTUOSO_ENDPOINT


class StoreError(Exception):
    pass


def _value(binding):
    """SPARQL JSON result term -> Python value (int for integer literals, str otherwise)."""
    if binding is None:
        return None
    v, dt = binding["value"], binding.get("datatype", "")
    if dt.endswith(("#integer", "#int", "#long", "#nonNegativeInteger", "#short")):
        return int(v)
    if dt.endswith(("#decimal", "#double", "#float")):
        return float(v)
    if dt.endswith("#boolean"):
        return v in ("true", "1")
    return v


class VirtuosoStore:
    name = "Virtuoso"

    def __init__(self, endpoint: str = VIRTUOSO_ENDPOINT, timeout: int = 120):
        self.endpoint, self.timeout = endpoint, timeout

    def _post(self, sparql: str, accept: str) -> bytes:
        body = urllib.parse.urlencode({"query": sparql}).encode()   # Virtuoso takes updates in "query" too
        req = urllib.request.Request(self.endpoint, data=body, method="POST", headers={
            "Accept": accept, "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            raise StoreError(f"Virtuoso rejected the request ({exc.code}): "
                             f"{exc.read().decode(errors='replace')[:400]}") from exc
        except urllib.error.URLError as exc:
            raise StoreError(f"Cannot reach Virtuoso at {self.endpoint} ({exc.reason}). Is the server "
                             "running? Or set KG_BACKEND=local to use the embedded store.") from exc

    def select(self, sparql):
        res = json.loads(self._post(sparql, "application/sparql-results+json"))
        cols = res["head"]["vars"]
        return cols, [tuple(_value(b.get(c)) for c in cols) for b in res["results"]["bindings"]]

    def ask(self, sparql):
        return bool(json.loads(self._post(sparql, "application/sparql-results+json"))["boolean"])

    def update(self, sparql):
        self._post(sparql, "application/sparql-results+json")

    def triples(self, sparql):
        from rdflib import Graph
        return Graph().parse(data=self._post(sparql, "text/turtle").decode("utf-8"), format="turtle")

    def ping(self) -> bool:
        try:
            return self.ask("ASK { }") or True
        except StoreError:
            return False


class LocalStore:
    """Embedded store. On first use it loads the ontology + sample KG into GRAPH_IRI."""
    name = "embedded rdflib store"

    def __init__(self, files=(ONTOLOGY_PATH, KG_SAMPLE_PATH), preload=True):
        from rdflib import Dataset, URIRef
        self.ds = Dataset(default_union=True)     # like Virtuoso: default graph = union of all graphs
        if preload:
            graph = self.ds.graph(URIRef(GRAPH_IRI))
            for f in files:
                graph.parse(str(f), format="xml")

    def select(self, sparql):
        res = self.ds.query(sparql)
        cols = [str(v) for v in res.vars]
        # rdflib returns URIRef / Literal objects -> plain str / int like the Virtuoso driver
        return cols, [tuple(None if t is None else _plain(t.toPython()) for t in row) for row in res]

    def triples(self, sparql):
        from rdflib import Graph
        g = Graph()
        for t in self.ds.query(sparql):
            g.add(t)
        return g

    def ask(self, sparql):
        return bool(self.ds.query(sparql).askAnswer)

    def update(self, sparql):
        try:
            self.ds.update(sparql)
        except Exception as exc:          # rdflib raises parser errors of several types
            raise StoreError(f"Update rejected: {exc}") from exc

    def ping(self):
        return True


def _plain(v):
    import datetime
    from decimal import Decimal
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return str(v)


_store = None


def get_store(backend: str | None = None):
    """Process-wide store (one LocalStore is shared so UI edits persist while the app runs)."""
    global _store
    backend = (backend or KG_BACKEND).lower()
    if _store is None or (backend == "local") != isinstance(_store, LocalStore):
        _store = LocalStore() if backend == "local" else VirtuosoStore()
    return _store


# ------------------------------------------------------------------ loading RDF/XML files
def load_files(store, files, graph_iri=GRAPH_IRI, clear=True, batch=1000, progress=print):
    """Load RDF/XML files into the named graph with SPARQL INSERT DATA batches.

    This is the scripted equivalent of Conductor -> Linked Data -> Quad Store Upload
    (manual 5.2.2) and works on any SPARQL 1.1 Update endpoint.
    """
    from rdflib import BNode, Graph
    if clear:
        store.update(f"CLEAR SILENT GRAPH <{graph_iri}>")
    total = 0
    for f in files:
        g = Graph().parse(str(f), format="xml")
        # blank nodes must keep their identity across batches: skolemise them into stable labels
        triples = list(g)
        lines = [f"{_nt(s)} {_nt(p)} {_nt(o)} ." for s, p, o in triples]
        # statements that mention a blank node go together in one batch so _:b labels stay consistent
        bn = [l for (s, p, o), l in zip(triples, lines) if isinstance(s, BNode) or isinstance(o, BNode)]
        plain = [l for (s, p, o), l in zip(triples, lines) if not (isinstance(s, BNode) or isinstance(o, BNode))]
        chunks = ([bn] if bn else []) + [plain[i:i + batch] for i in range(0, len(plain), batch)]
        for chunk in chunks:
            store.update("INSERT DATA { GRAPH <%s> {\n%s\n} }" % (graph_iri, "\n".join(chunk)))
            total += len(chunk)
        progress(f"   loaded {Path(f).name}: {len(triples)} triples")
    return total


def _nt(term):
    return term.n3()
