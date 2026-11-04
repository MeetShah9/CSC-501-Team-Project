-- =============================================================================
-- 01_schema.sql  --  DDL for "Beyond the Scoresheet" (Bayer Leverkusen 2023/24)
-- Relational schema mapped from the team's ER diagram (see doc/).
-- DBMS: SQLite 3 (>= 3.35). Conventions follow the course manual:
--   * PascalCase table/column names, surrogate PK named Id (autoincrement)
--   * PK_/UK_/FK_ constraint prefixes,
--     FK_SourceTable_Column_2_TargetTable_TargetColumn
--   * Source-assigned StatsBomb ids are kept as candidate keys (UK_Sb*)
-- Run:  sqlite3 data/preprocessed/leverkusen.db < 01_schema.sql
-- =============================================================================

PRAGMA foreign_keys = ON;

-- Entity set Team ------------------------------------------------------------
CREATE TABLE Team (
    Id        INTEGER PRIMARY KEY AUTOINCREMENT,
    SbTeamId  INTEGER NOT NULL,
    Name      VARCHAR(255) NOT NULL,
    CONSTRAINT UK_SbTeamId UNIQUE (SbTeamId),
    CONSTRAINT UK_Name     UNIQUE (Name)
);

-- Entity set Player ----------------------------------------------------------
CREATE TABLE Player (
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    SbPlayerId  INTEGER NOT NULL,
    Name        VARCHAR(255) NOT NULL,
    CONSTRAINT UK_SbPlayerId UNIQUE (SbPlayerId)
);

-- Entity set Match -----------------------------------------------------------
CREATE TABLE Match (
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    SbMatchId   INTEGER NOT NULL,
    MatchDate   DATE NOT NULL,                     -- ISO-8601 'YYYY-MM-DD'
    CONSTRAINT UK_SbMatchId UNIQUE (SbMatchId)
);

-- Relationship "plays in" (Team M:N Match, attribute Home or away) ------------
-- Cardinality 2..2 per match (exactly one Home and one Away team) is enforced
-- partly here (UK_MatchId_HomeOrAway / UK_MatchId_TeamId) and completed by
-- the loader/business layer (SQL-92 has no declarative "exactly 2 rows").
CREATE TABLE MatchTeam (
    Id          INTEGER PRIMARY KEY AUTOINCREMENT,
    MatchId     INTEGER NOT NULL,
    TeamId      INTEGER NOT NULL,
    HomeOrAway  VARCHAR(4) NOT NULL,
    CONSTRAINT CK_MatchTeam_HomeOrAway CHECK (HomeOrAway IN ('Home', 'Away')),
    CONSTRAINT UK_MatchTeam_MatchId_TeamId     UNIQUE (MatchId, TeamId),
    CONSTRAINT UK_MatchTeam_MatchId_HomeOrAway UNIQUE (MatchId, HomeOrAway),
    CONSTRAINT FK_MatchTeam_MatchId_2_Match_Id
        FOREIGN KEY (MatchId) REFERENCES Match(Id),
    CONSTRAINT FK_MatchTeam_TeamId_2_Team_Id
        FOREIGN KEY (TeamId) REFERENCES Team(Id)
);

-- Ternary relationship "appears for" (Player appears for a Team in a Match) ---
-- The composite FK guarantees the team really took part in that match.
CREATE TABLE AppearsFor (
    Id        INTEGER PRIMARY KEY AUTOINCREMENT,
    MatchId   INTEGER NOT NULL,
    TeamId    INTEGER NOT NULL,
    PlayerId  INTEGER NOT NULL,
    CONSTRAINT UK_AppearsFor_MatchId_PlayerId UNIQUE (MatchId, PlayerId),
    CONSTRAINT FK_AppearsFor_MatchId_TeamId_2_MatchTeam_MatchId_TeamId
        FOREIGN KEY (MatchId, TeamId) REFERENCES MatchTeam(MatchId, TeamId),
    CONSTRAINT FK_AppearsFor_PlayerId_2_Player_Id
        FOREIGN KEY (PlayerId) REFERENCES Player(Id)
);

-- Entity set MatchEvent, with the relationships
--   "contains"     (Match 1 : 1..N MatchEvent)     -> MatchId
--   "performed by" (Player 1 : 0..N MatchEvent)    -> PlayerId
--   "intended for" (Player 0..1 : 0..N MatchEvent) -> IntendedForPlayerId
--   "assists"      (pass 0..1 : shot 0..1)         -> AssistedShotEventId
-- and the composite attribute Match time (Period, Minute, Second).
-- Outcome is nullable: many event types (Carry, Pressure, ...) have none.
CREATE TABLE MatchEvent (
    Id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    SbEventUuid          CHAR(36) NOT NULL,
    MatchId              INTEGER NOT NULL,
    PlayerId             INTEGER NOT NULL,
    EventType            VARCHAR(64) NOT NULL,
    Period               INTEGER NOT NULL,
    Minute               INTEGER NOT NULL,
    Second               INTEGER NOT NULL,
    Outcome              VARCHAR(64),
    IntendedForPlayerId  INTEGER,            -- only for Pass, intended target
    AssistedShotEventId  INTEGER,            -- only for Pass, the shot it assists
    CONSTRAINT UK_SbEventUuid UNIQUE (SbEventUuid),
    -- 1-to-1: a shot is assisted by at most one pass
    CONSTRAINT UK_MatchEvent_AssistedShotEventId UNIQUE (AssistedShotEventId),
    CONSTRAINT CK_MatchEvent_Period CHECK (Period BETWEEN 1 AND 5),
    CONSTRAINT CK_MatchEvent_Minute CHECK (Minute >= 0),
    CONSTRAINT CK_MatchEvent_Second CHECK (Second BETWEEN 0 AND 59),
    CONSTRAINT CK_MatchEvent_PassLinks CHECK (
        (IntendedForPlayerId IS NULL AND AssistedShotEventId IS NULL)
        OR EventType = 'Pass'),
    CONSTRAINT FK_MatchEvent_MatchId_2_Match_Id
        FOREIGN KEY (MatchId) REFERENCES Match(Id),
    CONSTRAINT FK_MatchEvent_PlayerId_2_Player_Id
        FOREIGN KEY (PlayerId) REFERENCES Player(Id),
    CONSTRAINT FK_MatchEvent_IntendedForPlayerId_2_Player_Id
        FOREIGN KEY (IntendedForPlayerId) REFERENCES Player(Id),
    CONSTRAINT FK_MatchEvent_AssistedShotEventId_2_MatchEvent_Id
        FOREIGN KEY (AssistedShotEventId) REFERENCES MatchEvent(Id)
);

-- Triggers for what CHECK cannot express (cross-row rules) --------------------
-- An assisted event must be a Shot in the same match as the assisting Pass.
CREATE TRIGGER TR_MatchEvent_AssistsShot_Insert
BEFORE INSERT ON MatchEvent
WHEN NEW.AssistedShotEventId IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'AssistedShotEventId must reference a Shot of the same match')
    WHERE NOT EXISTS (SELECT 1 FROM MatchEvent AS S
                      WHERE S.Id = NEW.AssistedShotEventId
                        AND S.EventType = 'Shot'
                        AND S.MatchId = NEW.MatchId);
END;

CREATE TRIGGER TR_MatchEvent_AssistsShot_Update
BEFORE UPDATE OF AssistedShotEventId, MatchId ON MatchEvent
WHEN NEW.AssistedShotEventId IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'AssistedShotEventId must reference a Shot of the same match')
    WHERE NOT EXISTS (SELECT 1 FROM MatchEvent AS S
                      WHERE S.Id = NEW.AssistedShotEventId
                        AND S.EventType = 'Shot'
                        AND S.MatchId = NEW.MatchId);
END;

-- Indexes on foreign keys / frequent filters ---------------------------------
CREATE INDEX IX_MatchEvent_MatchId             ON MatchEvent (MatchId);
CREATE INDEX IX_MatchEvent_PlayerId            ON MatchEvent (PlayerId);
CREATE INDEX IX_MatchEvent_IntendedForPlayerId ON MatchEvent (IntendedForPlayerId);
CREATE INDEX IX_MatchEvent_EventType_Outcome   ON MatchEvent (EventType, Outcome);
CREATE INDEX IX_AppearsFor_PlayerId            ON AppearsFor (PlayerId);
