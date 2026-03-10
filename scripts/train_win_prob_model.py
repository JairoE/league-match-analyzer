"""Train V1 logistic regression win probability model from exported CSV.

Reads the CSV from scripts/export_training_data.py, encodes features,
fits LogisticRegression, and saves the model to a joblib file for use
by the scoring service.

Usage:
    python scripts/train_win_prob_model.py --input data/training.csv --output data/win_prob_model.joblib
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression

# Ensure app is importable when run from repo root (e.g. make install)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))
from app.services.win_prob_features import FEATURE_ORDER, encode_rank


def _read_training_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read CSV and return (X, y) with feature order and encoded rank."""
    rows: list[list[float]] = []
    labels: list[int] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        missing = [c for c in FEATURE_ORDER if c not in header]
        if missing:
            raise ValueError(f"Missing columns in CSV: {missing}")
        if "win" not in header:
            raise ValueError("CSV must contain 'win' column")
        for row in reader:
            vec = []
            for col in FEATURE_ORDER:
                val = row.get(col, "")
                if col == "average_rank":
                    vec.append(float(encode_rank(val if val else None)))
                else:
                    try:
                        vec.append(float(val) if val != "" else 0.0)
                    except (TypeError, ValueError):
                        vec.append(0.0)
            rows.append(vec)
            try:
                labels.append(int(row.get("win", 0)))
            except (TypeError, ValueError):
                labels.append(0)
    if not rows:
        raise ValueError("No data rows in CSV")
    X = np.array(rows, dtype=np.float64)
    y = np.array(labels, dtype=np.intp)
    return X, y


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train V1 win probability logistic regression model"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/training.csv",
        help="Input CSV path (default: data/training.csv)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/win_prob_model.joblib",
        help="Output joblib path (default: data/win_prob_model.joblib)",
    )
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        print(f"Input file not found: {path}")
        sys.exit(1)

    try:
        X, y = _read_training_csv(path)
    except ValueError as e:
        print(e)
        sys.exit(1)

    model = LogisticRegression(
        max_iter=2000,
        random_state=42,
        class_weight="balanced",
    )
    model.fit(X, y)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out_path)
    print(f"Model saved to {out_path} (n_samples={len(y)}, n_features={X.shape[1]})")


if __name__ == "__main__":
    main()
