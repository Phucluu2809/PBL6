"""Run V4 on an existing recording without starting a hardware session."""

import argparse
import csv
import json
from pathlib import Path

from models_v4 import coffee


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="task", required=True)
    coffee_parser = commands.add_parser("coffee")
    coffee_parser.add_argument("raw", type=Path)
    identity_parser = commands.add_parser("identity")
    identity_parser.add_argument("reference_id")
    identity_parser.add_argument("candidate_ids", nargs="+")
    identity_parser.add_argument("--sample-root", type=Path, default=Path("data/hardware"))
    identity_parser.add_argument("--model-dir", type=Path, default=Path("models/rescnn64/20261119_053351_6b8717"))
    args = parser.parse_args()
    if args.task == "coffee":
        with args.raw.open(encoding="utf-8-sig", newline="") as handle:
            result = coffee.predict_trial(csv.DictReader(handle, strict=True))
    else:
        from models_v4.identity import compare
        from robonose_s3.rescnn64 import ResCNN64Predictor

        encoder = ResCNN64Predictor(args.model_dir, [args.sample_root])
        result = compare(encoder, args.reference_id, args.candidate_ids)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return int(result["status"] == "UNAVAILABLE")


if __name__ == "__main__":
    raise SystemExit(main())
