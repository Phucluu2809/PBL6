"""Dependency-free local web adapter for the existing Session owner.

The HTTP layer never opens serial, owns phase timers, or writes canonical raw
files.  Commands enter the same bounded Session mailbox used by the terminal.
"""
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import uuid
from urllib.parse import parse_qs, urlparse

from .inference import InferenceCoordinator
from .schema import finite_or_none, valid_signal


SENSOR_META = (
    ("tgs2602", "tgs2602_voltage_v", "TGS2602 · A0", "V", 1, "tgs2602_adc_count"),
    ("mq3_1", "mq3_1_voltage_v", "MQ3 #1 · A1", "V", 1, "mq3_1_adc_count"),
    ("mq135_2", "mq135_2_voltage_v", "MQ135 #2 · A2", "V", 1, "mq135_2_adc_count"),
    ("mq3_2", "mq3_2_voltage_v", "MQ3 #2 · A3", "V", 1, "mq3_2_adc_count"),
    ("bme_gas", "gas_resistance_ohm", "BME688 · Gas", "kΩ", 1000, None),
    ("temperature", "temperature_c", "Nhiệt độ", "°C", 1, None),
    ("humidity", "humidity_pct", "Độ ẩm", "%RH", 1, None),
    ("pressure", "pressure_hpa", "Áp suất", "hPa", 1, None),
)

PHASE_ACTIONS = {
    "configure": {"MONITOR"},
    "start": {"MONITOR"},
    "expose": {"WAIT_EXPOSURE"},
    "recover": {"WAIT_RECOVERY"},
    "finish": {"WAIT_FINISH"},
    "name": {"WAIT_NAME"},
    "notes": {"WAIT_NAME"},
    "next": {"WAIT_NAME"},
    "abort": {"BASELINE", "WAIT_EXPOSURE", "EXPOSURE", "WAIT_RECOVERY", "RECOVERY", "WAIT_FINISH"},
    "pause": {"MONITOR"},
    "resume": {"OFF"},
}
ARGUMENT_ACTIONS = {"name", "notes", "mark", "configure"}
PLAIN_ACTIONS = {"start", "expose", "recover", "finish", "next", "abort", "pause", "resume"}


def _wall_time():
    return datetime.now(timezone.utc).astimezone().isoformat()


class MessageHub:
    def __init__(self):
        self.messages = deque(maxlen=256)
        self.sequence = 0
        self.lock = threading.Lock()

    def publish(self, text, level="INFO", **details):
        with self.lock:
            self.sequence += 1
            item = {"sequence": self.sequence, "at": _wall_time(), "level": level,
                    "text": str(text), **details}
            self.messages.append(item)
            return deepcopy(item)

    def snapshot(self, after=0):
        with self.lock:
            return [deepcopy(item) for item in self.messages if item["sequence"] > after]


class TrialCatalog:
    """Read-only listing of finalized and pending trial exports."""

    def __init__(self, data_roots):
        roots = data_roots if isinstance(data_roots, (list, tuple)) else [data_roots]
        self.data_roots = tuple(dict.fromkeys(Path(root).resolve() for root in roots))

    def list(self, limit=1000):
        rows = []
        paths = []
        for root in self.data_roots:
            paths.extend(path for path in root.rglob("metadata.json")
                         if path.parent.parent.name == "trials")
        seen = set()
        for path in paths:
            try:
                metadata = json.loads(path.read_text(encoding="utf-8-sig"))
                trial_id = metadata.get("trial_id")
                if not isinstance(trial_id, str) or not trial_id:
                    continue
                if trial_id in seen:
                    continue
                seen.add(trial_id)
                summary_path = path.parent / "summary.json"
                quality = "NOT_EVALUATED"
                quality_reasons = []
                if summary_path.is_file():
                    try:
                        summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
                        if isinstance(summary, dict):
                            quality = str(summary.get("quality", quality))
                            reasons = summary.get("quality_reasons")
                            if isinstance(reasons, list):
                                quality_reasons = [str(reason) for reason in reasons]
                    except (OSError, UnicodeError, ValueError):
                        quality = "INVALID_SUMMARY"
                rows.append({
                    "trial_id": trial_id,
                    "name": metadata.get("name"),
                    "status": metadata.get("status", "UNKNOWN"),
                    "mode": metadata.get("mode", "UNKNOWN"),
                    "started_at": metadata.get("started_at"),
                    "session_id": metadata.get("session_id"),
                    "export_finalized": metadata.get("export_finalized") is True,
                    "folder": str(path.parent.resolve()),
                    "summary_ready": summary_path.is_file(),
                    "quality": quality,
                    "quality_reasons": quality_reasons,
                })
            except (OSError, UnicodeError, ValueError):
                continue
        rows.sort(key=lambda item: (item.get("started_at") or "", item["trial_id"]), reverse=True)
        return rows[:limit]

    def find(self, trial_id):
        return next((item for item in self.list() if item["trial_id"] == trial_id), None)


def _action_state(phase, closed):
    states = {action: (not closed and phase in phases) for action, phases in PHASE_ACTIONS.items()}
    states.update(mark=not closed)
    return states


def _warnings(snapshot, heartbeat):
    warnings = []
    def add(code, severity, message):
        warnings.append({"code": code, "severity": severity, "message": message})
    if snapshot.get("mode") == "SIMULATED":
        add("SIMULATED_DATA", "info", "Dữ liệu mô phỏng; không phải đo từ cảm biến thật.")
    if (snapshot.get("device_info") or {}).get("firmware_version") == "3.0.0":
        add("LEGACY_FIRMWARE", "info", "Firmware 3.0.0 vẫn thu hardware bình thường; chỉnh thời gian bị khóa cho tới khi nạp 3.1.0.")
    if snapshot.get("fault"):
        add("SESSION_FAULT", "critical", str(snapshot["fault"]))
    writer = snapshot.get("writer") or {}
    if writer.get("error"):
        add("WRITER_ERROR", "critical", str(writer["error"]))
    if snapshot.get("sample_count", 0) and not heartbeat and snapshot.get("phase") not in ("CLOSED", "ERROR"):
        add("HEARTBEAT", "warning", "Heartbeat dữ liệu/writer chưa khỏe hoặc đã dừng.")
    if snapshot.get("errors", 0):
        add("DEVICE_ERRORS", "warning", f"Đã ghi nhận {snapshot['errors']} lỗi device.")
    if snapshot.get("stale", 0):
        add("STALE_SAMPLES", "warning", f"Đã ghi nhận {snapshot['stale']} giá trị stale.")
    quality = (snapshot.get("quality") or {}).get("overall")
    if quality in ("WARN", "INSUFFICIENT", "UNCONFIGURED"):
        add("QUALITY", "warning", f"Quality hiện tại: {quality}.")
    latest = snapshot.get("latest") or {}
    try:
        if latest.get("temperature_c") is not None and float(latest["temperature_c"]) > 35:
            add("TEMPERATURE", "warning", "Nhiệt độ BME688 cao hơn ngưỡng advisory 35°C.")
    except (TypeError, ValueError):
        pass
    return warnings


def project_snapshot(snapshot, window_s=600):
    """Make a bounded, JSON-safe presentation snapshot for 1 Hz polling."""
    now = float(snapshot.get("now") or 0)
    window_s = min(1800, max(30, int(window_s)))
    rows = [row for row in snapshot.get("history", ()) if float(row.get("mono_s", 0)) >= now - window_s]
    latest = snapshot.get("latest")
    sensors, series = [], {}
    quality_signals = (snapshot.get("quality") or {}).get("signals", {})
    for sensor_id, signal, label, unit, scale, count_key in SENSOR_META:
        usable = bool(latest and valid_signal(latest, signal) and now - float(latest["mono_s"]) < 3)
        value = float(latest[signal]) / scale if usable else None
        sensor = {"id": sensor_id, "signal": signal, "label": label, "unit": unit,
                  "value": value, "adc_count": latest.get(count_key) if usable and count_key else None,
                  "quality": quality_signals.get(signal, {})}
        sensors.append(sensor)
        points = []
        for row in rows:
            t = float(row["mono_s"])
            point = float(row[signal]) / scale if valid_signal(row, signal) else None
            points.append([t, point])
        series[signal] = points
    heartbeat = bool(snapshot.get("heartbeat_healthy", snapshot.get("simulated_heartbeat_healthy", False)))
    phase = snapshot.get("phase", "UNKNOWN")
    closed = phase in ("CLOSED", "ERROR")
    events = []
    for event in snapshot.get("events", ())[-40:]:
        details = event.get("details") if isinstance(event, dict) else {}
        events.append({"event": event.get("event", "event"),
                       "effective_mono_s": event.get("effective_mono_s"),
                       "details": details if isinstance(details, dict) else {}})
    result = {
        "mode": snapshot.get("mode"), "now": now, "phase": phase,
        "baseline_s": snapshot.get("baseline_s"), "exposure_s": snapshot.get("exposure_s"),
        "recovery_s": snapshot.get("recovery_s"),
        "remaining_s": snapshot.get("remaining_s"), "trial": snapshot.get("trial"),
        "context_epoch": snapshot.get("context_epoch"), "segment_id": snapshot.get("segment_id"),
        "outputs": {"pump_pwm_pct": snapshot.get("pump_pwm_pct"),
                    "valve_energized": snapshot.get("valve_energized"),
                    "air_path_commanded": snapshot.get("air_path_commanded"),
                    "commanded_state_only": snapshot.get("mode") != "SIMULATED"},
        "device": {"heartbeat_healthy": heartbeat, "startup": snapshot.get("startup"),
                   "off_confirmed": snapshot.get("off_confirmed"), "fault": snapshot.get("fault"),
                   "sample_count": snapshot.get("sample_count", 0), "gaps": snapshot.get("gaps", 0),
                   "errors": snapshot.get("errors", 0), "stale": snapshot.get("stale", 0),
                   "physical_sensor_count": 5, "signal_count": len(SENSOR_META)},
        "device_info": snapshot.get("device_info") or {},
        "writer": snapshot.get("writer"), "quality": snapshot.get("quality"),
        "sensors": sensors, "series": series, "events": events,
        "warnings": _warnings(snapshot, heartbeat), "actions": _action_state(phase, closed),
        "window_s": window_s, "session_finished": closed,
    }
    return finite_or_none(result)


class RoboNoseWebApplication:
    def __init__(self, session, data_root, predictor=None, catalog_roots=None):
        self.session = session
        self.data_root = Path(data_root)
        self.static_root = Path(__file__).with_name("web")
        self.messages = MessageHub()
        self.catalog = TrialCatalog(catalog_roots or [data_root])
        previous = session.on_message

        def combined_message(text):
            previous(text)
            self.messages.publish(text)
        session.on_message = combined_message
        self.inference = InferenceCoordinator(predictor=predictor, event_sink=self._record_inference)

    def _record_inference(self, result):
        event = {"event": "inference_result", "mode": self.session.mode,
                 "timestamp": self.session.clock.timestamp(), "details": result}
        self.session.engine.recorder.submit("event", event)
        label = result.get("predicted_id") or result.get("top_candidate") or result.get("status")
        backend = result.get("model_backend", "MODEL")
        self.messages.publish(f"{backend} {result['task']}: {label}", level="MODEL")

    def start(self):
        self.inference.start()

    def close(self):
        self.inference.close()

    def snapshot(self, window_s):
        snapshot = project_snapshot(self.session.snapshot(), window_s)
        config = self.session.config.snapshot()
        duration_reported = all(snapshot.get(key) is not None for key in
                                ("baseline_s", "exposure_s", "recovery_s"))
        legacy_firmware = snapshot.get("device_info", {}).get("firmware_version") == "3.0.0"
        snapshot["configuration"] = {
            "baseline_s": snapshot.get("baseline_s") or config["baseline_s"],
            "exposure_s": snapshot.get("exposure_s") or config["exposure_s"],
            "recovery_s": snapshot.get("recovery_s") or config["recovery_s"],
            "pump_pwm_pct": config["pump_pwm_pct"],
            "sampling_hz": config["sampling_hz"],
            "runtime_editable": snapshot.get("phase") == "MONITOR" and duration_reported and not legacy_firmware,
            "source": ("MCU_LEGACY_FIXED_60_120_60" if legacy_firmware else
                       "MCU_FIRMWARE_CONTRACT" if self.session.mode != "SIMULATED" else "SIMULATION_CONFIG"),
        }
        model = self.inference.describe()
        snapshot["model"] = model
        if model.get("synthetic_prediction") is True:
            snapshot["warnings"].append({
                "code": "MOCK_MODEL", "severity": "info",
                "message": "Hai chức năng nhận diện đang dùng model giả lập."})
        elif not model.get("unknown_calibrated"):
            snapshot["warnings"].append({
                "code": "MODEL_UNCALIBRATED", "severity": "warning",
                "message": "Model thật chỉ xếp hạng; chưa có ngưỡng để xác nhận danh tính/Unknown."})
        return snapshot

    def post_command(self, payload):
        action = str(payload.get("action", "")).strip().lower()
        if action not in PLAIN_ACTIONS | ARGUMENT_ACTIONS:
            raise ValueError("Unsupported command action")
        argument = str(payload.get("argument", "")).strip()
        if action in ARGUMENT_ACTIONS and not argument:
            raise ValueError(f"{action} requires an argument")
        if action in PLAIN_ACTIONS and argument:
            raise ValueError(f"{action} does not accept an argument")
        text = action if not argument else f"{action} {argument}"
        if len(text) > 2048:
            raise ValueError("Command exceeds 2048 characters")
        request_id = str(payload.get("request_id") or uuid.uuid4())
        if len(request_id) > 128:
            raise ValueError("request_id is too long")
        if not self.session.post(text, request_id=request_id):
            raise RuntimeError("Command queue busy or session closed")
        item = self.messages.publish(f"QUEUED {text}", command=text, request_id=request_id)
        return {"queued": True, "request_id": request_id, "command": text,
                "phase_at_enqueue": self.session.snapshot().get("phase"), "message": item}


class WebRequestHandler(BaseHTTPRequestHandler):
    server_version = "RoboNoseWeb/1.0"

    @property
    def app(self):
        return self.server.app

    def log_message(self, format, *args):
        self.app.messages.publish(format % args, level="HTTP")

    def _headers(self, status, content_type, length):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'")
        self.end_headers()

    def _json(self, value, status=HTTPStatus.OK):
        body = json.dumps(finite_or_none(value), ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _error(self, status, message):
        self._json({"error": str(message)}, status)

    def _payload(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid Content-Length") from error
        if length <= 0 or length > 16384:
            raise ValueError("JSON body must be between 1 and 16384 bytes")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Invalid UTF-8 JSON body") from error
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/snapshot":
                window = int(query.get("window", ["600"])[0])
                self._json(self.app.snapshot(window))
            elif parsed.path == "/api/messages":
                after = int(query.get("after", ["0"])[0])
                self._json({"messages": self.app.messages.snapshot(after)})
            elif parsed.path == "/api/trials":
                self._json({"trials": self.app.catalog.list()})
            elif parsed.path == "/api/inference/results":
                after = int(query.get("after", ["0"])[0])
                self._json({"jobs": self.app.inference.snapshot(after)})
            elif parsed.path == "/api/health":
                self._json({"status": "ok", "backend": "local", "model": self.app.inference.describe()})
            else:
                self._static(parsed.path)
        except (ValueError, TypeError) as error:
            self._error(HTTPStatus.BAD_REQUEST, error)
        except Exception as error:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(error).__name__}: {error}")

    def _static(self, path):
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/styles.css": ("styles.css", "text/css; charset=utf-8")}
        if path not in assets:
            self._error(HTTPStatus.NOT_FOUND, "Not found")
            return
        name, content_type = assets[path]
        body = (self.app.static_root / name).read_bytes()
        self._headers(HTTPStatus.OK, content_type, len(body))
        self.wfile.write(body)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            payload = self._payload()
            if parsed.path == "/api/commands":
                self._json(self.app.post_command(payload), HTTPStatus.ACCEPTED)
            elif parsed.path == "/api/inference/identity":
                sample_id = payload.get("sample_id") or payload.get("trial_id")
                known = self.app.catalog.find(sample_id)
                if known and (known.get("status") != "COMPLETE" or not known.get("export_finalized")):
                    raise ValueError("Mẫu đã bị hủy hoặc chưa lưu hoàn chỉnh; chỉ mẫu COMPLETE mới được dự đoán")
                self._json(self.app.inference.submit_identity(sample_id), HTTPStatus.ACCEPTED)
            elif parsed.path == "/api/inference/compare":
                candidates = payload.get("candidate_ids")
                if not isinstance(candidates, list):
                    raise ValueError("candidate_ids must be a list")
                self._json(self.app.inference.submit_comparison(
                    payload.get("reference_id"), candidates), HTTPStatus.ACCEPTED)
            else:
                self._error(HTTPStatus.NOT_FOUND, "Not found")
        except ValueError as error:
            self._error(HTTPStatus.BAD_REQUEST, error)
        except RuntimeError as error:
            self._error(HTTPStatus.CONFLICT, error)
        except Exception as error:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(error).__name__}: {error}")


class RoboNoseHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class RoboNoseWebServer:
    def __init__(self, session, data_root, host="127.0.0.1", port=8000, predictor=None,
                 catalog_roots=None):
        self.app = RoboNoseWebApplication(
            session, data_root, predictor=predictor, catalog_roots=catalog_roots)
        self.httpd = RoboNoseHTTPServer((host, port), WebRequestHandler)
        self.httpd.app = self.app
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       name="robonose-web-server", daemon=True)
        self.started = False

    @property
    def address(self):
        host, port = self.httpd.server_address[:2]
        display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        return f"http://{display_host}:{port}"

    def start(self):
        if not self.started:
            self.started = True
            self.app.start()
            self.thread.start()
        return self.address

    def stop(self):
        if self.started:
            self.httpd.shutdown()
            self.thread.join(3)
            self.started = False
        self.httpd.server_close()
        self.app.close()
