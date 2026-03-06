from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

ACCOUNT_BY_RIOT_ID_URL = "https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
SUMMONER_BY_PUUID_URL = "https://na1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/"
MATCH_IDS_BY_PUUID_URL = "https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/"
MATCH_DETAIL_URL = "https://americas.api.riotgames.com/lol/match/v5/matches/"
MATCH_TIMELINE_URL = "https://americas.api.riotgames.com/lol/match/v5/matches/"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _get(path: str, headers: dict[str, str]) -> Any:
    response = httpx.get(path, headers=headers, timeout=20.0)
    response.raise_for_status()
    return response.json()


def _trim_timeline(timeline: dict[str, Any], max_frames: int) -> dict[str, Any]:
    """Keep only the first *max_frames* frames and strip events (tests only use participantFrames)."""
    info = timeline.get("info")
    if not isinstance(info, dict):
        return timeline
    frames = info.get("frames")
    if isinstance(frames, list):
        info["frames"] = [
            {"participantFrames": f.get("participantFrames", {}), "timestamp": f.get("timestamp", 0)}
            for f in frames[:max_frames]
        ]
    return timeline


def _sanitize_identifier(raw: str) -> str:
    return raw.lower().replace("#", "_").replace("/", "_").replace(":", "_")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture live Riot payloads for backend test fixtures.")
    parser.add_argument("--game-name", default="damanjr", help="Riot game name.")
    parser.add_argument("--tag-line", default="NA1", help="Riot tag line.")
    parser.add_argument(
        "--count",
        type=int,
        default=30,
        help="Number of match IDs to request from Riot API.",
    )
    parser.add_argument(
        "--match-id",
        default=None,
        help="Specific Riot match ID for match detail/timeline fixture. Defaults to first returned ID.",
    )
    parser.add_argument(
        "--timeline-frames",
        type=int,
        default=16,
        help="Max frames to keep in the timeline fixture (0 = all). 16 covers laning phase (0-15 min).",
    )
    parser.add_argument(
        "--out-dir",
        default="services/api/tests/fixtures/riot",
        help="Directory to write fixture JSON files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.getenv("RIOT_API_KEY")
    if not api_key or api_key == "replace-me":
        raise SystemExit("RIOT_API_KEY is missing. Export it before running capture script.")

    out_dir = Path(args.out_dir)
    headers = {"X-Riot-Token": api_key}

    account_url = ACCOUNT_BY_RIOT_ID_URL + f"{quote(args.game_name)}/{quote(args.tag_line)}"
    account_info = _get(account_url, headers)
    puuid = str(account_info["puuid"])

    summoner_url = SUMMONER_BY_PUUID_URL + quote(puuid)
    summoner_info = _get(summoner_url, headers)

    match_ids_url = (
        MATCH_IDS_BY_PUUID_URL + quote(puuid) + f"/ids?start=0&count={int(args.count)}"
    )
    match_ids = _get(match_ids_url, headers)
    if not isinstance(match_ids, list):
        raise SystemExit("Riot match IDs payload is not a list.")
    if not match_ids and args.match_id is None:
        raise SystemExit("No match IDs returned and no --match-id override provided.")

    selected_match_id = str(args.match_id or match_ids[0])
    match_detail_url = MATCH_DETAIL_URL + quote(selected_match_id)
    match_detail = _get(match_detail_url, headers)
    match_timeline_url = MATCH_TIMELINE_URL + quote(selected_match_id) + "/timeline"
    match_timeline = _get(match_timeline_url, headers)

    riot_id_slug = _sanitize_identifier(f"{args.game_name}#{args.tag_line}")
    puuid_slug = _sanitize_identifier(puuid)
    match_id_slug = _sanitize_identifier(selected_match_id)

    account_filename = f"account_info.{riot_id_slug}.json"
    summoner_filename = f"summoner_info.{puuid_slug}.json"
    match_ids_filename = f"match_ids.{puuid_slug}.json"
    match_detail_filename = f"match_detail.{match_id_slug}.json"
    match_timeline_filename = f"match_timeline.{match_id_slug}.json"

    if args.timeline_frames and args.timeline_frames > 0:
        match_timeline = _trim_timeline(match_timeline, args.timeline_frames)

    _write_json(out_dir / account_filename, account_info)
    _write_json(out_dir / summoner_filename, summoner_info)
    _write_json(out_dir / match_ids_filename, match_ids)
    _write_json(out_dir / match_detail_filename, match_detail)
    _write_json(out_dir / match_timeline_filename, match_timeline)

    manifest = {
        "riot_id": f"{args.game_name}#{args.tag_line}",
        "puuid": puuid,
        "primary_match_id": selected_match_id,
        "account_info_file": account_filename,
        "summoner_info_file": summoner_filename,
        "match_ids_file": match_ids_filename,
        "match_detail_file": match_detail_filename,
        "match_timeline_file": match_timeline_filename,
        "match_ids_count": len(match_ids),
    }
    _write_json(out_dir / "manifest.json", manifest)

    print(f"Wrote Riot fixtures to {out_dir}")
    print(f"riot_id={manifest['riot_id']}")
    print(f"puuid={manifest['puuid']}")
    print(f"primary_match_id={manifest['primary_match_id']}")
    print(f"match_ids_count={manifest['match_ids_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
