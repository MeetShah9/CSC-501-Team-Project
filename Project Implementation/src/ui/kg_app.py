"""User-interface layer: a small Flask web app over the KNOWLEDGE GRAPH (Milestone 5).

End users never type SPARQL. Pages:
  dashboard · event search (by kick-off date range, minute range, player, type, outcome)
  add player + his events (data entry) · add one event · edit / delete event
  player search · rename / delete player · live SPARQL queries · integrity checks
All writes go through src/biz/kg_services.py (validation), which calls
src/dal/kg_repositories.py (SPARQL), which talks to the store (src/dal/kg_store.py).

    python main.py kg-ui            # Virtuoso at http://localhost:8890/sparql
    KG_BACKEND=local python main.py kg-ui    # embedded store, no server
"""
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

from src.biz import kg_services as svc
from src.biz.kg_demo import run_checks
from src.biz.kg_services import ValidationError
from src.dal import kg_queries as kq, kg_repositories as repo
from src.dal.kg_store import StoreError, get_store

PAGE_SIZE = 25


def create_kg_app(store=None) -> Flask:
    here = Path(__file__).resolve().parent          # absolute paths: works from any working directory
    app = Flask(__name__, static_folder=str(here / "static"), template_folder=str(here / "templates"))
    app.secret_key = "beyond-the-scoresheet-kg-demo"     # demo only: flash messages
    st = store or get_store()

    @app.errorhandler(StoreError)
    def store_down(exc):
        return render_template("kg_error.html", message=str(exc)), 503

    @app.context_processor
    def inject():
        return {"store_name": st.name}

    def _matches():
        return repo.list_matches(st)

    # ---------------------------------------------------------------- dashboard
    @app.route("/")
    def kg_index():
        return render_template("kg_index.html", counts=repo.counts(st))

    # ---------------------------------------------------------------- events
    @app.route("/events")
    def kg_events():
        a = request.args
        page = max(a.get("page", 1, type=int) or 1, 1)
        f = {k: a.get(k, "") for k in ("date_from", "date_to", "minute_from", "minute_to", "player",
                                       "event_class", "outcome", "match_id")}
        f["assists_only"] = bool(a.get("assists_only"))
        try:
            total, rows = repo.search_events(
                st, date_from=f["date_from"], date_to=f["date_to"],
                minute_from=svc._int(f["minute_from"], "Minute from", 0, 130, required=False),
                minute_to=svc._int(f["minute_to"], "Minute to", 0, 130, required=False),
                player_q=f["player"], event_class=f["event_class"], outcome=f["outcome"],
                sb_match=svc._int(f["match_id"], "Match", required=False), assists_only=f["assists_only"],
                limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
        except (ValidationError, ValueError) as exc:
            flash(str(exc), "error")
            total, rows = 0, []
        args = {k: v for k, v in a.items() if k != "page"}
        return render_template("kg_events.html", rows=rows, total=total, page=page,
                               pages=max(-(-total // PAGE_SIZE), 1), f=f, args=args,
                               matches=_matches(), classes=repo.event_classes(st))

    @app.route("/events/new", methods=["GET", "POST"])
    def kg_event_new():
        if request.method == "POST":
            try:
                new = svc.add_event(st, request.form)
                flash("Event added.", "ok")
                return redirect(url_for("kg_event_edit", uuid=new))
            except ValidationError as exc:
                flash(str(exc), "error")
        mid = request.values.get("match_id", type=int)
        return render_template("kg_event_new.html", matches=_matches(), match_id=mid,
                               classes=repo.event_classes(st), form=request.form,
                               squad=repo.players_in_match(st, mid) if mid else [],
                               shots=repo.shots_in_match(st, mid) if mid else [])

    @app.route("/events/<uuid>/edit", methods=["GET", "POST"])
    def kg_event_edit(uuid):
        try:
            if request.method == "POST":
                svc.edit_event(st, uuid, request.form)
                flash("Event updated.", "ok")
                return redirect(url_for("kg_event_edit", uuid=uuid))
            ev = repo.get_event(st, uuid)
        except (ValidationError, ValueError) as exc:
            flash(str(exc), "error")
            ev = repo.get_event(st, uuid) if request.method == "POST" else None
        if ev is None:
            flash("Event not found.", "error")
            return redirect(url_for("kg_events"))
        return render_template("kg_event_edit.html", e=ev)

    @app.post("/events/<uuid>/delete")
    def kg_event_delete(uuid):
        try:
            svc.remove_event(st, uuid)
            flash("Event deleted (all of its triples removed).", "ok")
        except (ValidationError, ValueError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("kg_event_edit", uuid=uuid))
        return redirect(url_for("kg_events"))

    # ---------------------------------------------------------------- players
    @app.route("/players")
    def kg_players():
        q = request.args.get("q", "")
        return render_template("kg_players.html", q=q, rows=repo.search_players(st, q))

    @app.route("/players/new", methods=["GET", "POST"])
    def kg_player_new():
        if request.method == "POST":
            try:
                sb, n = svc.add_player_with_events(st, request.form)
                flash(f"Saved {request.form.get('name')} (sbPlayerId {sb}) with {n} event(s).", "ok")
                return redirect(url_for("kg_events", player=request.form.get("name", ""),
                                        match_id=request.form.get("match_id")))
            except ValidationError as exc:
                flash(str(exc), "error")
        mid = request.values.get("match_id", type=int)
        return render_template("kg_player_new.html", matches=_matches(), match_id=mid, form=request.form,
                               teams=repo.match_teams(st, mid) if mid else [],
                               squad=repo.players_in_match(st, mid) if mid else [],
                               classes=repo.event_classes(st))

    @app.route("/players/<int:sb_player>/edit", methods=["GET", "POST"])
    def kg_player_edit(sb_player):
        if request.method == "POST":
            try:
                svc.rename_player(st, sb_player, request.form.get("name"))
                flash("Player updated.", "ok")
                return redirect(url_for("kg_players", q=request.form.get("name", "")))
            except ValidationError as exc:
                flash(str(exc), "error")
        p = repo.get_player(st, sb_player)
        if p is None:
            flash("Player not found.", "error")
            return redirect(url_for("kg_players"))
        return render_template("kg_player_edit.html", p=p, refs=repo.player_references(st, sb_player))

    @app.post("/players/<int:sb_player>/delete")
    def kg_player_delete(sb_player):
        try:
            svc.remove_player(st, sb_player)
            flash("Player and his appearances deleted.", "ok")
        except ValidationError as exc:
            flash(str(exc), "error")
            return redirect(url_for("kg_player_edit", sb_player=sb_player))
        return redirect(url_for("kg_players"))

    # ---------------------------------------------------------------- queries / checks
    @app.route("/queries")
    def kg_queries_page():
        out = []
        for b in kq.load_blocks("select"):
            res = kq.run(st, b)
            item = {**b, "kind": res[0]}
            if res[0] == "table":
                item.update(cols=res[1], rows=[[_short(v) for v in r] for r in res[2][:10]], n=len(res[2]))
            elif res[0] == "bool":
                item.update(value=res[1])
            else:
                item.update(triples=[[_short(t) for t in tr] for tr in sorted(res[1])[:10]], n=len(res[1]))
            out.append(item)
        return render_template("kg_queries.html", queries=out)

    @app.route("/checks")
    def kg_checks():
        blocks = kq.load_blocks("checks")
        failed = set(run_checks(st, quiet=True))
        return render_template("kg_checks.html", blocks=blocks, failed=failed)

    return app


def _short(v):
    s = "" if v is None else str(v)
    return s.split("#")[-1] if s.startswith("http") else s
