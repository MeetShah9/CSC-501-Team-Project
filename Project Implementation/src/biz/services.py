"""Business layer: validation and business rules between the UI and the data layer.

The UI never builds SQL; it calls these functions. Failures are raised as
ValidationError with a message that is safe to show to end users.
"""
import sqlite3
import uuid

from src.dal import repositories as repo


class ValidationError(Exception):
    pass


def _int(value, label, lo=None, hi=None, required=True):
    if value in (None, ""):
        if required:
            raise ValidationError(f"{label} is required.")
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a whole number.")
    if lo is not None and n < lo or hi is not None and n > hi:
        raise ValidationError(f"{label} must be between {lo} and {hi}.")
    return n


def _db_error(exc: sqlite3.Error) -> ValidationError:
    msg = str(exc)
    if "FOREIGN KEY" in msg:
        return ValidationError("Operation refused: other records still reference this row "
                               "(foreign-key constraint).")
    if "UNIQUE" in msg:
        return ValidationError(f"Duplicate value rejected ({msg.split(': ')[-1]}).")
    return ValidationError(f"Database rejected the change: {msg}")


# --- events ------------------------------------------------------------------------
def add_event(conn, form) -> int:
    match_id = _int(form.get("match_id"), "Match")
    player_id = _int(form.get("player_id"), "Player")
    event_type = (form.get("event_type") or "").strip()
    if not event_type:
        raise ValidationError("Event type is required.")
    period = _int(form.get("period"), "Period", 1, 5)
    minute = _int(form.get("minute"), "Minute", 0, 130)
    second = _int(form.get("second"), "Second", 0, 59)
    outcome = (form.get("outcome") or "").strip() or None
    intended = _int(form.get("intended_for"), "Intended-for player", required=False)
    assisted = _int(form.get("assisted_shot"), "Assisted shot", required=False)
    if event_type != "Pass" and (intended or assisted):
        raise ValidationError("Only a Pass can have an intended-for player or an assisted shot.")

    squad = {p["Id"] for p in repo.players_in_match(conn, match_id)}
    if player_id not in squad:
        raise ValidationError("That player did not appear in the selected match.")
    if intended and intended not in squad:
        raise ValidationError("The intended-for player must have appeared in the same match.")
    try:
        new_id = repo.insert_event(conn, str(uuid.uuid4()), match_id, player_id, event_type,
                                   period, minute, second, outcome, intended, assisted)
        conn.commit()
        return new_id
    except sqlite3.Error as exc:
        conn.rollback()
        raise _db_error(exc)


def edit_event(conn, event_id, form) -> None:
    period = _int(form.get("period"), "Period", 1, 5)
    minute = _int(form.get("minute"), "Minute", 0, 130)
    second = _int(form.get("second"), "Second", 0, 59)
    outcome = (form.get("outcome") or "").strip() or None
    try:
        if repo.update_event(conn, event_id, period, minute, second, outcome) == 0:
            raise ValidationError("Event not found.")
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise _db_error(exc)


def remove_event(conn, event_id) -> None:
    try:
        if repo.delete_event(conn, event_id) == 0:
            raise ValidationError("Event not found.")
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValidationError("This event is the target of an assisting pass, so it cannot be deleted "
                              "until that pass is deleted or edited first.") from exc


# --- players / squad -----------------------------------------------------------------
def add_player_to_match(conn, form) -> int:
    """Find-or-create the player by name, then register the appearance (manual 4.4 pattern)."""
    name = (form.get("name") or "").strip()
    if not name:
        raise ValidationError("Player name is required.")
    match_id = _int(form.get("match_id"), "Match")
    team_id = _int(form.get("team_id"), "Team")
    if team_id not in {t["Id"] for t in repo.match_teams(conn, match_id)}:
        raise ValidationError("That team did not play in the selected match.")
    try:
        existing = repo.find_player_by_name(conn, name)
        player_id = existing["Id"] if existing else repo.insert_player(
            conn, repo.next_manual_sb_player_id(conn), name)
        repo.insert_appearance(conn, match_id, team_id, player_id)
        conn.commit()
        return player_id
    except sqlite3.Error as exc:
        conn.rollback()
        if "AppearsFor" in str(exc) and "UNIQUE" in str(exc):
            raise ValidationError("That player is already in the squad for this match.")
        raise _db_error(exc)


def rename_player(conn, player_id, name) -> None:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Player name is required.")
    try:
        if repo.update_player(conn, player_id, name) == 0:
            raise ValidationError("Player not found.")
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise _db_error(exc)


def remove_player(conn, player_id) -> None:
    """A player can only be deleted when no event references them. Squad rows
    (AppearsFor) are removed together with the player in one transaction."""
    try:
        repo.delete_player_appearances(conn, player_id)
        if repo.delete_player(conn, player_id) == 0:
            raise ValidationError("Player not found.")
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValidationError("This player still has recorded events (or is named as an intended "
                              "target), so they cannot be deleted.") from exc
