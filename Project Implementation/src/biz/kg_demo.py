"""Business layer: run the SPARQL demonstration scripts and print the results.

    01_insert.sparql          on an EMPTY scratch graph   (<GRAPH_IRI>demo-insert/)
    02_select_queries.sparql  on the real graph            (read only)
    03_update_delete.sparql   on a scratch COPY of the real graph (<GRAPH_IRI>demo-update/)
    04_integrity_checks       on the real graph            (read only)

Scratch graphs are dropped at the end, so the real graph is never modified.
"""
from src.cmn.config import GRAPH_IRI
from src.dal import kg_queries as kq

INSERT_GRAPH = GRAPH_IRI + "demo-insert/"
UPDATE_GRAPH = GRAPH_IRI + "demo-update/"


def _count(store, graph):
    return store.select(f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}")[1][0][0]


def show(result, limit=8, indent="   "):
    kind = result[0]
    if kind == "table":
        _, cols, rows = result
        print(indent + " | ".join(cols))
        for r in rows[:limit]:
            print(indent + " | ".join("" if v is None else str(v).split("#")[-1] for v in r))
        if len(rows) > limit:
            print(f"{indent}... ({len(rows)} rows)")
        if not rows:
            print(indent + "(no rows)")
    elif kind == "bool":
        print(f"{indent}{result[1]}")
    elif kind == "graph":
        g = result[1]
        print(f"{indent}{len(g)} triples, e.g.")
        for s, p, o in sorted(g)[:min(limit, 5)]:
            print(f"{indent}  {s.split('#')[-1]}  {p.split('#')[-1]}  {str(o).split('#')[-1]}")


def run_checks(store, graph=GRAPH_IRI, quiet=False) -> list[str]:
    """Run every ASK in 04_integrity_checks.sparql; returns the names of violated checks."""
    failed = []
    for b in kq.load_blocks("checks"):
        violated = store.ask(kq.with_graph(b["sparql"], graph))
        if violated:
            failed.append(b["name"])
        if not quiet:
            print(f"   [{'VIOLATED' if violated else 'ok'}] {b['title']}")
    return failed


def run_demo(store) -> None:
    print(f"Triple store: {store.name}\n")
    if _count(store, GRAPH_IRI) == 0:
        raise SystemExit(f"Graph <{GRAPH_IRI}> is empty: run `python main.py kg-load` first.")

    # 01 -------------------------------------------------------------------------------
    print(f"== 01_insert.sparql on an empty graph <{INSERT_GRAPH}> ==")
    store.update(f"CLEAR SILENT GRAPH <{INSERT_GRAPH}>")
    for b in kq.load_blocks("insert"):
        res = kq.run(store, kq.with_graph(b["sparql"], INSERT_GRAPH))
        print(f"-- {b['title']}")
        if res[0] == "update":
            print(f"   graph now holds {_count(store, INSERT_GRAPH)} triples")
        else:
            show(res)
    before = _count(store, INSERT_GRAPH)
    kq.run(store, kq.with_graph(kq.load_blocks("insert")[0]["sparql"], INSERT_GRAPH))
    print(f"-- Re-running INSERT DATA: {before} -> {_count(store, INSERT_GRAPH)} triples "
          "(set semantics: duplicates are not stored)")
    store.update(f"DROP SILENT GRAPH <{INSERT_GRAPH}>")

    # 02 -------------------------------------------------------------------------------
    print(f"\n== 02_select_queries.sparql on <{GRAPH_IRI}> ==")
    for b in kq.load_blocks("select"):
        print(f"-- {b['title']}")
        show(kq.run(store, b))

    # 03 -------------------------------------------------------------------------------
    print(f"\n== 03_update_delete.sparql on a scratch copy <{UPDATE_GRAPH}> ==")
    store.update(f"DROP SILENT GRAPH <{UPDATE_GRAPH}>")
    store.update(f"INSERT {{ GRAPH <{UPDATE_GRAPH}> {{ ?s ?p ?o }} }} WHERE {{ GRAPH <{GRAPH_IRI}> {{ ?s ?p ?o }} }}")
    # the demo player from 01 (without events) is needed by the cascade-delete block
    for b in kq.load_blocks("insert")[1:2]:
        kq.run(store, kq.with_graph(b["sparql"], UPDATE_GRAPH))
    for b in kq.load_blocks("update"):
        n0 = _count(store, UPDATE_GRAPH)
        res = kq.run(store, kq.with_graph(b["sparql"], UPDATE_GRAPH))
        print(f"-- {b['title']}")
        if res[0] == "update":
            n1 = _count(store, UPDATE_GRAPH)
            print(f"   triples {n0} -> {n1} ({n1 - n0:+d})" + ("   nothing changed" if n0 == n1 else ""))
        else:
            show(res)
    print("-- 04 checks on the modified copy (the unguarded delete, duplicate team and bad second show up):")
    failed = run_checks(store, UPDATE_GRAPH, quiet=True)
    print("   violated: " + (", ".join(failed) if failed else "none"))
    store.update(f"DROP SILENT GRAPH <{UPDATE_GRAPH}>")

    # 04 -------------------------------------------------------------------------------
    print(f"\n== 04_integrity_checks.sparql on <{GRAPH_IRI}> (each ASK should be false) ==")
    failed = run_checks(store)
    print(f"\n{'All constraints hold.' if not failed else 'Violations: ' + ', '.join(failed)}"
          "  Scratch graphs dropped; the real graph is unchanged.")
