"""Business layer: run the SQL demonstration scripts (02, 03, 04) and print results.

Nothing persistent is changed: 02 runs on data/preprocessed/sample.db (rebuilt each
time); 03/04 run on an in-memory copy of the full database.
"""
import re
import sqlite3

from src.cmn.config import DB_PATH, SAMPLE_DB_PATH, SQL_DIR
from src.dal import database, queries

_BLOCK = re.compile(r"^-- name:\s*(\w+)\s*\|\s*(.+)$", re.M)


def _table(cols, rows, limit=8):
    print("   " + " | ".join(cols))
    for r in rows[:limit]:
        print("   " + " | ".join(str(v) for v in r))
    if len(rows) > limit:
        print(f"   ... ({len(rows)} rows)")


def parse_blocks(path):
    text = path.read_text(encoding="utf-8")
    heads = list(_BLOCK.finditer(text))
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[h.end():end].strip()
        yield h.group(1), h.group(2).strip(), body, "-- expect: error" in body


def run_demo() -> None:
    # 02: DML on a fresh database ---------------------------------------------------
    print("== 02_sample_insert.sql on a fresh database ==")
    SAMPLE_DB_PATH.unlink(missing_ok=True)
    conn = database.connect(SAMPLE_DB_PATH)
    database.create_schema(conn)
    database.run_script(conn, SQL_DIR / "02_sample_insert.sql")
    for t in ("Team", "Player", "Match", "MatchTeam", "AppearsFor", "MatchEvent"):
        print(f"   {t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} rows")
    q = next(q for q in queries.load_named_queries() if q["name"] == "assist_chain_example")
    _table(*queries.run_query(conn, q["sql"]))
    conn.close()

    # 03: SELECT queries on the full database -------------------------------------------
    if not DB_PATH.exists():
        raise SystemExit("Full database missing: run `python main.py build` first.")
    disk = database.connect(DB_PATH)
    mem = sqlite3.connect(":memory:")
    disk.backup(mem)
    disk.close()
    mem.row_factory = sqlite3.Row
    mem.execute("PRAGMA foreign_keys = ON")

    print("\n== 03_select_queries.sql on the full database ==")
    for q in queries.load_named_queries():
        print(f"-- {q['title']}")
        _table(*queries.run_query(mem, q["sql"]))

    # 04: UPDATE / DELETE / constraint checks (rolled back) --------------------------------
    print("\n== 04_update_delete.sql (each block runs on a clean state and is rolled back) ==")
    mem.isolation_level = None
    mem.execute("BEGIN")
    for name, title, body, expect_error in parse_blocks(SQL_DIR / "04_update_delete.sql"):
        sql = "\n".join(l for l in body.splitlines() if not l.strip().startswith("-- expect"))
        mem.execute("SAVEPOINT s")
        try:
            cur = mem.execute(sql)
            result = f"OK ({cur.rowcount} row(s) affected)" if cur.description is None else \
                     f"OK rows={[tuple(r) for r in cur.fetchall()]}"
            verdict = "UNEXPECTED SUCCESS" if expect_error else ""
        except sqlite3.Error as exc:
            result = f"rejected: {exc}"
            verdict = "" if expect_error else "UNEXPECTED ERROR"
        mem.execute("ROLLBACK TO s"); mem.execute("RELEASE s")   # every block starts from a clean state
        print(f"-- {title}\n   {result} {verdict}".rstrip())
    mem.execute("ROLLBACK")
    print("\nAll changes rolled back; database files untouched.")
