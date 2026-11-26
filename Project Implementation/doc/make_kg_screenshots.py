"""Developer helper: drives the knowledge-graph web UI with Playwright and saves labelled
screenshots to doc/screenshots/kg_*.png. Uses its own in-memory store (KG_BACKEND=local),
so Virtuoso and the real graph are untouched.
    python doc/make_kg_screenshots.py      (pip install playwright && playwright install chromium)
Set CHROME=/path/to/chrome to use an installed browser instead.
"""
import os, re, sys, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from src.dal.kg_store import LocalStore
from src.ui.kg_app import create_kg_app

OUT = ROOT / "doc" / "screenshots"; OUT.mkdir(exist_ok=True)
srv = make_server("127.0.0.1", 5056, create_kg_app(LocalStore()))
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5056"

with sync_playwright() as p:
    br = p.chromium.launch(executable_path=os.environ.get("CHROME") or None)
    pg = br.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
    def shot(name, full=False): pg.screenshot(path=str(OUT / name), full_page=full)
    pg.goto(B); shot("kg_01_dashboard.png")
    pg.goto(f"{B}/events?date_from=2024-04-01&date_to=2024-04-30&minute_from=60&minute_to=75&event_class=Goal"); shot("kg_02_search_by_datetime.png")
    pg.goto(f"{B}/players?q=wirtz"); shot("kg_03_search_player_by_name.png")
    pg.goto(f"{B}/players/new?match_id=3895302")
    pg.fill("[name=name]", "Demo Player"); pg.select_option("[name=team_id]", "904")
    for i, (cls, mi, se, out) in enumerate([("Pass", "10", "5", "Complete"), ("Shot", "11", "2", "Saved")], 1):
        pg.select_option(f"[name=e{i}_event_class]", cls); pg.fill(f"[name=e{i}_minute]", mi)
        pg.fill(f"[name=e{i}_second]", se); pg.fill(f"[name=e{i}_outcome]", out)
    pg.select_option("[name=e1_intended_for]", label=pg.eval_on_selector_all(
        "[name=e1_intended_for] option", "o=>o.map(x=>x.textContent).find(t=>t.includes('Wirtz'))"))
    shot("kg_04_add_player_events_form.png", True)
    pg.click("button:has-text('Save player and events')"); shot("kg_05_add_player_events_result.png")
    pg.click("a:has-text('edit / delete') >> nth=1")
    pg.fill("[name=minute]", "12"); pg.fill("[name=outcome]", "Goal"); pg.click("button:has-text('Save changes')")
    shot("kg_06_update_event.png")
    pg.once("dialog", lambda d: d.accept()); pg.click("button:has-text('Delete event')"); shot("kg_07_delete_event.png")
    pg.goto(f"{B}/events/5085715b-09f6-403c-8b67-a546bcfed0ec/edit")
    pg.once("dialog", lambda d: d.accept()); pg.click("button:has-text('Delete event')"); shot("kg_08_delete_refused.png")
    pg.goto(f"{B}/players?q=demo"); pg.click("a:has-text('edit / delete')")
    pg.once("dialog", lambda d: d.accept()); pg.click("button:has-text('Delete player')"); shot("kg_09_delete_player_refused.png")
    pg.goto(f"{B}/queries"); shot("kg_10_sparql_queries.png")
    pg.goto(f"{B}/checks"); shot("kg_11_integrity_checks.png", True)
    br.close()
srv.shutdown(); print("screenshots saved:", sorted(f.name for f in OUT.glob("kg_*.png")))
