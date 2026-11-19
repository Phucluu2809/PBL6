"""Start RoboNose from configs/run.json without a long command line."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "run.json"


def fail(message):
    raise SystemExit(f"Cấu hình chạy không hợp lệ: {message}\nFile: {CONFIG_PATH}")


def load_config():
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(error)
    if not isinstance(value, dict):
        fail("nội dung gốc phải là JSON object")
    return value


def build_argv(config):
    mode = config.get("mode")
    interface = config.get("interface", "web")
    if mode not in ("demo", "hardware"):
        fail("mode phải là 'demo' hoặc 'hardware'")
    if interface not in ("web", "qt"):
        fail("interface phải là 'web' hoặc 'qt'")
    argv = ["--demo"] if mode == "demo" else []
    if mode == "hardware":
        hardware = config.get("hardware") or {}
        port = str(hardware.get("port") or "").strip()
        serial_kind = hardware.get("serial_kind")
        if not port:
            fail("hardware.port chưa được đặt")
        if serial_kind not in ("native-cdc", "uart"):
            fail("hardware.serial_kind phải là native-cdc hoặc uart")
        argv += ["--port", port, "--serial-kind", serial_kind]
    if interface == "web":
        web = config.get("web") or {}
        argv += ["--web", "--web-host", str(web.get("host", "127.0.0.1")),
                 "--web-port", str(web.get("port", 8000))]
        model = config.get("model") or {}
        directory = str(model.get("directory") or "").strip()
        if directory:
            argv += ["--model-dir", directory]
            roots = model.get("sample_roots", ["data/hardware"])
            if not isinstance(roots, list) or not all(isinstance(root, str) and root.strip() for root in roots):
                fail("model.sample_roots phải là danh sách đường dẫn")
            for root in roots:
                argv += ["--model-sample-root", root]
            similarity = model.get("similarity_threshold")
            margin = model.get("margin_threshold")
            if (similarity is None) != (margin is None):
                fail("phải đặt đồng thời hai ngưỡng model hoặc để cả hai là null")
            if similarity is not None:
                argv += ["--model-similarity-threshold", str(similarity),
                         "--model-margin-threshold", str(margin)]
    return argv


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    from robonose_s3.__main__ import main
    raise SystemExit(main(build_argv(load_config())))
