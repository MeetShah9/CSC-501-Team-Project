# Beyond the Scoresheet – Bayer Leverkusen 2023/24

CSC 501 team project. Team: Meet Hemang Shah, Sakshi Pinkeshkumar Patel, Ayush Bharatbhai Patel.

The same real-world domain, every Bundesliga match of Bayer 04 Leverkusen's 2023/24 season from StatsBomb Open
Data, represented two ways:

| Milestone | Representation | Store | Where |
|---|---|---|---|
| 4 – Part I: Relational | ER → relational schema → SQL | SQLite | `src/dal/models/relational/`, [Relational](#relational-implementation-milestone-4) |
| 5 – Part II: Semantic Web | ER → RDFS/OWL ontology → RDF knowledge graph → SPARQL | Virtuoso 7 (or embedded rdflib) | `src/dal/models/semantic/`, [Semantic Web](#semantic-web-implementation-milestone-5) |

---

## Semantic Web implementation (Milestone 5)

### 1. Intro
An OWL 2 ontology (TBox) translated from our ER model, and a knowledge graph (ABox) of individuals for the season,
stored in a Virtuoso triple store as one named graph and queried / modified with SPARQL 1.1. The model keeps the
recorded player–event links explicit: `lev:performedBy`, `lev:intendedFor` (the pass's named target, not a
guaranteed receipt) and `lev:assists` (pass → shot). A Flask web app lets users search, add, update and delete
without writing SPARQL.

| ER / relational | RDFS / OWL 2 (`leverkusen.owl`) |
|---|---|
| entity sets Team, Player, Match, MatchEvent | `owl:Class` `lev:Team`, `lev:Player`, `lev:Match`, `lev:MatchEvent` |
| EventType values | IS-A: 27 disjoint subclasses of `lev:MatchEvent` (`lev:Pass`, `lev:Shot`, …); defined class `lev:Goal ≡ Shot ⊓ (outcome value "Goal")` |
| attributes | `owl:DatatypeProperty` (`lev:name`, `lev:kickOff` xsd:dateTime, `lev:period` xsd:integer[1..5], `lev:second` xsd:integer[0..59], …) |
| relationships contains / performed by / intended for / assists | `owl:ObjectProperty` `lev:inMatch`, `lev:performedBy`, `lev:intendedFor`, `lev:assists` (+ inverses) |
| plays in (M:N) + attribute HomeOrAway | `lev:homeTeam`, `lev:awayTeam` ⊑ `lev:hasTeam`; restrictions =1, =1 and =2 |
| ternary appears for (table AppearsFor) | association class `lev:Appearance` with `appearanceOf` / `appearanceFor` / `appearanceIn` (=1 each) |
| cardinalities, NOT NULL | `owl:qualifiedCardinality`, `owl:maxQualifiedCardinality`, `owl:FunctionalProperty`, `owl:InverseFunctionalProperty` |
| PK / UNIQUE | `owl:hasKey` (sbTeamId, sbPlayerId, sbMatchId, sbEventUuid, (appearanceIn, appearanceOf)) |
| FK, CHECK, trigger | `rdfs:domain` / `rdfs:range`, datatype restrictions; checked by `04_integrity_checks.sparql` and the business layer (Open World Assumption, see below) |

| Layer | Folder | Role |
|---|---|---|
| UI | `src/ui/kg_app.py`, `templates/kg_*.html` | Flask pages and forms (search, add, edit, delete, queries, checks) |
| Business | `src/biz/kg_*.py` | ontology builder, JSON → RDF ETL, validation and integrity rules, demo runner, reasoner check |
| Data | `src/dal/kg_*.py`, `src/dal/models/semantic/` | triple-store driver (Virtuoso over HTTP, or embedded), SPARQL statements, `.owl` / `.rdf` / `.sparql` files |

Architecture: `doc/architecture_semantic.png`. Ontology diagram: `doc/ontology.png`. Screenshots: `doc/screenshots/kg_*.png`.
Report (ACM sigconf, LaTeX + PDF): `doc/report/`.

**Open World Assumption.** The ontology states cardinalities, keys and ranges, but a triple store does not reject
data that breaks them (a missing triple means "unknown", not "error"). So `src/biz/kg_services.py` validates every
change before it is sent, deletes are guarded in their `WHERE` clause (the SPARQL analogue of `ON DELETE RESTRICT`),
and `04_integrity_checks.sparql` checks the stored data. `python main.py kg-check --reasoner` also runs the OWL 2
reasoner HermiT: the ontology plus data is consistent, and a period of 7, a second performer for one event, or two
periods for one event each make it inconsistent.

### 2. Illustrative sample
Leverkusen v Werder Bremen, 14 Apr 2024: Andrich's pass at 67:22 names Wirtz and assists Wirtz's goal at 67:25.

```turtle
lev:event_4c9d47f0-… a lev:Pass ; lev:performedBy lev:player_9195 ; lev:intendedFor lev:player_40724 ;
    lev:assists lev:event_5085715b-… ; lev:inMatch lev:match_3895302 ; lev:minute 67 ; lev:second 22 .
lev:event_5085715b-… a lev:Shot , lev:Goal ; lev:performedBy lev:player_40724 ; lev:outcome "Goal" .
```
```
passer         | intendedFor   | passTime | shooter       | shotTime | shotOutcome
Robert Andrich | Florian Wirtz | 67:22    | Florian Wirtz | 67:25    | Goal
```

### 3. Prerequisites
- Python ≥ 3.10 with `Flask` and `rdflib` (`requirements.txt`).
- A triple store: **Virtuoso Open Source 7** (https://github.com/openlink/virtuoso-opensource), installed locally or
  run with Docker. Without it, everything also runs on the embedded rdflib store (`KG_BACKEND=local`).
- Optional: Protégé (https://protege.stanford.edu) to open and edit `leverkusen.owl`; Java + `owlready2` for
  `kg-check --reasoner`.

### 4. Installation
```
git clone https://github.com/MeetShah9/CSC-501-Team-Project && cd "CSC-501-Team-Project/Project Implementation"
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Virtuoso** (one of):
- Docker: `docker run -d --name csc501-virtuoso -p 8890:8890 -p 1111:1111 -e DBA_PASSWORD=dba openlink/virtuoso-opensource-7:latest`
- Binary / installer from the Virtuoso GitHub releases page. On macOS/Linux, start it with
  `cd <virtuoso>/database && ../bin/virtuoso-t -f -c virtuoso.ini` (keep it running).

Then open Conductor at http://localhost:8890/conductor (user `dba`, password `dba`) and give the web endpoint write
access (manual 5.2.3): **System Admin → User Accounts → Users → SPARQL → Edit**, tick *User enabled*, add roles
`SPARQL_SELECT` and `SPARQL_UPDATE`, save. Same thing from isql:
`isql 1111 dba dba exec="GRANT SPARQL_UPDATE TO \"SPARQL\"; DB.DBA.RDF_DEFAULT_USER_PERMS_SET ('nobody', 7);"`

### 5. Quickstart
One command (creates the venv, builds the files, finds or starts Virtuoso, falls back to the embedded store,
loads the graph, runs the demo, starts the UI):
```
bash scripts/quickstart_semantic.sh          # Windows: .\scripts\quickstart_semantic.ps1
```
Step by step:
```
python main.py kg-ontology      # src/dal/models/semantic/leverkusen.owl      (TBox, 504 triples)
python main.py kg-build         # src/dal/models/semantic/leverkusen_kg.rdf   (ABox sample, 53,100 triples)
python main.py kg-load          # both into named graph <https://github.com/MeetShah9/CSC-501-Team-Project/leverkusen/>
python main.py kg-demo          # runs the SPARQL scripts 01-04 and prints the results
python main.py kg-check         # integrity ASK checks (add --reasoner for HermiT)
python main.py kg-ui            # http://127.0.0.1:5001
KG_BACKEND=local python main.py kg-ui        # same UI on the embedded store, no server
```
Expected after `kg-load`: 53,604 triples (Team 18, Player 460, Match 34, Appearance 1,353, MatchEvent 5,770 of which
916 Shot / 110 Goal, 690 `assists` links).

**Sample vs full graph.** The committed sample has every team, player, match, appearance and shot, every pass that
assists a shot, and all 4,209 player events of match 3895302, so every season-level goal / assist query is complete.
`python main.py kg-build --full && python main.py kg-load --full` builds and loads all 137,257 events
(1,055,798 triples, ~120 MB, not committed); on it every SPARQL query returns the same answer as its SQL twin.
For the full file, Virtuoso's bulk loader is faster than HTTP: copy the file into a folder listed in `DirsAllowed`
(virtuoso.ini), then in isql: `ld_dir('<folder>', 'leverkusen_kg_full.rdf', 'https://github.com/MeetShah9/CSC-501-Team-Project/leverkusen/'); rdf_loader_run(); checkpoint;`

**Manual route (Conductor, as in the course manual).** Linked Data → Quad Store Upload: upload `leverkusen.owl`, then
`leverkusen_kg.rdf`, both into the named graph IRI above. Linked Data → Graphs lists it. Paste any block of the
`.sparql` files into Linked Data → SPARQL (or http://localhost:8890/sparql); each block is self-contained.

| Script (`src/dal/models/semantic/`) | Content |
|---|---|
| `leverkusen.owl` | ontology (TBox), RDF/XML, opens in Protégé |
| `leverkusen_kg.rdf` | knowledge graph sample (ABox), RDF/XML |
| `00_debug.sparql` | manual Appendix B: list graphs, all triples, class triples, counts |
| `01_insert.sparql` | INSERT DATA (report's goal chain), find-or-create INSERT … WHERE |
| `02_select_queries.sparql` | 14 queries: twins of all 9 SQL queries, datetime search, ASK, CONSTRUCT, DESCRIBE, … |
| `03_update_delete.sparql` | DELETE/INSERT updates, guarded and unguarded deletes, accepted constraint violations |
| `04_integrity_checks.sparql` | 14 ASK checks replacing PK / UNIQUE / FK / CHECK / trigger |

### 6. Citation
StatsBomb Open Data, https://github.com/statsbomb/open-data (competition 9, season 281). Please cite this repository
and StatsBomb when reusing the code, ontology or data.

### 7. License
Code and ontology: MIT (`LICENSE`). Data: StatsBomb Open Data terms (attribution required).

---

## Relational implementation (Milestone 4)

### 1. Intro
A relational database (SQLite) that links matches, teams, players, squads (lineups) and 137k timestamped match events of
all 34 Bundesliga games of Bayer 04 Leverkusen's 2023/24 season, built from StatsBomb Open Data. A small Flask web app
demonstrates insert, retrieve, update and delete.

ER diagram → relational schema: `Team`, `Player`, `Match`, `MatchTeam` (plays in), `AppearsFor` (ternary), `MatchEvent`
(self-reference for *assists*). See `doc/relational_schema.png` and `src/dal/models/relational/sql/01_schema.sql`.

| Layer | Folder | Role |
|---|---|---|
| UI | `src/ui` | Flask pages/forms (search, add, edit, delete) |
| Business | `src/biz` | download, ETL (JSON → rows), validation (`services.py`), demo runner |
| Data | `src/dal` | connection (FK enforcement), parameterised SQL, SQL scripts |

Architecture diagram: `doc/architecture.png`. UI screenshots: `doc/screenshots/` (files without the `kg_` prefix).

### 2. Quickstart
```
python main.py build     # creates data/preprocessed/leverkusen.db from scratch (≈5 s) and loads all data
python main.py demo      # runs the SQL scripts 02/03/04 and prints results
python main.py ui        # http://127.0.0.1:5000
python main.py all       # build + demo + ui
```
Expected load: Team 18, Player 460, Match 34, MatchTeam 68, AppearsFor 1353, MatchEvent 137,257 (690 pass→shot links).
The raw StatsBomb files (≈115 MB) are included in `data/raw/`. To re-fetch them: `python main.py download`.

Pure-SQL route (any SQLite client): run `01_schema.sql`, then `02_sample_insert.sql` on a fresh DB; run `03`/`04` on the
database produced by `python main.py build`.

| Script (`src/dal/models/relational/sql/`) | Content |
|---|---|
| `01_schema.sql` | DDL: tables, PK/UK/FK, CHECKs, triggers, indexes |
| `02_sample_insert.sql` | INSERT with find-or-create pattern (report's goal chain) |
| `03_select_queries.sql` | 9 SELECTs: joins, self-join, aggregation, HAVING, IN, NOT EXISTS |
| `04_update_delete.sql` | UPDATE/DELETE and rejected statements (FK, UNIQUE, CHECK, trigger) |

### Modelling notes / assumptions (both representations)
- Only player-attributed events are stored (508 events without a player, e.g. *Starting XI*, *Half Start*, are skipped).
- A Pass with no outcome in StatsBomb is a completed pass → stored as `Complete`.
- Relational: `Match plays-in` cardinality 2..2 is enforced by `UK_MatchTeam_MatchId_HomeOrAway` plus the loader.
  Semantic: stated declaratively (`homeTeam` =1, `awayTeam` =1, `hasTeam` =2) and checked by `match_not_two_teams`.
- Own goals are separate StatsBomb events (`Own Goal For/Against`), so goals via `Shot`/`Goal` match the official score in 31 of 34 matches; the other 3 differ by one own goal each.
- Missing pass–shot links stay NULL / absent and are never inferred.
- `lev:kickOff` is `xsd:dateTime` (date + StatsBomb kick-off time) because `xsd:date` is not in the OWL 2 datatype map
  (reasoners such as HermiT reject it).
