"""Run the coffee-odor detector on every raw.csv in one dated data folder.

Accuracy is calculated only for manifest rows marked ELIGIBLE with a binary
coffee_on_person_label. Other experiment groups are still scored, but their
results are reported as OUT_OF_SCOPE instead of being counted as correct or
wrong.

Usage:
    python analysis/test_all_coffee_odor.py
    python analysis/test_all_coffee_odor.py data/2026-10-28
    python analysis/test_all_coffee_odor.py --output-dir analysis/results_2026_10_28
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def ensure_dependencies() -> None:
    try:
        import sklearn  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    if candidate.is_file() and Path(sys.executable).resolve() != candidate.resolve():
        completed = subprocess.run(
            [str(candidate), str(Path(__file__).resolve()), *sys.argv[1:]],
            check=False,
        )
        raise SystemExit(completed.returncode)
    raise ModuleNotFoundError("Thiếu scikit-learn và không tìm thấy .venv")


ensure_dependencies()

import check_coffee_odor as detector


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


DEFAULT_DATE_ROOT = ROOT / "data" / "2026-10-28"
DECISIVE = {"COFFEE_ODOR_LIKELY", "NO_COFFEE_ODOR_LIKELY"}
ABSTAINED = {"UNCERTAIN", "OUT_OF_DOMAIN", "INVALID_MEASUREMENT"}


def parse_label(value: object) -> int | None:
    text = str(value).strip()
    return int(text) if text in {"0", "1"} else None


def load_manifest(date_root: Path) -> list[dict[str, str]]:
    path = date_root / "label_manifest.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy manifest: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def evaluate_result(prediction: str, label: int | None, eligible: bool) -> str:
    if not eligible or label is None:
        return "OUT_OF_SCOPE"
    if prediction in ABSTAINED:
        return "ABSTAIN"
    predicted_label = int(prediction == "COFFEE_ODOR_LIKELY")
    return "CORRECT" if predicted_label == label else "WRONG"


def run_all(date_root: Path) -> dict[str, object]:
    rows = []
    manifest = load_manifest(date_root)
    manifest_folders = {row["folder"] for row in manifest}
    raw_folders = {
        path.parent.name for path in date_root.rglob("raw.csv") if path.is_file()
    }
    missing_raw = sorted(manifest_folders - raw_folders)
    unlisted_raw = sorted(raw_folders - manifest_folders)

    for manifest_row in manifest:
        folder = manifest_row["folder"]
        raw_path = date_root / folder / "raw.csv"
        label = parse_label(manifest_row.get("coffee_on_person_label"))
        eligible = manifest_row.get("binary_use") == "ELIGIBLE" and label is not None
        if not raw_path.is_file():
            rows.append(
                {
                    "session_no": manifest_row.get("session_no"),
                    "folder": folder,
                    "experiment_group": manifest_row.get("experiment_group"),
                    "binary_use": manifest_row.get("binary_use"),
                    "qc_status": manifest_row.get("qc_status"),
                    "true_label": label,
                    "prediction": "MISSING_RAW",
                    "evaluation": "ABSTAIN" if eligible else "OUT_OF_SCOPE",
                    "decision_score": None,
                    "focused_score": None,
                    "out_of_distribution": None,
                    "error": "Không tìm thấy raw.csv",
                }
            )
            continue
        try:
            result = detector.predict(raw_path, detector.DATA_ROOT)
            prediction = str(result["prediction"])
            rows.append(
                {
                    "session_no": int(manifest_row["session_no"]),
                    "folder": folder,
                    "experiment_group": manifest_row.get("experiment_group"),
                    "binary_use": manifest_row.get("binary_use"),
                    "qc_status": manifest_row.get("qc_status"),
                    "true_label": label,
                    "prediction": prediction,
                    "evaluation": evaluate_result(prediction, label, eligible),
                    "decision_score": result.get("decision_score"),
                    "focused_score": result.get("focused_mq135_mq3_score"),
                    "out_of_distribution": result.get("out_of_distribution"),
                    "quality_pass": result.get("quality", {}).get("passed"),
                    "quality_errors": result.get("quality", {}).get("errors", []),
                    "model_version": result.get("model_version"),
                    "feature_version": result.get("feature_version"),
                    "training_manifest_hash": result.get("training_manifest_hash"),
                    "error": None,
                }
            )
        except (FileNotFoundError, ValueError, KeyError, csv.Error) as error:
            rows.append(
                {
                    "session_no": int(manifest_row["session_no"]),
                    "folder": folder,
                    "experiment_group": manifest_row.get("experiment_group"),
                    "binary_use": manifest_row.get("binary_use"),
                    "qc_status": manifest_row.get("qc_status"),
                    "true_label": label,
                    "prediction": "ERROR",
                    "evaluation": "ABSTAIN" if eligible else "OUT_OF_SCOPE",
                    "decision_score": None,
                    "focused_score": None,
                    "out_of_distribution": None,
                    "error": str(error),
                }
            )

    eligible_rows = [
        row for row in rows if row["binary_use"] == "ELIGIBLE" and row["true_label"] in {0, 1}
    ]
    decisive_rows = [row for row in eligible_rows if row["prediction"] in DECISIVE]
    correct = sum(row["evaluation"] == "CORRECT" for row in eligible_rows)
    wrong = sum(row["evaluation"] == "WRONG" for row in eligible_rows)
    abstained = len(eligible_rows) - correct - wrong
    positive_rows = [row for row in eligible_rows if row["true_label"] == 1]
    negative_rows = [row for row in eligible_rows if row["true_label"] == 0]
    true_positive = sum(
        row["prediction"] == "COFFEE_ODOR_LIKELY" for row in positive_rows
    )
    false_negative = sum(
        row["prediction"] == "NO_COFFEE_ODOR_LIKELY" for row in positive_rows
    )
    false_positive = sum(
        row["prediction"] == "COFFEE_ODOR_LIKELY" for row in negative_rows
    )
    summary = {
        "manifest_sessions": len(manifest),
        "raw_files": len(raw_folders),
        "eligible_sessions": len(eligible_rows),
        "out_of_scope_sessions": len(rows) - len(eligible_rows),
        "decisive": len(decisive_rows),
        "correct": correct,
        "wrong": wrong,
        "abstained": abstained,
        "coverage": len(decisive_rows) / len(eligible_rows) if eligible_rows else None,
        "accuracy_when_decisive": correct / len(decisive_rows) if decisive_rows else None,
        "correct_over_all_eligible": correct / len(eligible_rows) if eligible_rows else None,
        "positive_total": len(positive_rows),
        "positive_detected": true_positive,
        "positive_missed_as_no_coffee": false_negative,
        "positive_abstained": len(positive_rows) - true_positive - false_negative,
        "negative_total": len(negative_rows),
        "negative_false_positive": false_positive,
        "missing_raw": missing_raw,
        "unlisted_raw": unlisted_raw,
    }
    return {"date_root": str(date_root.resolve()), "summary": summary, "rows": rows}


def format_score(value: object) -> str:
    return "-" if value is None else f"{float(value):+.3f}"


def print_report(report: dict[str, object]) -> None:
    summary = report["summary"]
    print("=" * 118)
    print("BATCH TEST COFFEE ODOR – TẤT CẢ MẪU 2026-10-28")
    print("=" * 118)
    print("STT | Nhãn | Main   | MQ     | Kết quả                  | Đánh giá     | Nhóm          | Folder")
    for row in report["rows"]:
        label = "-" if row["true_label"] is None else str(row["true_label"])
        print(
            f"{int(row['session_no']):>3} | {label:^4} | "
            f"{format_score(row['decision_score']):>6} | "
            f"{format_score(row['focused_score']):>6} | "
            f"{str(row['prediction']):<24} | "
            f"{str(row['evaluation']):<12} | "
            f"{str(row['experiment_group']):<13} | {row['folder']}"
        )
    print("\nTHỐNG KÊ CHỈ TRÊN CÁC MẪU ELIGIBLE CÓ NHÃN 0/1")
    print(
        f"  Tổng {summary['eligible_sessions']}; kết luận {summary['decisive']}; "
        f"đúng {summary['correct']}; sai {summary['wrong']}; "
        f"từ chối {summary['abstained']}"
    )
    print(
        f"  Coverage: {summary['coverage']:.1%}; "
        f"accuracy khi có kết luận: {summary['accuracy_when_decisive']:.1%}; "
        f"đúng trên toàn bộ eligible: {summary['correct_over_all_eligible']:.1%}"
    )
    print(
        f"  Có cà phê: phát hiện {summary['positive_detected']}/{summary['positive_total']}; "
        f"kết luận nhầm KHÔNG {summary['positive_missed_as_no_coffee']}; "
        f"từ chối {summary['positive_abstained']}"
    )
    print(
        f"  Không cà phê: {summary['negative_false_positive']} false positive / "
        f"{summary['negative_total']} mẫu"
    )
    print(
        f"  Ngoài phạm vi accuracy: {summary['out_of_scope_sessions']} phiên "
        "air/coffee-only/paired"
    )


def write_outputs(report: dict[str, object], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "coffee_odor_batch_results.json"
    csv_path = output_dir / "coffee_odor_batch_results.csv"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    columns = [
        "session_no",
        "folder",
        "experiment_group",
        "binary_use",
        "qc_status",
        "true_label",
        "prediction",
        "evaluation",
        "decision_score",
        "focused_score",
        "out_of_distribution",
        "quality_pass",
        "model_version",
        "feature_version",
        "training_manifest_hash",
        "error",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["rows"])
    return csv_path, json_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test detector trên mọi raw.csv trong một thư mục ngày."
    )
    parser.add_argument("date_root", nargs="?", type=Path, default=DEFAULT_DATE_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Mặc định: <date_root>/coffee_odor_batch_test",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date_root = args.date_root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else date_root / "coffee_odor_batch_test"
    )
    try:
        report = run_all(date_root)
        print_report(report)
        csv_path, json_path = write_outputs(report, output_dir)
        print(f"\nĐã ghi CSV : {csv_path}")
        print(f"Đã ghi JSON: {json_path}")
        return 0
    except (FileNotFoundError, ValueError, KeyError, csv.Error) as error:
        print(f"LỖI: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
