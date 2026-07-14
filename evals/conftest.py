"""Path + env setup for the eval harness (mirrors scripts/ conventions)."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

_api_root = Path(__file__).resolve().parents[1] / "services" / "api"
if str(_api_root) not in sys.path:
    sys.path.insert(0, str(_api_root))

load_dotenv(_api_root / ".env")
