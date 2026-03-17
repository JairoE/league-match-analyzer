"""Print a mapping of Riot champion IDs to names using Data Dragon.

Usage:
    python scripts/print_champion_ids.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

_api_root = Path(__file__).resolve().parents[1] / "services" / "api"
sys.path.insert(0, str(_api_root))

from app.services.ddragon_client import DdragonClient


async def _run() -> None:
    client = DdragonClient()
    champions: list[dict[str, Any]] = await client.fetch_champion_catalog()
    mapping = {c["champ_id"]: c["name"] for c in champions}
    print(json.dumps(mapping, indent=2, sort_keys=True))


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

