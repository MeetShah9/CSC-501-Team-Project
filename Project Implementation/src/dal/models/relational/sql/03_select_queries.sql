-- =============================================================================
-- 03_select_queries.sql -- demonstration SELECT queries (joins, aggregation,
-- aliases, subqueries). Run against the full database (python main.py build).
-- Each block starts with "-- name: <id> | <title>" and is also shown in the
-- web UI ("Queries" page).
-- Team Id 904 in StatsBomb = Bayer Leverkusen; here we look it up by name.
-- =============================================================================

-- name: assist_chain_example | Report example: Andrich's pass at 67:22 -> Wirtz's shot (match 3895302)
-- Pass --assists--> Shot via a self-join of MatchEvent (aliases Pass / Shot).
SELECT Passer.Name         AS Passer,
       Intended.Name       AS IntendedFor,
       Pass.Minute || ':' || printf('%02d', Pass.Second) AS PassTime,
       Shooter.Name        AS Shooter,
       Shot.Minute || ':' || printf('%02d', Shot.Second) AS ShotTime,
       Shot.Outcome        AS ShotOutcome
FROM MatchEvent AS Pass
JOIN MatchEvent AS Shot      ON Pass.AssistedShotEventId = Shot.Id
JOIN Match                   ON Match.Id = Pass.MatchId
JOIN Player AS Passer        ON Passer.Id  = Pass.PlayerId
JOIN Player AS Shooter       ON Shooter.Id = Shot.PlayerId
LEFT JOIN Player AS Intended ON Intended.Id = Pass.IntendedForPlayerId
WHERE Match.SbMatchId = 3895302
  AND Passer.Name LIKE '%Andrich%'
  AND Pass.Minute = 67;

-- name: top_scorers | Leverkusen top scorers (JOIN + aggregation)
-- Goals = Shot events with outcome 'Goal'; the scorer's club in that match
-- comes from the ternary relationship AppearsFor.
SELECT Player.Name AS Player, COUNT(*) AS Goals
FROM MatchEvent AS Shot
JOIN Player     ON Player.Id = Shot.PlayerId
JOIN AppearsFor ON AppearsFor.MatchId = Shot.MatchId AND AppearsFor.PlayerId = Shot.PlayerId
JOIN Team       ON Team.Id = AppearsFor.TeamId
WHERE Shot.EventType = 'Shot'
  AND Shot.Outcome   = 'Goal'
  AND Team.Name      = 'Bayer Leverkusen'
GROUP BY Player.Id, Player.Name
ORDER BY Goals DESC, Player.Name
LIMIT 10;

-- name: top_assisters | Players with most goal assists (self-join, GROUP BY)
SELECT Passer.Name AS Player, COUNT(*) AS GoalAssists
FROM MatchEvent AS Pass
JOIN MatchEvent AS Shot ON Pass.AssistedShotEventId = Shot.Id
JOIN Player AS Passer   ON Passer.Id = Pass.PlayerId
WHERE Shot.Outcome = 'Goal'
GROUP BY Passer.Id, Passer.Name
ORDER BY GoalAssists DESC, Passer.Name
LIMIT 10;

-- name: duos | Most productive pass-to-goal pairs (assister -> scorer)
SELECT Passer.Name AS Assister, Shooter.Name AS Scorer, COUNT(*) AS Goals
FROM MatchEvent AS Pass
JOIN MatchEvent AS Shot ON Pass.AssistedShotEventId = Shot.Id
JOIN Player AS Passer   ON Passer.Id  = Pass.PlayerId
JOIN Player AS Shooter  ON Shooter.Id = Shot.PlayerId
WHERE Shot.Outcome = 'Goal'
GROUP BY Passer.Id, Shooter.Id
HAVING COUNT(*) >= 2
ORDER BY Goals DESC, Assister, Scorer
LIMIT 10;

-- name: intended_targets | Players most often named as the *intended* target of an incomplete pass
-- "intended for" is not a completed receipt: these passes named a target but did not reach him.
SELECT Intended.Name AS IntendedFor,
       COUNT(*)      AS IncompletePasses,
       COUNT(DISTINCT Pass.PlayerId) AS DifferentPassers
FROM MatchEvent AS Pass
JOIN Player AS Intended ON Intended.Id = Pass.IntendedForPlayerId
WHERE Pass.EventType = 'Pass' AND Pass.Outcome = 'Incomplete'
GROUP BY Intended.Id, Intended.Name
ORDER BY IncompletePasses DESC
LIMIT 10;

-- name: goals_per_match | Leverkusen goals per match with opponent and venue
SELECT Match.MatchDate,
       Opp.Name       AS Opponent,
       OwnSide.HomeOrAway AS Venue,
       COUNT(Shot.Id) AS LeverkusenGoals
FROM Match
JOIN MatchTeam AS OwnSide ON OwnSide.MatchId = Match.Id
JOIN Team      AS Own     ON Own.Id = OwnSide.TeamId AND Own.Name = 'Bayer Leverkusen'
JOIN MatchTeam AS OppSide ON OppSide.MatchId = Match.Id AND OppSide.TeamId <> Own.Id
JOIN Team      AS Opp     ON Opp.Id = OppSide.TeamId
LEFT JOIN (SELECT MatchEvent.Id, MatchEvent.MatchId
           FROM MatchEvent
           JOIN AppearsFor ON AppearsFor.MatchId = MatchEvent.MatchId
                          AND AppearsFor.PlayerId = MatchEvent.PlayerId
           WHERE MatchEvent.EventType = 'Shot' AND MatchEvent.Outcome = 'Goal'
             AND AppearsFor.TeamId = (SELECT Id FROM Team WHERE Name = 'Bayer Leverkusen')
          ) AS Shot ON Shot.MatchId = Match.Id
GROUP BY Match.Id
ORDER BY Match.MatchDate
LIMIT 40;

-- name: late_goals | Players who scored in the 85th minute or later (subquery with IN)
SELECT Player.Name, Match.MatchDate, Shot.Minute
FROM MatchEvent AS Shot
JOIN Player ON Player.Id = Shot.PlayerId
JOIN Match  ON Match.Id  = Shot.MatchId
WHERE Shot.EventType = 'Shot' AND Shot.Outcome = 'Goal' AND Shot.Minute >= 85
  AND Shot.PlayerId IN (SELECT AppearsFor.PlayerId
                        FROM AppearsFor JOIN Team ON Team.Id = AppearsFor.TeamId
                        WHERE Team.Name = 'Bayer Leverkusen')
ORDER BY Match.MatchDate, Shot.Minute;

-- name: scorers_without_assists | Scorers who never registered a goal assist (NOT EXISTS)
SELECT Player.Name, COUNT(*) AS Goals
FROM MatchEvent AS Shot
JOIN Player ON Player.Id = Shot.PlayerId
WHERE Shot.EventType = 'Shot' AND Shot.Outcome = 'Goal'
  AND NOT EXISTS (SELECT 1
                  FROM MatchEvent AS Pass
                  JOIN MatchEvent AS AssistedShot ON Pass.AssistedShotEventId = AssistedShot.Id
                  WHERE Pass.PlayerId = Shot.PlayerId AND AssistedShot.Outcome = 'Goal')
GROUP BY Player.Id, Player.Name
ORDER BY Goals DESC, Player.Name
LIMIT 10;

-- name: event_type_counts | Number of recorded events per type (aggregation)
SELECT EventType, COUNT(*) AS Events
FROM MatchEvent
GROUP BY EventType
ORDER BY Events DESC;
