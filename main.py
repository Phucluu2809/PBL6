"""Simple entry point for identifying a person from an odor raw.csv file."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PREDICTOR = ROOT / "analysis" / "predict_odor_identity.py"
DEFAULT_MODEL_DIR = ROOT / "data" / "2026-10-25_augmented"


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Nhận diện người từ một file raw.csv bằng vector đặc trưng và "
            "cosine similarity."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="Đường dẫn tới raw.csv hoặc thư mục chứa raw.csv.",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=DEFAULT_MODEL_DIR,
        help="Thư mục chứa identity_model.json và scaler.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Đường dẫn file kết quả JSON; mặc định là prediction.json cạnh raw.csv.",
    )
    return parser.parse_args()


def clean_pasted_path(value: str) -> Path:
    return Path(value.strip().strip('"').strip("'"))


def resolve_raw_path(input_path: Path) -> Path:
    path = input_path.expanduser().resolve()
    raw_path = path / "raw.csv" if path.is_dir() else path
    if not raw_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file raw.csv: {raw_path}")
    return raw_path


def main() -> int:
    configure_console()
    args = parse_args()

    input_path = args.input
    if input_path is None:
        pasted = input("Nhập đường dẫn raw.csv (hoặc thư mục chứa nó): ")
        if not pasted.strip():
            print("Lỗi: chưa nhập đường dẫn dữ liệu.", file=sys.stderr)
            return 1
        input_path = clean_pasted_path(pasted)

    try:
        raw_path = resolve_raw_path(input_path)
    except FileNotFoundError as error:
        print(f"Lỗi: {error}", file=sys.stderr)
        return 1

    model_dir = args.model_dir.expanduser().resolve()
    required_model_files = ["identity_model.json", "scaler.json"]
    missing = [name for name in required_model_files if not (model_dir / name).is_file()]
    if missing:
        print(
            f"Lỗi: thiếu {', '.join(missing)} trong {model_dir}.\n"
            "Hãy chạy: python analysis\\augment_and_extract_odor_features.py",
            file=sys.stderr,
        )
        return 1

    command = [
        sys.executable,
        str(PREDICTOR),
        "--input",
        str(raw_path),
        "--model-dir",
        str(model_dir),
    ]
    if args.output is not None:
        command.extend(["--output", str(args.output.expanduser().resolve())])

    print(f"Đang phân tích: {raw_path}", flush=True)
    print(f"Model: {model_dir}", flush=True)
    print("-" * 60, flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)

    if completed.returncode == 2:
        print("\nKết luận: mẫu bị từ chối vì chất lượng tín hiệu không đạt.")
    elif completed.returncode != 0:
        print("\nKhông thể hoàn thành nhận diện.", file=sys.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
