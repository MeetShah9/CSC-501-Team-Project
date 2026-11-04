-- =============================================================================
-- 04_update_delete.sql -- UPDATE / DELETE demonstrations and constraint checks
-- Blocks are named "-- name: <id> | <title>"; a block marked "-- expect: error"
-- must be rejected by the DBMS. `python main.py demo` runs every block inside a
-- transaction on an in-memory copy of the database, so nothing is changed.
-- Ids used below refer to the full database built by `python main.py build`.
-- =============================================================================

-- name: select_before_update | Check the WHERE clause with a SELECT before updating
SELECT Id, Name FROM Player WHERE Name = 'Florian Wirtz';

-- name: update_player_name | UPDATE a single tuple (correct a name)
UPDATE Player SET Name = 'Florian Richard Wirtz' WHERE Name = 'Florian Wirtz';

-- name: update_event_outcome | UPDATE an event's outcome (re-classify one shot)
UPDATE MatchEvent
SET Outcome = 'Saved'
WHERE SbEventUuid = '5085715b-09f6-403c-8b67-a546bcfed0ec';

-- name: delete_unreferenced_event | DELETE an event nobody references
DELETE FROM MatchEvent
WHERE SbEventUuid = '4c9d47f0-9ffb-4cb0-a6ef-e6c9b0581f11';     -- the assisting pass

-- name: delete_referenced_shot | DELETE a shot that a pass assists
-- expect: error
DELETE FROM MatchEvent
WHERE SbEventUuid = '5085715b-09f6-403c-8b67-a546bcfed0ec';     -- still referenced

-- name: delete_player_with_events | DELETE a player who still has events
-- expect: error
DELETE FROM Player WHERE Name = 'Florian Wirtz';

-- name: duplicate_team | INSERT violating candidate key UK_Name
-- expect: error
INSERT INTO Team(SbTeamId, Name) VALUES (999999, 'Bayer Leverkusen');

-- name: bad_second | INSERT violating CHECK on Second
-- expect: error
INSERT INTO MatchEvent(SbEventUuid, MatchId, PlayerId, EventType, Period, Minute, Second)
VALUES ('demo-bad-second', 1, 1, 'Carry', 1, 10, 75);

-- name: link_to_non_shot | UPDATE with an assist pointing to a non-Shot (trigger)
-- expect: error
UPDATE MatchEvent
SET AssistedShotEventId = (SELECT Id FROM MatchEvent WHERE SbEventUuid = '1cfc163d-727f-4823-b67c-70f03ff0894a')
WHERE SbEventUuid = '4c9d47f0-9ffb-4cb0-a6ef-e6c9b0581f11';

-- name: pass_links_on_non_pass | CHECK: only a Pass may have an intended-for / assist link
-- expect: error
UPDATE MatchEvent SET IntendedForPlayerId = 1
WHERE SbEventUuid = '5085715b-09f6-403c-8b67-a546bcfed0ec';     -- a Shot
