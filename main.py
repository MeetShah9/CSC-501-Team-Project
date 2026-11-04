"""Entry point of the pipeline.

    python main.py download [--source-dir DIR]   fetch raw StatsBomb files
    python main.py build                         create DB from scratch + load data
    python main.py demo                          run the SQL demonstration scripts
    python main.py ui [--port 5000]              start the web interface
    python main.py all                           build + demo + ui
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download"); d.add_argument("--source-dir"); d.set_defaults(fn=cmd_download)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    sub.add_parser("demo").set_defaults(fn=cmd_demo)
    u = sub.add_parser("ui"); u.add_argument("--port", type=int, default=5000); u.set_defaults(fn=cmd_ui)
    a = sub.add_parser("all"); a.add_argument("--port", type=int, default=5000); a.set_defaults(fn=None)
    args = ap.parse_args()
    if args.cmd == "all":
        cmd_build(args); cmd_demo(args); cmd_ui(args)
    else:
        args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
