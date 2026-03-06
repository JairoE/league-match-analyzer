from __future__ import annotations

import json
from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent / "riot"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


@cache
def _read_json_cached(path: Path) -> Any:
    """Read and cache JSON from disk. Callers must deepcopy mutable results."""
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_meta() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Missing Riot fixture manifest: {MANIFEST_PATH}. "
            "Run scripts/capture_riot_test_fixtures.py first."
        )
    return deepcopy(_read_json_cached(MANIFEST_PATH))


def _fixture_path(manifest_key: str) -> Path:
    meta = fixture_meta()
    filename = str(meta[manifest_key])
    return FIXTURE_DIR / filename


def load_account_info() -> dict[str, Any]:
    return deepcopy(_read_json_cached(_fixture_path("account_info_file")))


def load_summoner_info() -> dict[str, Any]:
    return deepcopy(_read_json_cached(_fixture_path("summoner_info_file")))


def load_match_ids() -> list[str]:
    payload = _read_json_cached(_fixture_path("match_ids_file"))
    if not isinstance(payload, list):
        raise TypeError("match_ids fixture must be a list.")
    return [str(item) for item in payload]


def load_match_detail() -> dict[str, Any]:
    return deepcopy(_read_json_cached(_fixture_path("match_detail_file")))


def load_match_timeline() -> dict[str, Any]:
    return deepcopy(_read_json_cached(_fixture_path("match_timeline_file")))
