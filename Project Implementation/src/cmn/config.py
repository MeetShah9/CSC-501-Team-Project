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
