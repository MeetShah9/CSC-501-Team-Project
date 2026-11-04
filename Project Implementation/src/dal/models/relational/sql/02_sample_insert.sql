-- =============================================================================
-- 02_sample_insert.sql -- DML demonstration on a FRESH database (after 01_schema.sql)
-- Inserts the goal chain used in the report:
--   Leverkusen v Werder Bremen, 14 Apr 2024 (StatsBomb match 3895302)
--   Andrich's pass at 67:22 names Wirtz and assists Wirtz's shot at 67:25 (Goal).
-- Pattern from the manual: find-or-create parent rows first (no duplicates),
-- then insert child rows using the retrieved Ids.
-- =============================================================================
PRAGMA foreign_keys = ON;

-- Teams (find-or-create: insert only when the SbTeamId is not yet stored) ------
INSERT INTO Team(SbTeamId, Name)
SELECT 904, 'Bayer Leverkusen' WHERE NOT EXISTS (SELECT 1 FROM Team WHERE SbTeamId = 904);
INSERT INTO Team(SbTeamId, Name)
SELECT 176, 'Werder Bremen'    WHERE NOT EXISTS (SELECT 1 FROM Team WHERE SbTeamId = 176);

-- Players ------------------------------------------------------------------------
INSERT INTO Player(SbPlayerId, Name)
SELECT 9195,  'Robert Andrich' WHERE NOT EXISTS (SELECT 1 FROM Player WHERE SbPlayerId = 9195);
INSERT INTO Player(SbPlayerId, Name)
SELECT 40724, 'Florian Wirtz'  WHERE NOT EXISTS (SELECT 1 FROM Player WHERE SbPlayerId = 40724);

-- Match and "plays in" ---------------------------------------------------------
INSERT INTO Match(SbMatchId, MatchDate) VALUES (3895302, '2024-04-14');

INSERT INTO MatchTeam(MatchId, TeamId, HomeOrAway)
VALUES ((SELECT Id FROM Match WHERE SbMatchId = 3895302),
        (SELECT Id FROM Team  WHERE SbTeamId  = 904), 'Home');
INSERT INTO MatchTeam(MatchId, TeamId, HomeOrAway)
VALUES ((SELECT Id FROM Match WHERE SbMatchId = 3895302),
        (SELECT Id FROM Team  WHERE SbTeamId  = 176), 'Away');

-- "appears for" (ternary Player-Team-Match) ----------------------------------------
INSERT INTO AppearsFor(MatchId, TeamId, PlayerId)
VALUES ((SELECT Id FROM Match  WHERE SbMatchId  = 3895302),
        (SELECT Id FROM Team   WHERE SbTeamId   = 904),
        (SELECT Id FROM Player WHERE SbPlayerId = 9195));
INSERT INTO AppearsFor(MatchId, TeamId, PlayerId)
VALUES ((SELECT Id FROM Match  WHERE SbMatchId  = 3895302),
        (SELECT Id FROM Team   WHERE SbTeamId   = 904),
        (SELECT Id FROM Player WHERE SbPlayerId = 40724));

-- MatchEvent: the shot first (so the pass can reference it) ---------------------------
INSERT INTO MatchEvent(SbEventUuid, MatchId, PlayerId, EventType, Period, Minute, Second, Outcome)
VALUES ('5085715b-09f6-403c-8b67-a546bcfed0ec',
        (SELECT Id FROM Match  WHERE SbMatchId  = 3895302),
        (SELECT Id FROM Player WHERE SbPlayerId = 40724),
        'Shot', 2, 67, 25, 'Goal');

-- MatchEvent: the pass, with "intended for" and "assists" links ------------------------
INSERT INTO MatchEvent(SbEventUuid, MatchId, PlayerId, EventType, Period, Minute, Second,
                       Outcome, IntendedForPlayerId, AssistedShotEventId)
VALUES ('4c9d47f0-9ffb-4cb0-a6ef-e6c9b0581f11',
        (SELECT Id FROM Match  WHERE SbMatchId  = 3895302),
        (SELECT Id FROM Player WHERE SbPlayerId = 9195),
        'Pass', 2, 67, 22, 'Complete',
        (SELECT Id FROM Player     WHERE SbPlayerId = 40724),
        (SELECT Id FROM MatchEvent WHERE SbEventUuid = '5085715b-09f6-403c-8b67-a546bcfed0ec'));

-- Constraint demonstrations (each statement below is REJECTED; run manually) ----------
-- Duplicate candidate key  -> UNIQUE constraint failed: Team.Name
--   INSERT INTO Team(SbTeamId, Name) VALUES (999, 'Bayer Leverkusen');
-- Unknown parent           -> FOREIGN KEY constraint failed
--   INSERT INTO MatchEvent(SbEventUuid, MatchId, PlayerId, EventType, Period, Minute, Second)
--   VALUES ('x', 999, 1, 'Pass', 1, 0, 0);
-- Assist pointing to a non-shot -> AssistedShotEventId must reference a Shot of the same match
--   UPDATE MatchEvent SET AssistedShotEventId = Id WHERE SbEventUuid = '4c9d47f0-9ffb-4cb0-a6ef-e6c9b0581f11';
