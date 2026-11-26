"""Entry point of the pipeline.

    python main.py download [--source-dir DIR]   fetch raw StatsBomb files
    python main.py build                         create DB from scratch + load data
    python main.py demo                          run the SQL demonstration scripts
    python main.py ui [--port 5000]              start the web interface
    python main.py all                           build + demo + ui

Semantic Web (Milestone 5), triple store chosen with --backend virtuoso|local
(default: $KG_BACKEND or virtuoso):
    python main.py kg-ontology                   write the ontology (TBox) .owl
    python main.py kg-build [--full]             write the knowledge graph (ABox) .rdf
    python main.py kg-load [--full]              load ontology + KG into Virtuoso (named graph)
    python main.py kg-demo                       run the SPARQL scripts 01-04 and print results
    python main.py kg-check [--reasoner]         run the integrity ASK checks (+ HermiT, optional)
    python main.py kg-ui [--port 5001]           start the knowledge-graph web interface
    python main.py kg-all                        kg-ontology + kg-build + kg-load + kg-demo + kg-ui
"""
import argparse
import sys
from pathlib import Path

from src.cmn.config import DB_PATH, SAMPLE_DB_PATH, SQL_DIR


def cmd_download(args):
    from src.biz.download import download
    n = download(Path(args.source_dir) if args.source_dir else None)
    print(f"Downloaded/verified files for {n} matches into data/raw/")


def cmd_build(_args):
    from src.biz import etl
    from src.dal import database
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.unlink(missing_ok=True)
    conn = database.connect(DB_PATH)
    database.create_schema(conn)
    stats = etl.load_all(conn)
    for w in stats.pop("warnings"):
        print("warning:", w)
    print("Loaded:", ", ".join(f"{k}={v}" for k, v in stats.items()))
    conn.close()
    print(f"Database written to {DB_PATH}")


def cmd_demo(_args):
    from src.biz.demo import run_demo
    run_demo()


def cmd_ui(args):
    from src.ui.app import create_app
    create_app().run(host="127.0.0.1", port=args.port, debug=False)


# ------------------------------------------------------------------ Semantic Web
def _store(args):
    from src.dal.kg_store import get_store
    return get_store(getattr(args, "backend", None))


def cmd_kg_ontology(_args):
    from src.biz.kg_ontology import write_ontology
    from src.cmn.config import ONTOLOGY_PATH
    print(f"Ontology (TBox): {write_ontology()} triples -> {ONTOLOGY_PATH}")


def cmd_kg_build(args):
    from src.biz.kg_etl import write_kg
    path, stats = write_kg(full=args.full)
    for w in stats.pop("warnings"):
        print("warning:", w)
    print("Individuals:", ", ".join(f"{k}={v}" for k, v in stats.items()))
    print(f"Knowledge graph (ABox) written to {path}")


def cmd_kg_load(args):
    from src.cmn.config import GRAPH_IRI, KG_FULL_PATH, KG_SAMPLE_PATH, ONTOLOGY_PATH
    from src.dal.kg_store import LocalStore, load_files
    store = _store(args)
    if isinstance(store, LocalStore):
        print("Embedded store: the ontology and sample graph are loaded automatically at start-up.")
        return
    kg = KG_FULL_PATH if args.full else KG_SAMPLE_PATH
    if not kg.exists():
        raise SystemExit(f"{kg} missing: run `python main.py kg-build{' --full' if args.full else ''}` first.")
    print(f"Loading into <{GRAPH_IRI}> at {store.endpoint} ...")
    n = load_files(store, [ONTOLOGY_PATH, kg])
    total = store.select(f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{GRAPH_IRI}> {{ ?s ?p ?o }} }}")[1][0][0]
    print(f"Sent {n} triples; the graph now holds {total} triples.")


def cmd_kg_demo(args):
    from src.biz.kg_demo import run_demo
    run_demo(_store(args))


def cmd_kg_check(args):
    from src.biz.kg_demo import run_checks
    print("SPARQL integrity checks (each ASK should be false):")
    failed = run_checks(_store(args))
    if args.reasoner:
        from src.biz.kg_reasoner import check_consistency
        print("\nOWL 2 reasoner (HermiT) on the ontology + the showcase match:")
        print("   " + check_consistency())
    sys.exit(1 if failed else 0)


def cmd_kg_ui(args):
    from src.ui.kg_app import create_kg_app
    create_kg_app(_store(args)).run(host="127.0.0.1", port=args.port, debug=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download"); d.add_argument("--source-dir"); d.set_defaults(fn=cmd_download)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    sub.add_parser("demo").set_defaults(fn=cmd_demo)
    u = sub.add_parser("ui"); u.add_argument("--port", type=int, default=5000); u.set_defaults(fn=cmd_ui)
    a = sub.add_parser("all"); a.add_argument("--port", type=int, default=5000); a.set_defaults(fn=None)
    kg = {"kg-ontology": cmd_kg_ontology, "kg-build": cmd_kg_build, "kg-load": cmd_kg_load,
          "kg-demo": cmd_kg_demo, "kg-check": cmd_kg_check, "kg-ui": cmd_kg_ui, "kg-all": None}
    for name, fn in kg.items():
        sp = sub.add_parser(name)
        sp.add_argument("--backend", choices=["virtuoso", "local"])
        if name in ("kg-build", "kg-load", "kg-all"):
            sp.add_argument("--full", action="store_true", help="all 137k events instead of the sample")
        if name == "kg-check":
            sp.add_argument("--reasoner", action="store_true", help="also run HermiT (needs Java + owlready2)")
        if name in ("kg-ui", "kg-all"):
            sp.add_argument("--port", type=int, default=5001)
        sp.set_defaults(fn=fn)
    args = ap.parse_args()
    if args.cmd == "all":
        cmd_build(args); cmd_demo(args); cmd_ui(args)
    elif args.cmd == "kg-all":
        cmd_kg_ontology(args); cmd_kg_build(args); cmd_kg_load(args); cmd_kg_demo(args); cmd_kg_ui(args)
    else:
        args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
