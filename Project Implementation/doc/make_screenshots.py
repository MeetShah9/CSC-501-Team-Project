"""Developer helper: drives the web UI with Playwright and saves labelled screenshots to doc/screenshots.
Runs on a scratch COPY of the database so the real one is untouched.
    python doc/make_screenshots.py
"""
import shutil, sqlite3, sys, tempfile, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from src.ui.app import create_app

OUT = ROOT / "doc" / "screenshots"; OUT.mkdir(exist_ok=True)
tmp = Path(tempfile.mkdtemp()) / "copy.db"; shutil.copy(ROOT / "data/preprocessed/leverkusen.db", tmp)
srv = make_server("127.0.0.1", 5055, create_app(tmp)); threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5055"
c = sqlite3.connect(tmp)
mid = c.execute("select Id from Match where SbMatchId=3895302").fetchone()[0]

with sync_playwright() as p:
    br = p.chromium.launch(); pg = br.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=2)
    def shot(name, full=False): pg.screenshot(path=str(OUT / name), full_page=full)
    pg.goto(B); shot("01_dashboard.png")
    pg.goto(f"{B}/events?player=Wirtz&event_type=Shot&outcome=Goal"); shot("02_search_goals.png")
    pg.goto(f"{B}/events?match_id={mid}&assists_only=1"); shot("03_assisting_passes.png")
    pg.goto(f"{B}/events/new?match_id={mid}")
    pg.select_option("select[name=player_id]", label=pg.eval_on_selector_all("select[name=player_id] option", "o=>o.map(x=>x.textContent).find(t=>t.includes('Andrich'))"))
    pg.select_option("select[name=event_type]", "Pass"); pg.fill("[name=period]", "1"); pg.fill("[name=minute]", "10"); pg.fill("[name=second]", "5"); pg.fill("[name=outcome]", "Complete")
    pg.select_option("select[name=intended_for]", label=pg.eval_on_selector_all("select[name=intended_for] option", "o=>o.map(x=>x.textContent).find(t=>t.includes('Wirtz'))"))
    shot("04_add_event_form.png", True)
    pg.click("button:has-text('Add event')"); shot("05_add_event_result.png")
    pg.fill("[name=minute]", "12"); pg.fill("[name=outcome]", "Incomplete"); pg.click("button:has-text('Save changes')"); shot("06_update_event.png")
    pg.once("dialog", lambda d: d.accept()); pg.click("button:has-text('Delete event')"); shot("07_delete_event.png")
    pg.goto(f"{B}/events?match_id={mid}&event_type=Shot&outcome=Goal&player=Wirtz")
    pg.click("a:has-text('edit / delete')"); pg.once("dialog", lambda d: d.accept()); pg.click("button:has-text('Delete event')"); shot("08_delete_refused_fk.png")
    pg.goto(f"{B}/players/new?match_id={mid}"); pg.fill("[name=name]", "Demo Player"); shot("09_add_player_form.png")
    pg.click("button:has-text('Add to squad')"); shot("10_add_player_result.png")
    pg.goto(f"{B}/players?q=Wirtz"); pg.click("a:has-text('edit / delete')"); pg.once("dialog", lambda d: d.accept()); pg.click("button:has-text('Delete player')"); shot("11_delete_player_refused.png")
    pg.goto(f"{B}/queries"); shot("12_queries.png")
    br.close()
srv.shutdown(); print("screenshots saved:", sorted(f.name for f in OUT.iterdir()))
