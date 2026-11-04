"""Fetch the StatsBomb Open Data files used by the project into data/raw/.

Only the 34 Leverkusen 2023/24 matches are needed:
  data/raw/matches/281.json
  data/raw/events/<match_id>.json
  data/raw/lineups/<match_id>.json

Usage:  python main.py download [--source-dir PATH_TO_LOCAL_open-data/data]
"""
import json
import shutil
import urllib.request
from pathlib import Path

from src.cmn.config import COMPETITION_ID, DATA_RAW, SEASON_ID, STATSBOMB_RAW_URL


def _fetch(rel: str, dest: Path, source_dir: Path | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source_dir:                                  # local clone of statsbomb/open-data
        shutil.copyfile(source_dir / rel, dest)
    else:
        urllib.request.urlretrieve(f"{STATSBOMB_RAW_URL}/{rel}", dest)


def download(source_dir: Path | None = None, raw_dir: Path = DATA_RAW) -> int:
    match_rel = f"matches/{COMPETITION_ID}/{SEASON_ID}.json"
    match_file = raw_dir / "matches" / f"{SEASON_ID}.json"
    _fetch(match_rel, match_file, source_dir)
    ids = [m["match_id"] for m in json.loads(match_file.read_text(encoding="utf-8"))]
    for mid in ids:
        for kind in ("events", "lineups"):
            dest = raw_dir / kind / f"{mid}.json"
            if not dest.exists():
                _fetch(f"{kind}/{mid}.json", dest, source_dir)
    return len(ids)
