"""Win probability scoring service for ΔW computation.

Loads the V1 logistic regression model and scores game state feature dicts
to produce w(x) for use in action delta_w and aggregation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.win_prob_features import FEATURE_ORDER, encode_rank

logger = get_logger("league_api.services.win_prob_scoring")

_loaded_model: Any = None
_loaded_path: str | None = None


def _get_model_path() -> Path | None:
    path_str = get_settings().win_prob_model_path.strip()
    if not path_str:
        return None
    p = Path(path_str)
    if not p.is_absolute():
        # Resolve relative to cwd (worker often runs from repo root)
        p = Path.cwd() / p
    return p if p.exists() else None


def load_model() -> bool:
    """Load the win probability model from disk if path is configured.

    Returns:
        True if a model is loaded, False otherwise.
    """
    global _loaded_model, _loaded_path
    path = _get_model_path()
    if path is None:
        _loaded_model = None
        _loaded_path = None
        return False

    if _loaded_path == str(path):
        return _loaded_model is not None

    try:
        import joblib

        _loaded_model = joblib.load(path)
        _loaded_path = str(path)
        logger.info(
            "win_prob_model_loaded",
            extra={"path": str(path)},
        )
        return True
    except Exception as exc:
        logger.warning(
            "win_prob_model_load_failed",
            extra={"path": str(path), "error_message": str(exc)},
        )
        _loaded_model = None
        _loaded_path = None
        return False


def _features_dict_to_vector(features: dict[str, Any]) -> np.ndarray:
    """Build a feature vector in FEATURE_ORDER from a state features dict."""
    vec: list[float] = []
    for col in FEATURE_ORDER:
        val = features.get(col)
        if col == "average_rank":
            if isinstance(val, (int, float)):
                vec.append(float(val))
            else:
                vec.append(float(encode_rank(str(val) if val is not None else "")))
        else:
            try:
                vec.append(float(val) if val is not None and val != "" else 0.0)
            except (TypeError, ValueError):
                vec.append(0.0)
    return np.array([vec], dtype=np.float64)


def score_state(features: dict[str, Any]) -> float | None:
    """Score a game state to get win probability w(x) for team 100 (blue).

    Args:
        features: State feature dict (e.g. MatchStateVector.features).

    Returns:
        P(win) in [0, 1], or None if model is not loaded.
    """
    if _loaded_model is None and not load_model():
        return None
    if _loaded_model is None:
        return None
    X = _features_dict_to_vector(features)
    proba = _loaded_model.predict_proba(X)
    # predict_proba returns [P(class 0), P(class 1)]; class 1 = win
    return float(proba[0, 1])
