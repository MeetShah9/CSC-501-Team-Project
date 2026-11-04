"""Data layer: parse the named SELECT queries in 03_select_queries.sql."""
import re
import sqlite3

from src.cmn.config import SQL_DIR

_HEADER = re.compile(r"^-- name:\s*(\w+)\s*\|\s*(.+)$", re.M)


def load_named_queries() -> list[dict]:
    text = (SQL_DIR / "03_select_queries.sql").read_text(encoding="utf-8")
    heads = list(_HEADER.finditer(text))
    out = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[h.end():end].strip()
        out.append({"name": h.group(1), "title": h.group(2).strip(), "sql": body})
    return out


def run_query(conn: sqlite3.Connection, sql: str):
    cur = conn.execute(sql)
    cols = [c[0] for c in cur.description]
    return cols, [tuple(r) for r in cur.fetchall()]
