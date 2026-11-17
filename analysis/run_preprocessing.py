from __future__ import annotations

import argparse
from pathlib import Path

from preprocessing import run_preprocessing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preprocess RoboNose trials for one date.")
    parser.add_argument("date", help="Data directory name, for example 2026-11-07")
    parser.add_argument("--data-root", type=Path, default=Path(__file__).resolve().parents[1] / "data")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = run_preprocessing(args.data_root / args.date)
    print(output)


if __name__ == "__main__":
    main()
