"""Common configuration shared by every layer (paths, constants)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DATA_RAW = ROOT / "data" / "raw"
DATA_PREPROCESSED = ROOT / "data" / "preprocessed"
SQL_DIR = ROOT / "src" / "dal" / "models" / "relational" / "sql"

DB_PATH = DATA_PREPROCESSED / "leverkusen.db"
SAMPLE_DB_PATH = DATA_PREPROCESSED / "sample.db"

COMPETITION_ID = 9      # 1. Bundesliga
SEASON_ID = 281         # 2023/2024

STATSBOMB_RAW_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

# --- Semantic Web (Milestone 5) ------------------------------------------------
import os

SEMANTIC_DIR = ROOT / "src" / "dal" / "models" / "semantic"
ONTOLOGY_PATH = SEMANTIC_DIR / "leverkusen.owl"          # TBox (RDF/XML)
KG_SAMPLE_PATH = SEMANTIC_DIR / "leverkusen_kg.rdf"      # ABox, committed sample (RDF/XML)
KG_FULL_PATH = DATA_PREPROCESSED / "leverkusen_kg_full.rdf"   # ABox, all 137k events (generated)

# Ontology namespace (terms and individuals) and the named graph in the triple store
ONTOLOGY_IRI = "https://github.com/MeetShah9/CSC-501-Team-Project/leverkusen"
NS = ONTOLOGY_IRI + "#"
GRAPH_IRI = ONTOLOGY_IRI + "/"

# Match used for the illustrative example; all of its events go into the sample KG
SHOWCASE_SB_MATCH_ID = 3895302      # Leverkusen v Werder Bremen, 14 Apr 2024

# Triple store: "virtuoso" (default, server-based) or "local" (embedded rdflib store,
# no server needed; used for tests and when Virtuoso is not installed).
KG_BACKEND = os.environ.get("KG_BACKEND", "virtuoso")
VIRTUOSO_ENDPOINT = os.environ.get("VIRTUOSO_ENDPOINT", "http://localhost:8890/sparql")
