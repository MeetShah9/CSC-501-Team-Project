# Beyond the Scoresheet – Bayer Leverkusen 2023/24 (Relational implementation)

CSC 501, Milestone 4 – Part I: Relational. Team: Meet Hemang Shah, Sakshi Pinkeshkumar Patel, Ayush Bharatbhai Patel.

## 1. Intro
A relational database (SQLite) that links matches, teams, players, squads (lineups) and 137k timestamped match events of
all 34 Bundesliga games of Bayer 04 Leverkusen's 2023/24 season, built from StatsBomb Open Data. The model keeps the
*recorded* player–event links explicit: **performed by**, **intended for** (the pass's named target, not a guaranteed
receipt) and **assists** (pass → shot). A small Flask web app demonstrates insert, retrieve, update and delete.

ER diagram → relational schema: `Team`, `Player`, `Match`, `MatchTeam` (plays in), `AppearsFor` (ternary), `MatchEvent`
(self-reference for *assists*). See `doc/relational_schema.png` and `src/dal/models/relational/sql/01_schema.sql`.

| Layer | Folder | Role |
|---|---|---|
| UI | `src/ui` | Flask pages/forms (search, add, edit, delete) |
| Business | `src/biz` | download, ETL (JSON → rows), validation (`services.py`), demo runner |
| Data | `src/dal` | connection (FK enforcement), parameterised SQL, SQL scripts |

Architecture diagram: `doc/architecture.png`. UI screenshots: `doc/screenshots/`.

## 2. Illustrative sample
Leverkusen v Werder Bremen, 14 Apr 2024: Andrich's pass at 67:22 names Wirtz and assists Wirtz's goal at 67:25:

```
Passer | IntendedFor | PassTime | Shooter | ShotTime | ShotOutcome
Robert Andrich | Florian Wirtz | 67:22 | Florian Wirtz | 67:25 | Goal
```

## 3. Prerequisites
Python ≥ 3.10 (SQLite ≥ 3.35 is bundled with Python) and Flask (`requirements.txt`). No database server is needed.

## 4. Installation
```
git clone https://github.com/MeetShah9/CSC-501-Team-Project && cd CSC-501-Team-Project
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
The raw StatsBomb files (≈115 MB) are included in `data/raw/`. To re-fetch them: `python main.py download`.

## 5. Quickstart
```
python main.py build     # creates data/preprocessed/leverkusen.db from scratch (≈5 s) and loads all data
python main.py demo      # runs the SQL scripts 02/03/04 and prints results
python main.py ui        # http://127.0.0.1:5000
python main.py all       # build + demo + ui
```
Expected load: Team 18, Player 460, Match 34, MatchTeam 68, AppearsFor 1353, MatchEvent 137,257 (690 pass→shot links).

Pure-SQL route (any SQLite client): run `01_schema.sql`, then `02_sample_insert.sql` on a fresh DB; run `03`/`04` on the
database produced by `python main.py build`.

| Script (`src/dal/models/relational/sql/`) | Content |
|---|---|
| `01_schema.sql` | DDL: tables, PK/UK/FK, CHECKs, triggers, indexes |
| `02_sample_insert.sql` | INSERT with find-or-create pattern (report's goal chain) |
| `03_select_queries.sql` | 9 SELECTs: joins, self-join, aggregation, HAVING, IN, NOT EXISTS |
| `04_update_delete.sql` | UPDATE/DELETE and rejected statements (FK, UNIQUE, CHECK, trigger) |

## Modelling notes / assumptions
- Only player-attributed events are stored (508 events without a player, e.g. *Starting XI*, *Half Start*, are skipped).
- A Pass with no outcome in StatsBomb is a completed pass → stored as `Complete`.
- `Match plays-in` cardinality 2..2 is enforced by `UK_MatchTeam_MatchId_HomeOrAway` plus the loader (no declarative "exactly 2").
- Own goals are separate StatsBomb events (`Own Goal For/Against`), so goals via `Shot`/`Goal` match the official score in 31 of 34 matches; the other 3 differ by one own goal each.
- Missing pass–shot links stay NULL and are never inferred.

## 6. Citation
StatsBomb Open Data, https://github.com/statsbomb/open-data (competition 9, season 281). Please cite this repository
and StatsBomb when reusing the code or data.

## 7. License
Code: MIT (`LICENSE`). Data: StatsBomb Open Data terms (attribution required).

