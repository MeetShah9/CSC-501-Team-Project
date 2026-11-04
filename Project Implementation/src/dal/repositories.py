"""Data layer: all SQL used by the user interface (parameterised, no string-built SQL
except for fixed column lists). Functions take an open connection and return plain rows."""
import sqlite3

OWN_TEAM = "Bayer Leverkusen"


def counts(conn):
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("Team", "Player", "Match", "AppearsFor", "MatchEvent")}


# --- matches / teams ------------------------------------------------------------
def list_matches(conn):
    return conn.execute(
        """SELECT Match.Id, Match.SbMatchId, Match.MatchDate,
                  Opp.Name AS Opponent, OwnSide.HomeOrAway AS Venue
           FROM Match
           JOIN MatchTeam AS OwnSide ON OwnSide.MatchId = Match.Id
           JOIN Team AS Own ON Own.Id = OwnSide.TeamId AND Own.Name = ?
           JOIN MatchTeam AS OppSide ON OppSide.MatchId = Match.Id AND OppSide.TeamId <> Own.Id
           JOIN Team AS Opp ON Opp.Id = OppSide.TeamId
           ORDER BY Match.MatchDate""", (OWN_TEAM,)).fetchall()


def match_teams(conn, match_id):
    return conn.execute(
        """SELECT Team.Id, Team.Name, MatchTeam.HomeOrAway FROM MatchTeam
           JOIN Team ON Team.Id = MatchTeam.TeamId WHERE MatchTeam.MatchId = ?""", (match_id,)).fetchall()


def players_in_match(conn, match_id):
    return conn.execute(
        """SELECT Player.Id, Player.Name, Team.Name AS Team FROM AppearsFor
           JOIN Player ON Player.Id = AppearsFor.PlayerId
           JOIN Team ON Team.Id = AppearsFor.TeamId
           WHERE AppearsFor.MatchId = ? ORDER BY Team.Name, Player.Name""", (match_id,)).fetchall()


def shots_in_match(conn, match_id):
    return conn.execute(
        """SELECT E.Id, Player.Name, E.Period, E.Minute, E.Second, E.Outcome
           FROM MatchEvent AS E JOIN Player ON Player.Id = E.PlayerId
           WHERE E.MatchId = ? AND E.EventType = 'Shot'
           ORDER BY E.Period, E.Minute, E.Second""", (match_id,)).fetchall()


# --- players --------------------------------------------------------------------
def search_players(conn, name_q=""):
    return conn.execute(
        """SELECT Player.Id, Player.SbPlayerId, Player.Name,
                  (SELECT COUNT(*) FROM AppearsFor WHERE PlayerId = Player.Id) AS Matches,
                  (SELECT COUNT(*) FROM MatchEvent WHERE PlayerId = Player.Id) AS Events
           FROM Player WHERE Name LIKE ? ORDER BY Name LIMIT 200""", (f"%{name_q}%",)).fetchall()


def get_player(conn, player_id):
    return conn.execute("SELECT * FROM Player WHERE Id = ?", (player_id,)).fetchone()


def find_player_by_name(conn, name):
    return conn.execute("SELECT Id FROM Player WHERE lower(Name) = lower(?)", (name,)).fetchone()


def next_manual_sb_player_id(conn):
    return conn.execute("SELECT MAX(MAX(SbPlayerId), 8999999) + 1 FROM Player").fetchone()[0]


def insert_player(conn, sb_id, name):
    return conn.execute("INSERT INTO Player(SbPlayerId, Name) VALUES (?, ?)", (sb_id, name)).lastrowid


def insert_appearance(conn, match_id, team_id, player_id):
    return conn.execute("INSERT INTO AppearsFor(MatchId, TeamId, PlayerId) VALUES (?, ?, ?)",
                        (match_id, team_id, player_id)).lastrowid


def update_player(conn, player_id, name):
    return conn.execute("UPDATE Player SET Name = ? WHERE Id = ?", (name, player_id)).rowcount


def delete_player(conn, player_id):
    return conn.execute("DELETE FROM Player WHERE Id = ?", (player_id,)).rowcount


def delete_player_appearances(conn, player_id):
    return conn.execute("DELETE FROM AppearsFor WHERE PlayerId = ?", (player_id,)).rowcount


# --- events ---------------------------------------------------------------------
EVENT_SELECT = """
    SELECT E.Id, E.SbEventUuid, Match.MatchDate, Match.Id AS MatchId, Player.Name AS Player,
           E.EventType, E.Period, E.Minute, E.Second, E.Outcome,
           Intended.Name AS IntendedFor, ShotP.Name AS AssistedShooter,
           Shot.Outcome AS AssistedShotOutcome
    FROM MatchEvent AS E
    JOIN Match  ON Match.Id = E.MatchId
    JOIN Player ON Player.Id = E.PlayerId
    LEFT JOIN Player AS Intended ON Intended.Id = E.IntendedForPlayerId
    LEFT JOIN MatchEvent AS Shot ON Shot.Id = E.AssistedShotEventId
    LEFT JOIN Player AS ShotP ON ShotP.Id = Shot.PlayerId
"""


def event_types(conn):
    return [r[0] for r in conn.execute("SELECT DISTINCT EventType FROM MatchEvent ORDER BY 1")]


def search_events(conn, match_id=None, player_q="", event_type="", outcome="",
                  assists_only=False, limit=25, offset=0):
    where, args = [], []
    if match_id:
        where.append("E.MatchId = ?"); args.append(match_id)
    if player_q:
        where.append("Player.Name LIKE ?"); args.append(f"%{player_q}%")
    if event_type:
        where.append("E.EventType = ?"); args.append(event_type)
    if outcome:
        where.append("E.Outcome = ?"); args.append(outcome)
    if assists_only:
        where.append("E.AssistedShotEventId IS NOT NULL")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(
        f"SELECT COUNT(*) FROM MatchEvent AS E JOIN Player ON Player.Id = E.PlayerId {clause}", args
    ).fetchone()[0]
    rows = conn.execute(
        f"{EVENT_SELECT} {clause} ORDER BY Match.MatchDate, E.MatchId, E.Period, E.Minute, E.Second, E.Id "
        f"LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
    return total, rows


def get_event(conn, event_id):
    return conn.execute(EVENT_SELECT + " WHERE E.Id = ?", (event_id,)).fetchone()


def insert_event(conn, uuid, match_id, player_id, event_type, period, minute, second,
                 outcome, intended_for, assisted_shot):
    return conn.execute(
        """INSERT INTO MatchEvent(SbEventUuid, MatchId, PlayerId, EventType, Period, Minute, Second,
                                  Outcome, IntendedForPlayerId, AssistedShotEventId)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uuid, match_id, player_id, event_type, period, minute, second, outcome,
         intended_for, assisted_shot)).lastrowid


def update_event(conn, event_id, period, minute, second, outcome):
    return conn.execute(
        "UPDATE MatchEvent SET Period = ?, Minute = ?, Second = ?, Outcome = ? WHERE Id = ?",
        (period, minute, second, outcome, event_id)).rowcount


def delete_event(conn, event_id):
    return conn.execute("DELETE FROM MatchEvent WHERE Id = ?", (event_id,)).rowcount


def event_match_id(conn, event_id):
    r = conn.execute("SELECT MatchId, PlayerId, EventType FROM MatchEvent WHERE Id = ?", (event_id,)).fetchone()
    return r
