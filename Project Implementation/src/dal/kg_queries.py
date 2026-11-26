"""Data layer: read the named SPARQL blocks of the *.sparql scripts.

A block starts with a header line   # name: <id> | <title>
and runs until the next header. Comment lines are kept (SPARQL ignores them).
"""
import re
from pathlib import Path

from src.cmn.config import SEMANTIC_DIR

_HEADER = re.compile(r"^# name:\s*(\w+)\s*\|\s*(.+)$", re.M)

SCRIPTS = {
    "debug": "00_debug.sparql",
    "insert": "01_insert.sparql",
    "select": "02_select_queries.sparql",
    "update": "03_update_delete.sparql",
    "checks": "04_integrity_checks.sparql",
}


def load_blocks(script: str) -> list[dict]:
    path = Path(SEMANTIC_DIR / SCRIPTS.get(script, script))
    text = path.read_text(encoding="utf-8")
    heads = list(_HEADER.finditer(text))
    out = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[h.end():end].strip()
        out.append({"name": h.group(1), "title": h.group(2).strip(), "sparql": body, "form": form_of(body)})
    return out


def form_of(sparql: str) -> str:
    """Query form of a block: SELECT, ASK, CONSTRUCT, DESCRIBE or UPDATE."""
    code = "\n".join(l for l in sparql.splitlines() if not l.lstrip().startswith(("#", "PREFIX", "prefix")))
    m = re.search(r"\b(SELECT|ASK|CONSTRUCT|DESCRIBE|INSERT|DELETE|CLEAR|LOAD|DROP)\b", code, re.I)
    kw = m.group(1).upper() if m else "SELECT"
    return "UPDATE" if kw in ("INSERT", "DELETE", "CLEAR", "LOAD", "DROP") else kw


def run(store, block_or_sparql):
    """Run any block; returns ('table', cols, rows) | ('bool', value) | ('graph', triples) | ('update',)."""
    sparql = block_or_sparql["sparql"] if isinstance(block_or_sparql, dict) else block_or_sparql
    form = form_of(sparql)
    if form == "SELECT":
        return ("table", *store.select(sparql))
    if form == "ASK":
        return ("bool", store.ask(sparql))
    if form in ("CONSTRUCT", "DESCRIBE"):
        return ("graph", store.triples(sparql))
    store.update(sparql)
    return ("update",)


def with_graph(sparql: str, graph_iri: str) -> str:
    """Point a block at another named graph (used to run demos on a scratch copy)."""
    from src.cmn.config import GRAPH_IRI
    return sparql.replace(f"<{GRAPH_IRI}>", f"<{graph_iri}>")
