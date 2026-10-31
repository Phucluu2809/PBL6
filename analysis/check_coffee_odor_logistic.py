"""Independent Logistic Regression baseline for coffee-odor detection.

This script reuses the validated 25-feature extractor from
``check_coffee_odor.py`` but does not modify the existing RBF-SVM detector.

Examples:
    python analysis/check_coffee_odor_logistic.py path/to/raw.csv
    python analysis/check_coffee_odor_logistic.py --self-test
    python analysis/check_coffee_odor_logistic.py --batch
    python analysis/check_coffee_odor_logistic.py --batch data/2026-10-28
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

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import check_coffee_odor as feature_pipeline


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


MODEL_VERSION = "coffee-logistic-l2-v1"
DEFAULT_DATE_ROOT = ROOT / "data" / "2026-10-28"
DEFAULT_NEGATIVE_THRESHOLD = 0.35
DEFAULT_POSITIVE_THRESHOLD = 0.65
LOGISTIC_C = 1.0


def build_model() -> Pipeline:
    return Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "logistic",
                LogisticRegression(
                    C=LOGISTIC_C,
                    solver="lbfgs",
                    class_weight="balanced",
                    max_iter=5000,
                    random_state=42,
                ),
            ),
        ]
    )


def classify_probability(
    probability: float,
    out_of_distribution: bool,
    negative_threshold: float,
    positive_threshold: float,
) -> tuple[str, str]:
    if out_of_distribution:
        return "OUT_OF_DOMAIN", "Mẫu nằm ngoài miền dữ liệu đã học"
    if probability >= positive_threshold:
        return "COFFEE_ODOR_LIKELY", "Có khả năng có mùi cà phê"
    if probability <= negative_threshold:
        return "NO_COFFEE_ODOR_LIKELY", "Có khả năng không có mùi cà phê"
    return "UNCERTAIN", "Chưa thể kết luận"


def known_training_row(raw_path: Path, data_root: Path) -> dict[str, object] | None:
    resolved = raw_path.resolve()
    rows = {
        (Path(row["directory"]) / "raw.csv").resolve(): row
        for row in feature_pipeline.discover_training_rows(data_root)
    }
    return rows.get(resolved)


def feature_explanations(
    model: Pipeline, x_input: np.ndarray
) -> list[dict[str, object]]:
    scaler: StandardScaler = model.named_steps["scale"]
    logistic: LogisticRegression = model.named_steps["logistic"]
    standardized = scaler.transform(x_input)[0]
    coefficients = logistic.coef_[0]
    rows = []
    for index, name in enumerate(feature_pipeline.FEATURE_NAMES):
        contribution = float(standardized[index] * coefficients[index])
        rows.append(
            {
                "feature": name,
                "feature_label": feature_pipeline.feature_label(name),
                "value": float(x_input[0, index]),
                "standardized_value": float(standardized[index]),
                "coefficient": float(coefficients[index]),
                "log_odds_contribution": contribution,
                "supports_coffee": contribution > 0,
            }
        )
    rows.sort(key=lambda row: abs(float(row["log_odds_contribution"])), reverse=True)
    return rows


def predict(
    raw_path: Path,
    data_root: Path,
    negative_threshold: float = DEFAULT_NEGATIVE_THRESHOLD,
    positive_threshold: float = DEFAULT_POSITIVE_THRESHOLD,
) -> dict[str, object]:
    raw_path = raw_path.resolve()
    known_row = known_training_row(raw_path, data_root)
    known_label = int(known_row["label"]) if known_row is not None else None
    extracted = feature_pipeline.extract_features(raw_path)
    quality = extracted["quality"]
    if not quality["passed"]:
        return {
            "input_file": str(raw_path),
            "prediction": "INVALID_MEASUREMENT",
            "prediction_vi": "Dữ liệu đo chưa đủ chất lượng để phân loại",
            "coffee_probability": None,
            "known_ground_truth": known_label,
            "evaluation_against_label": "INVALID",
            "quality": quality,
            "warnings": extracted["warnings"],
            "model_version": MODEL_VERSION,
            "feature_version": feature_pipeline.FEATURE_VERSION,
        }

    sessions, skipped = feature_pipeline.load_training_sessions(
        data_root,
        excluded_raw=raw_path if known_row is not None else None,
    )
    x_train = feature_pipeline.feature_matrix(sessions)
    y_train = np.asarray([int(session["label"]) for session in sessions])
    x_input = np.asarray(
        [[float(extracted["features"][name]) for name in feature_pipeline.FEATURE_NAMES]],
        dtype=float,
    )
    model = build_model()
    model.fit(x_train, y_train)
    probability = float(model.predict_proba(x_input)[0, 1])
    domain = feature_pipeline.domain_diagnostics(model, x_train, x_input)[0]
    prediction, prediction_vi = classify_probability(
        probability,
        bool(domain["out_of_distribution"]),
        negative_threshold,
        positive_threshold,
    )
    if known_label is None:
        evaluation = None
    elif prediction in {"UNCERTAIN", "OUT_OF_DOMAIN"}:
        evaluation = "ABSTAIN"
    else:
        predicted_label = int(prediction == "COFFEE_ODOR_LIKELY")
        evaluation = "CORRECT" if predicted_label == known_label else "WRONG"

    negative_count = int(np.sum(y_train == 0))
    positive_count = int(np.sum(y_train == 1))
    return {
        "input_file": str(raw_path),
        "prediction": prediction,
        "prediction_vi": prediction_vi,
        "coffee_probability": probability,
        "known_ground_truth": known_label,
        "evaluation_against_label": evaluation,
        "leave_one_out_for_known_file": known_row is not None,
        "out_of_distribution": bool(domain["out_of_distribution"]),
        "domain": domain,
        "thresholds": {
            "no_coffee_max": negative_threshold,
            "coffee_min": positive_threshold,
        },
        "feature_support": feature_explanations(model, x_input),
        "features": extracted["features"],
        "quality": quality,
        "warnings": extracted["warnings"],
        "training": {
            "sessions": len(sessions),
            "negative": negative_count,
            "positive": positive_count,
            "skipped": skipped,
        },
        "model_version": MODEL_VERSION,
        "feature_version": feature_pipeline.FEATURE_VERSION,
        "training_manifest_hash": feature_pipeline.training_manifest_hash(sessions),
        "model": {
            "pipeline": "StandardScaler + LogisticRegression",
            "penalty": "l2",
            "C": LOGISTIC_C,
            "class_weight": "balanced",
        },
    }


def evaluate_predictions(
    labels: np.ndarray,
    probabilities: np.ndarray,
    decisions: list[str],
) -> dict[str, object]:
    raw_predictions = (probabilities >= 0.5).astype(int)
    matrix = confusion_matrix(labels, raw_predictions, labels=[0, 1])
    decisive_indices = [
        index
        for index, decision in enumerate(decisions)
        if decision in {"COFFEE_ODOR_LIKELY", "NO_COFFEE_ODOR_LIKELY"}
    ]
    decisive_correct = sum(
        int(decisions[index] == "COFFEE_ODOR_LIKELY") == int(labels[index])
        for index in decisive_indices
    )
    return {
        "raw_balanced_accuracy": float(balanced_accuracy_score(labels, raw_predictions)),
        "raw_confusion_matrix": matrix.tolist(),
        "raw_accuracy": float(np.mean(raw_predictions == labels)),
        "coverage": len(decisive_indices) / len(labels),
        "accuracy_when_decisive": (
            decisive_correct / len(decisive_indices) if decisive_indices else None
        ),
        "decisive": len(decisive_indices),
        "abstained": len(labels) - len(decisive_indices),
        "positive_detected": sum(
            decision == "COFFEE_ODOR_LIKELY" and label == 1
            for decision, label in zip(decisions, labels)
        ),
        "positive_missed_as_no_coffee": sum(
            decision == "NO_COFFEE_ODOR_LIKELY" and label == 1
            for decision, label in zip(decisions, labels)
        ),
        "positive_abstained": sum(
            decision in {"UNCERTAIN", "OUT_OF_DOMAIN"} and label == 1
            for decision, label in zip(decisions, labels)
        ),
        "negative_false_positive": sum(
            decision == "COFFEE_ODOR_LIKELY" and label == 0
            for decision, label in zip(decisions, labels)
        ),
    }


def self_test(
    data_root: Path,
    negative_threshold: float,
    positive_threshold: float,
) -> dict[str, object]:
    sessions, skipped = feature_pipeline.load_training_sessions(data_root)
    x = feature_pipeline.feature_matrix(sessions)
    labels = np.asarray([int(session["label"]) for session in sessions])
    probabilities = []
    decisions = []
    rows = []
    for index, session in enumerate(sessions):
        mask = np.arange(len(sessions)) != index
        model = build_model()
        model.fit(x[mask], labels[mask])
        probability = float(model.predict_proba(x[index : index + 1])[0, 1])
        domain = feature_pipeline.domain_diagnostics(
            model, x[mask], x[index : index + 1]
        )[0]
        decision, _ = classify_probability(
            probability,
            bool(domain["out_of_distribution"]),
            negative_threshold,
            positive_threshold,
        )
        probabilities.append(probability)
        decisions.append(decision)
        rows.append(
            {
                "day": session["day"],
                "folder": session["folder"],
                "truth": int(session["label"]),
                "coffee_probability": probability,
                "prediction": decision,
                "out_of_distribution": bool(domain["out_of_distribution"]),
            }
        )
    return {
        "model_version": MODEL_VERSION,
        "feature_version": feature_pipeline.FEATURE_VERSION,
        "sessions": len(sessions),
        "negative": int(np.sum(labels == 0)),
        "positive": int(np.sum(labels == 1)),
        "thresholds": {
            "no_coffee_max": negative_threshold,
            "coffee_min": positive_threshold,
        },
        "evaluation": evaluate_predictions(
            labels, np.asarray(probabilities), decisions
        ),
        "rows": rows,
        "skipped": skipped,
    }


def parse_manifest_label(value: object) -> int | None:
    text = str(value).strip()
    return int(text) if text in {"0", "1"} else None


def batch_test(
    date_root: Path,
    data_root: Path,
    negative_threshold: float,
    positive_threshold: float,
) -> dict[str, object]:
    manifest_path = date_root / "label_manifest.csv"
    with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    rows = []
    for manifest_row in manifest:
        raw_path = date_root / manifest_row["folder"] / "raw.csv"
        label = parse_manifest_label(manifest_row.get("coffee_on_person_label"))
        eligible = manifest_row.get("binary_use") == "ELIGIBLE" and label is not None
        result = predict(
            raw_path,
            data_root,
            negative_threshold,
            positive_threshold,
        )
        prediction = str(result["prediction"])
        if not eligible:
            evaluation = "OUT_OF_SCOPE"
        elif prediction in {"UNCERTAIN", "OUT_OF_DOMAIN", "INVALID_MEASUREMENT"}:
            evaluation = "ABSTAIN"
        else:
            predicted_label = int(prediction == "COFFEE_ODOR_LIKELY")
            evaluation = "CORRECT" if predicted_label == label else "WRONG"
        rows.append(
            {
                "session_no": int(manifest_row["session_no"]),
                "folder": manifest_row["folder"],
                "experiment_group": manifest_row.get("experiment_group"),
                "true_label": label,
                "eligible": eligible,
                "coffee_probability": result.get("coffee_probability"),
                "prediction": prediction,
                "evaluation": evaluation,
                "out_of_distribution": result.get("out_of_distribution"),
            }
        )
    eligible_rows = [row for row in rows if row["eligible"]]
    decisive = [
        row
        for row in eligible_rows
        if row["prediction"] in {"COFFEE_ODOR_LIKELY", "NO_COFFEE_ODOR_LIKELY"}
    ]
    correct = sum(row["evaluation"] == "CORRECT" for row in eligible_rows)
    positives = [row for row in eligible_rows if row["true_label"] == 1]
    negatives = [row for row in eligible_rows if row["true_label"] == 0]
    return {
        "date_root": str(date_root.resolve()),
        "model_version": MODEL_VERSION,
        "rows": rows,
        "summary": {
            "eligible": len(eligible_rows),
            "decisive": len(decisive),
            "correct": correct,
            "wrong": sum(row["evaluation"] == "WRONG" for row in eligible_rows),
            "abstained": len(eligible_rows) - len(decisive),
            "coverage": len(decisive) / len(eligible_rows) if eligible_rows else None,
            "accuracy_when_decisive": correct / len(decisive) if decisive else None,
            "correct_over_all": correct / len(eligible_rows) if eligible_rows else None,
            "positive_total": len(positives),
            "positive_detected": sum(
                row["prediction"] == "COFFEE_ODOR_LIKELY" for row in positives
            ),
            "positive_missed": sum(
                row["prediction"] == "NO_COFFEE_ODOR_LIKELY" for row in positives
            ),
            "positive_abstained": sum(
                row["prediction"] in {"UNCERTAIN", "OUT_OF_DOMAIN"}
                for row in positives
            ),
            "negative_false_positive": sum(
                row["prediction"] == "COFFEE_ODOR_LIKELY" for row in negatives
            ),
        },
    }


def format_probability(value: object) -> str:
    return "-" if value is None else f"{float(value):.3f}"


def print_prediction(result: dict[str, object]) -> None:
    print("=" * 72)
    print("LOGISTIC REGRESSION – KIỂM TRA MÙI CÀ PHÊ")
    print("=" * 72)
    print(f"Kết luận       : {result['prediction_vi']}")
    print(f"Mã kết quả     : {result['prediction']}")
    if result["coffee_probability"] is None:
        for error in result["quality"]["errors"]:
            print(f"  - {error}")
        return
    print(f"P(cà phê)      : {float(result['coffee_probability']):.3f}")
    print(
        f"Ngưỡng         : KHÔNG <= {result['thresholds']['no_coffee_max']:.2f}; "
        f"CÓ >= {result['thresholds']['coffee_min']:.2f}"
    )
    print(f"Ngoài miền học : {'Có' if result['out_of_distribution'] else 'Không'}")
    if result["known_ground_truth"] is not None:
        print(f"Nhãn thật      : {result['known_ground_truth']}")
        print(f"Đánh giá       : {result['evaluation_against_label']}")
    training = result["training"]
    print(
        f"Tập học        : {training['sessions']} phiên "
        f"({training['negative']} âm, {training['positive']} dương)"
    )
    print("\nĐặc trưng ảnh hưởng mạnh nhất:")
    for row in result["feature_support"][:10]:
        direction = "ủng hộ CÓ" if row["supports_coffee"] else "ủng hộ KHÔNG"
        print(
            f"  - {row['feature_label']}: {float(row['value']):+.3f}; "
            f"{direction} ({float(row['log_odds_contribution']):+.3f} log-odds)"
        )
    print("\nLưu ý: P(cà phê) chưa được hiệu chỉnh xác suất do tập dữ liệu rất nhỏ.")


def print_self_test(result: dict[str, object]) -> None:
    evaluation = result["evaluation"]
    matrix = evaluation["raw_confusion_matrix"]
    print("=" * 86)
    print("LOOCV LOGISTIC REGRESSION – TOÀN BỘ TẬP HUẤN LUYỆN")
    print("=" * 86)
    print(
        f"Dữ liệu: {result['sessions']} phiên "
        f"({result['negative']} âm, {result['positive']} dương)"
    )
    print(
        f"Ngưỡng 0.5: accuracy {evaluation['raw_accuracy']:.1%}; "
        f"balanced accuracy {evaluation['raw_balanced_accuracy']:.1%}; "
        f"confusion [[TN, FP], [FN, TP]] = {matrix}"
    )
    print(
        f"Vùng từ chối: coverage {evaluation['coverage']:.1%}; "
        f"accuracy khi kết luận "
        f"{evaluation['accuracy_when_decisive']:.1%}"
        if evaluation["accuracy_when_decisive"] is not None
        else "Không có quyết định chắc chắn"
    )
    print(
        f"Có cà phê: phát hiện {evaluation['positive_detected']}/{result['positive']}; "
        f"nhầm KHÔNG {evaluation['positive_missed_as_no_coffee']}; "
        f"từ chối {evaluation['positive_abstained']}"
    )
    print(f"Không cà phê bị báo nhầm CÓ: {evaluation['negative_false_positive']}")
    print("\nNgày  | Nhãn | P(cà phê) | Kết quả                 | Folder")
    for row in result["rows"]:
        print(
            f"{str(row['day'])[-5:]:>5} | {row['truth']:^4} | "
            f"{row['coffee_probability']:^9.3f} | {row['prediction']:<23} | "
            f"{row['folder']}"
        )


def print_batch(result: dict[str, object]) -> None:
    print("=" * 112)
    print("BATCH LOGISTIC REGRESSION – TẤT CẢ MẪU TRONG MANIFEST")
    print("=" * 112)
    print("STT | Nhãn | P(CF) | Kết quả                  | Đánh giá     | Nhóm          | Folder")
    for row in result["rows"]:
        label = "-" if row["true_label"] is None else str(row["true_label"])
        print(
            f"{row['session_no']:>3} | {label:^4} | "
            f"{format_probability(row['coffee_probability']):>5} | "
            f"{row['prediction']:<24} | {row['evaluation']:<12} | "
            f"{str(row['experiment_group']):<13} | {row['folder']}"
        )
    summary = result["summary"]
    print("\nTHỐNG KÊ TRÊN CÁC MẪU ELIGIBLE")
    print(
        f"  Tổng {summary['eligible']}; kết luận {summary['decisive']}; "
        f"đúng {summary['correct']}; sai {summary['wrong']}; "
        f"từ chối {summary['abstained']}"
    )
    print(
        f"  Coverage {summary['coverage']:.1%}; accuracy khi kết luận "
        f"{summary['accuracy_when_decisive']:.1%}; "
        f"đúng trên toàn bộ {summary['correct_over_all']:.1%}"
        if summary["accuracy_when_decisive"] is not None
        else "  Không có quyết định chắc chắn"
    )
    print(
        f"  Có cà phê: phát hiện {summary['positive_detected']}/{summary['positive_total']}; "
        f"nhầm KHÔNG {summary['positive_missed']}; "
        f"từ chối {summary['positive_abstained']}"
    )
    print(f"  Không cà phê bị báo nhầm CÓ: {summary['negative_false_positive']}")


def validate_thresholds(negative: float, positive: float) -> None:
    if not 0.0 <= negative < 0.5 < positive <= 1.0:
        raise ValueError(
            "Cần 0 <= --negative-threshold < 0.5 < --positive-threshold <= 1"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Logistic Regression độc lập kiểm tra mùi cà phê từ raw.csv."
    )
    parser.add_argument("raw_csv", nargs="?", type=Path)
    parser.add_argument("--data-root", type=Path, default=feature_pipeline.DATA_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--batch",
        nargs="?",
        type=Path,
        const=DEFAULT_DATE_ROOT,
        metavar="DATE_ROOT",
    )
    parser.add_argument(
        "--negative-threshold", type=float, default=DEFAULT_NEGATIVE_THRESHOLD
    )
    parser.add_argument(
        "--positive-threshold", type=float, default=DEFAULT_POSITIVE_THRESHOLD
    )
    parser.add_argument("--json", type=Path, help="Ghi kết quả chi tiết ra JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate_thresholds(args.negative_threshold, args.positive_threshold)
        selected_modes = sum(
            [args.raw_csv is not None, bool(args.self_test), args.batch is not None]
        )
        if selected_modes != 1:
            raise ValueError("Chọn đúng một chế độ: raw.csv, --self-test hoặc --batch")
        if args.self_test:
            result = self_test(
                args.data_root,
                args.negative_threshold,
                args.positive_threshold,
            )
            print_self_test(result)
        elif args.batch is not None:
            result = batch_test(
                args.batch,
                args.data_root,
                args.negative_threshold,
                args.positive_threshold,
            )
            print_batch(result)
        else:
            result = predict(
                args.raw_csv,
                args.data_root,
                args.negative_threshold,
                args.positive_threshold,
            )
            print_prediction(result)
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"\nĐã ghi JSON: {args.json}")
        return 0
    except (FileNotFoundError, ValueError, KeyError, csv.Error) as error:
        print(f"LỖI: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
