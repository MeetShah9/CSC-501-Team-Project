"""User-interface layer: a small Flask web app over the relational database.

Pages: dashboard, match browser, event search (retrieve / update / delete),
add event, add player to a match squad, player search (update / delete),
and a read-only page showing the demonstration SELECT queries.
"""
import sqlite3

from flask import Flask, flash, g, redirect, render_template, request, url_for

from src.biz import services
from src.biz.services import ValidationError
from src.cmn.config import DB_PATH
from src.dal import database, queries, repositories as repo

PAGE_SIZE = 25


def create_app(db_path=DB_PATH) -> Flask:
    app = Flask(__name__)
    app.secret_key = "beyond-the-scoresheet-demo"       # demo only: flash messages
    app.config["DB_PATH"] = str(db_path)

    def db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = database.connect(app.config["DB_PATH"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    # ---------------------------------------------------------------- dashboard
    @app.route("/")
    def index():
        return render_template("index.html", counts=repo.counts(db()))

    @app.route("/matches")
    def matches():
        return render_template("matches.html", matches=repo.list_matches(db()))

    # ---------------------------------------------------------------- events
    @app.route("/events")
    def events():
        page = max(int(request.args.get("page", 1) or 1), 1)
        f = {k: request.args.get(k, "") for k in ("match_id", "player", "event_type", "outcome")}
        f["assists_only"] = bool(request.args.get("assists_only"))
        total, rows = repo.search_events(
            db(), match_id=int(f["match_id"]) if f["match_id"] else None, player_q=f["player"],
            event_type=f["event_type"], outcome=f["outcome"], assists_only=f["assists_only"],
            limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
        args = {k: v for k, v in request.args.items() if k != "page"}
        return render_template("events.html", rows=rows, total=total, page=page, pages=max(-(-total // PAGE_SIZE), 1),
                               f=f, args=args, matches=repo.list_matches(db()), types=repo.event_types(db()))

    @app.route("/events/new", methods=["GET", "POST"])
    def event_new():
        conn = db()
        if request.method == "POST":
            try:
                new_id = services.add_event(conn, request.form)
                flash(f"Event #{new_id} added.", "ok")
                return redirect(url_for("event_edit", event_id=new_id))
            except ValidationError as exc:
                flash(str(exc), "error")
        match_id = request.values.get("match_id", type=int)
        return render_template(
            "event_new.html", matches=repo.list_matches(conn), match_id=match_id, types=repo.event_types(conn),
            squad=repo.players_in_match(conn, match_id) if match_id else [],
            shots=repo.shots_in_match(conn, match_id) if match_id else [], form=request.form)

    @app.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
    def event_edit(event_id):
        conn = db()
        if request.method == "POST":
            try:
                services.edit_event(conn, event_id, request.form)
                flash(f"Event #{event_id} updated.", "ok")
                return redirect(url_for("event_edit", event_id=event_id))
            except ValidationError as exc:
                flash(str(exc), "error")
        ev = repo.get_event(conn, event_id)
        if ev is None:
            flash("Event not found.", "error")
            return redirect(url_for("events"))
        return render_template("event_edit.html", e=ev)

    @app.post("/events/<int:event_id>/delete")
    def event_delete(event_id):
        try:
            services.remove_event(db(), event_id)
            flash(f"Event #{event_id} deleted.", "ok")
        except ValidationError as exc:
            flash(str(exc), "error")
            return redirect(url_for("event_edit", event_id=event_id))
        return redirect(url_for("events"))

    # ---------------------------------------------------------------- players
    @app.route("/players")
    def players():
        q = request.args.get("q", "")
        return render_template("players.html", q=q, rows=repo.search_players(db(), q))

    @app.route("/players/new", methods=["GET", "POST"])
    def player_new():
        conn = db()
        if request.method == "POST":
            try:
                services.add_player_to_match(conn, request.form)
                flash("Player added to the match squad.", "ok")
                return redirect(url_for("players", q=request.form.get("name", "")))
            except ValidationError as exc:
                flash(str(exc), "error")
        match_id = request.values.get("match_id", type=int)
        return render_template("player_new.html", matches=repo.list_matches(conn), match_id=match_id,
                               teams=repo.match_teams(conn, match_id) if match_id else [], form=request.form)

    @app.route("/players/<int:player_id>/edit", methods=["GET", "POST"])
    def player_edit(player_id):
        conn = db()
        if request.method == "POST":
            try:
                services.rename_player(conn, player_id, request.form.get("name"))
                flash("Player updated.", "ok")
                return redirect(url_for("players", q=request.form.get("name", "")))
            except ValidationError as exc:
                flash(str(exc), "error")
        p = repo.get_player(conn, player_id)
        if p is None:
            flash("Player not found.", "error")
            return redirect(url_for("players"))
        return render_template("player_edit.html", p=p)

    @app.post("/players/<int:player_id>/delete")
    def player_delete(player_id):
        try:
            services.remove_player(db(), player_id)
            flash("Player deleted.", "ok")
        except ValidationError as exc:
            flash(str(exc), "error")
            return redirect(url_for("player_edit", player_id=player_id))
        return redirect(url_for("players"))

    # ---------------------------------------------------------------- queries
    @app.route("/queries")
    def queries_page():
        out = []
        for q in queries.load_named_queries():
            cols, rows = queries.run_query(db(), q["sql"])
            out.append({**q, "cols": cols, "rows": rows[:10], "n": len(rows)})
        return render_template("queries.html", queries=out)

    return app
