"""Business layer for the knowledge graph: validation and integrity rules.

Why this layer matters more here than for SQLite: under the Open World Assumption the
triple store accepts any triple. Cardinalities, keys, ranges and "foreign keys" in the
ontology describe the data but are not enforced on INSERT/DELETE. So every rule the
relational schema enforced is checked here before a statement is sent:

  rule (relational origin)                      check here
  NOT NULL, CHECK on Period/Minute/Second       _int(...) ranges; period 1..5, second 0..59
  UK_SbPlayerId / owl:hasKey                    a new player gets a fresh sbPlayerId
  composite FK AppearsFor -> MatchTeam          the team must play in the match
  UK_AppearsFor_MatchId_PlayerId                one appearance per (match, player)
  FK performedBy / intendedFor (squad rule)     both players appeared in the match
  CK_MatchEvent_PassLinks                       only a Pass gets intendedFor / assists
  trigger (assist -> Shot of same match)        the assisted shot is in the same match
  UK on AssistedShotEventId (inverse functional) the shot is not already assisted
  FK ON DELETE RESTRICT                         guarded deletes (see kg_repositories)

The UI never writes SPARQL; it calls these functions.
"""
import uuid as uuidlib

from src.dal import kg_repositories as repo
from src.dal.kg_store import StoreError


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
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        raise ValidationError(f"{label} must be between {lo} and {hi}.")
    return n


def _text(value, label, required=True, max_len=120):
    v = (value or "").strip()
    if required and not v:
        raise ValidationError(f"{label} is required.")
    if len(v) > max_len:
        raise ValidationError(f"{label} is too long (max {max_len} characters).")
    return v or None


def _match_and_squad(store, sb_match):
    if sb_match not in {m["sbMatchId"] for m in repo.list_matches(store)}:
        raise ValidationError("Unknown match.")
    return {p["sbPlayerId"] for p in repo.players_in_match(store, sb_match)}


def _event_fields(store, form, prefix, sb_match, squad, classes):
    """Validate one event row of a form. Returns kwargs for repo.insert_event or None if empty."""
    g = lambda k: form.get(prefix + k)
    event_class = (g("event_class") or "").strip()
    if not event_class:
        return None
    if event_class not in classes:
        raise ValidationError(f"Unknown event type {event_class!r}.")
    ev = dict(event_class=event_class,
              period=_int(g("period"), "Period", 1, 5),
              minute=_int(g("minute"), "Minute", 0, 130),
              second=_int(g("second"), "Second", 0, 59),
              outcome=_text(g("outcome"), "Outcome", required=False, max_len=40),
              intended_for=_int(g("intended_for"), "Intended-for player", required=False),
              assists_uuid=(g("assists") or "").strip() or None)
    if event_class != "Pass" and (ev["intended_for"] or ev["assists_uuid"]):
        raise ValidationError("Only a Pass can have an intended-for player or an assisted shot.")
    if ev["outcome"] == "Goal" and event_class != "Shot":
        raise ValidationError("Only a Shot can have the outcome 'Goal'.")
    if ev["intended_for"] and ev["intended_for"] not in squad:
        raise ValidationError("The intended-for player must have appeared in the same match.")
    if ev["assists_uuid"]:
        shots = {s["uuid"] for s in repo.shots_in_match(store, sb_match)}   # unassisted shots of this match
        if ev["assists_uuid"] not in shots:
            raise ValidationError("The assisted event must be a not-yet-assisted Shot of the same match.")
    return ev


# ------------------------------------------------------------------ data entry
def add_player_with_events(store, form) -> tuple[int, int]:
    """Find-or-create a player by name, add him to a match squad, and insert the events he performed.

    Returns (sbPlayerId, number of events inserted). All rows are validated before
    anything is written, so a bad event row does not leave a half-entered player.
    """
    name = _text(form.get("name"), "Player name")
    sb_match = _int(form.get("match_id"), "Match")
    sb_team = _int(form.get("team_id"), "Team")
    squad = _match_and_squad(store, sb_match)
    if sb_team not in {t["sbTeamId"] for t in repo.match_teams(store, sb_match)}:
        raise ValidationError("That team did not play in the selected match.")
    classes = set(repo.event_classes(store))
    existing = repo.find_player_by_name(store, name)
    sb_player = existing or repo.next_manual_player_id(store)
    new_appearance = not (existing and repo.has_appearance(store, sb_match, existing))
    squad_after = squad | {sb_player}
    events = [e for e in (_event_fields(store, form, f"e{i}_", sb_match, squad_after, classes)
                          for i in range(1, 4)) if e]
    if not new_appearance and not events:
        raise ValidationError("That player is already in the squad for this match; add at least one event.")
    try:
        if not existing:
            repo.insert_player(store, sb_player, name)
        if new_appearance:
            repo.insert_appearance(store, sb_match, sb_team, sb_player)
        for ev in events:
            repo.insert_event(store, str(uuidlib.uuid4()), sb_match=sb_match, sb_player=sb_player, **ev)
    except StoreError as exc:
        raise ValidationError(str(exc))
    return sb_player, len(events)


def add_event(store, form) -> str:
    sb_match = _int(form.get("match_id"), "Match")
    sb_player = _int(form.get("player_id"), "Player")
    squad = _match_and_squad(store, sb_match)
    if sb_player not in squad:
        raise ValidationError("That player did not appear in the selected match.")
    ev = _event_fields(store, form, "", sb_match, squad, set(repo.event_classes(store)))
    if ev is None:
        raise ValidationError("Event type is required.")
    new = str(uuidlib.uuid4())
    try:
        repo.insert_event(store, new, sb_match=sb_match, sb_player=sb_player, **ev)
    except StoreError as exc:
        raise ValidationError(str(exc))
    return new


# ------------------------------------------------------------------ update / delete
def edit_event(store, uuid, form) -> None:
    ev = repo.get_event(store, uuid)
    if ev is None:
        raise ValidationError("Event not found.")
    outcome = _text(form.get("outcome"), "Outcome", required=False, max_len=40)
    if outcome == "Goal" and ev["class"] != "Shot":
        raise ValidationError("Only a Shot can have the outcome 'Goal'.")
    repo.update_event(store, uuid, _int(form.get("period"), "Period", 1, 5),
                      _int(form.get("minute"), "Minute", 0, 130),
                      _int(form.get("second"), "Second", 0, 59), outcome)


def remove_event(store, uuid) -> None:
    if not repo.event_exists(store, uuid):
        raise ValidationError("Event not found.")
    if repo.event_is_assisted(store, uuid):
        raise ValidationError("This shot is the target of an assisting pass, so it cannot be deleted "
                              "until that pass is deleted first.")
    repo.delete_event(store, uuid)
    if repo.event_exists(store, uuid):          # the guarded DELETE refused it
        raise ValidationError("Delete refused: another resource still references this event.")


def rename_player(store, sb_player, name) -> None:
    name = _text(name, "Player name")
    if repo.get_player(store, sb_player) is None:
        raise ValidationError("Player not found.")
    repo.rename_player(store, sb_player, name)


def remove_player(store, sb_player) -> None:
    if repo.get_player(store, sb_player) is None:
        raise ValidationError("Player not found.")
    n = repo.player_references(store, sb_player)
    if n:
        raise ValidationError(f"This player is still referenced by {n} event(s) (performed by or intended "
                              "for), so he cannot be deleted.")
    repo.delete_player(store, sb_player)
