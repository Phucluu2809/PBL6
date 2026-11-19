import argparse
import json
import math
import os
from pathlib import Path
import signal
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description="RoboNose dataset host — explicit simulation or USB hardware")
    backend = parser.add_mutually_exclusive_group(required=True)
    backend.add_argument("--demo", action="store_true", help="Run the simulation terminal and dashboard")
    backend.add_argument("--port", help="Explicit hardware port; valid startup automatically commands PWM 80%%")
    backend.add_argument("--find-sample", metavar="NAME", help="Find every trial with this name and print its folder; read-only, no COM/GUI")
    parser.add_argument("--serial-kind", choices=["native-cdc", "uart"], help="Required with --port; DTR/RTS deasserted before open")
    parser.add_argument("--offscreen", action="store_true", help="Qt offscreen integration check")
    parser.add_argument("--auto-close-s", type=float, default=0, help="Finite smoke run; zero keeps the window open")
    parser.add_argument("--web", action="store_true", help="Run the local web dashboard instead of the Qt window")
    parser.add_argument("--web-host", default="127.0.0.1", help="Web bind address; use 0.0.0.0 for an explicitly trusted LAN")
    parser.add_argument("--web-port", type=int, default=8000, help="Local web port (default: 8000)")
    parser.add_argument("--model-dir", type=Path,
                        help="Versioned ResCNN64 artifact directory; omit to keep the explicit mock backend")
    parser.add_argument("--model-sample-root", type=Path, action="append", default=[],
                        help="Additional read-only trial root for model inference; may be repeated")
    parser.add_argument("--model-similarity-threshold", type=float,
                        help="Calibrated cosine threshold; requires --model-margin-threshold")
    parser.add_argument("--model-margin-threshold", type=float,
                        help="Calibrated top-1/top-2 margin; requires --model-similarity-threshold")
    args = parser.parse_args(argv)
    # Windows redirected/legacy consoles may otherwise reject Vietnamese UI
    # messages before the web server has fully started.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if args.port and not args.serial_kind:
        parser.error("--port requires explicit --serial-kind native-cdc or uart")
    if args.serial_kind and not args.port:
        parser.error("--serial-kind applies only to --port")
    if not math.isfinite(args.auto_close_s) or args.auto_close_s < 0:
        parser.error("--auto-close-s must be finite and nonnegative")
    if not 1 <= args.web_port <= 65535:
        parser.error("--web-port must be in 1..65535")
    if args.web and args.offscreen:
        parser.error("--offscreen applies to the Qt dashboard, not --web")
    model_options = (args.model_similarity_threshold, args.model_margin_threshold)
    if args.model_dir and not args.web:
        parser.error("--model-dir applies only to --web")
    if args.model_sample_root and not args.model_dir:
        parser.error("--model-sample-root requires --model-dir")
    if any(value is not None for value in model_options) and not args.model_dir:
        parser.error("model thresholds require --model-dir")
    if (model_options[0] is None) != (model_options[1] is None):
        parser.error("both model thresholds must be supplied together")
    root = Path(__file__).resolve().parents[1]
    if args.find_sample is not None:
        if args.offscreen or args.auto_close_s or args.web:
            parser.error("GUI/web options do not apply to --find-sample")
        from .sample_catalog import find_samples, format_results
        try:
            result = find_samples(root / "data", args.find_sample)
        except ValueError as error:
            parser.error(str(error))
        print(format_results(args.find_sample, result))
        for warning in result.warnings:
            print(f"Cảnh báo đọc dữ liệu: {warning}", file=sys.stderr)
        return 0
    # The approved Windows workflow pins its interpreter.  Raspberry Pi uses a
    # separate Linux venv and must not inherit a D:\ path from paths.local.json.
    if os.name == "nt":
        paths = json.loads((root / "configs/paths.local.json").read_text(encoding="utf-8"))
        if Path(sys.executable).resolve() != Path(paths["python_exe"]).resolve():
            parser.error(f"Use the configured interpreter: {paths['python_exe']}")
    if args.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    data_root = root / ("data/simulation" if args.demo else "data/hardware")
    hardware_root = (root / "data/hardware").resolve()
    predictor = None
    model_sample_roots = []
    if args.model_dir:
        from .rescnn64 import ResCNN64Predictor
        model_dir = args.model_dir if args.model_dir.is_absolute() else root / args.model_dir
        for value in args.model_sample_root:
            sample_root = value if value.is_absolute() else root / value
            try:
                sample_root = sample_root.resolve(strict=True)
            except OSError as error:
                parser.error(f"model sample root does not exist: {sample_root}: {error}")
            if not sample_root.is_dir():
                parser.error(f"model sample root is not a directory: {sample_root}")
            model_sample_roots.append(sample_root)
        # Hardware trials are the canonical source for inference and win on duplicate UUIDs.
        inference_roots = list(dict.fromkeys([hardware_root, data_root.resolve(), *model_sample_roots]))
        try:
            predictor = ResCNN64Predictor(
                model_dir, inference_roots,
                similarity_threshold=args.model_similarity_threshold,
                margin_threshold=args.model_margin_threshold)
        except Exception as error:
            print(f"Model startup failed: {type(error).__name__}: {error}", file=sys.stderr)
            return 1
    from .recorder import find_partial_sessions
    from .session import Session
    from .terminal import Terminal

    partials = find_partial_sessions(data_root)
    if partials:
        print(f"Found {len(partials)} prior PARTIAL/ERROR sessions; kept unchanged, not resumed.", flush=True)
    try:
        if args.demo:
            session = Session(data_root, on_message=lambda text: print(text, flush=True))
        else:
            from .hardware import HardwareEngine
            from .usb_protocol import SerialOptions
            options = SerialOptions(args.port, args.serial_kind)
            session = Session(data_root, mode="HARDWARE", on_message=lambda text: print(text, flush=True),
                engine_factory=lambda config, clock, recorder: HardwareEngine(config, clock, recorder, options))
    except Exception as error:
        print(f"Host startup failed: {error}", file=sys.stderr)
        return 1

    if args.web:
        from .web_server import RoboNoseWebServer
        try:
            web = RoboNoseWebServer(
                session, data_root, args.web_host, args.web_port, predictor=predictor,
                catalog_roots=list(dict.fromkeys([hardware_root, data_root.resolve(), *model_sample_roots])))
        except Exception as error:
            session.engine.shutdown("web startup fault")
            print(f"Web startup failed: {error}", file=sys.stderr)
            return 1
        terminal = Terminal(session) if sys.stdin.isatty() and not args.auto_close_s else None
        previous_signal = signal.signal(signal.SIGINT, lambda *_: session.request_stop("Ctrl+C"))
        session.start()
        address = web.start()
        if terminal:
            terminal.start()
        print(f"{session.mode} DATA | web: {address} | bind: {args.web_host}:{web.httpd.server_address[1]}", flush=True)
        print(f"Session: {session.engine.recorder.path}\nBrowser close does not stop acquisition; use Dừng hệ thống or Ctrl+C.", flush=True)
        started = session.clock.now()
        try:
            while not session.finished.wait(.1):
                if args.auto_close_s and session.clock.now() - started >= args.auto_close_s:
                    session.request_stop("web-auto-close")
        finally:
            if terminal:
                terminal.stop()
            session.request_stop("web-exit")
            session.thread.join(15 if not args.demo else 12)
            web.stop()
            signal.signal(signal.SIGINT, previous_signal)
        snap = session.snapshot()
        print(f"Session {snap['writer']['status']} | last reported PWM {snap['pump_pwm_pct']}% | {snap['writer']['path']}" +
              (f" | commanded OFF acknowledged: {snap.get('off_confirmed', False)}" if not args.demo else "") +
              (f" | reason: {snap.get('fault') or snap['writer']['error']}" if snap.get('fault') or snap['writer']['error'] else ""), flush=True)
        return 1 if session.thread.is_alive() or snap["writer"]["error"] else 0

    from PySide6 import QtCore, QtWidgets
    from .dashboard import Dashboard, configure_qt_font
    app = QtWidgets.QApplication([sys.argv[0]])
    configure_qt_font(app)
    terminal = Terminal(session)
    previous_signal = signal.signal(signal.SIGINT, lambda *_: session.request_stop("Ctrl+C"))
    window = Dashboard(session)
    app.aboutToQuit.connect(lambda: session.request_stop("Qt-exit"))
    session.start()
    # Finite offscreen smoke uses an idle terminal, not the tool runner's closed stdin.
    if not (args.offscreen and args.auto_close_s):
        terminal.start()
    if args.auto_close_s:
        QtCore.QTimer.singleShot(int(args.auto_close_s * 1000), window.close)
    print(f"{session.mode} DATA | session: {session.engine.recorder.path}\nCommands: help, start, expose, recover, finish, name Mau1, next, quit", flush=True)
    window.show()
    try:
        result = app.exec()
    finally:
        terminal.stop()
        session.request_stop("Qt-exit")
        session.thread.join(15 if not args.demo else 12)
        signal.signal(signal.SIGINT, previous_signal)
    snap = session.snapshot()
    print(f"Session {snap['writer']['status']} | last reported PWM {snap['pump_pwm_pct']}% | {snap['writer']['path']}" +
          (f" | commanded OFF acknowledged: {snap.get('off_confirmed', False)}" if not args.demo else "") +
          (f" | reason: {snap.get('fault') or snap['writer']['error']}" if snap.get('fault') or snap['writer']['error'] else ""), flush=True)
    return 1 if session.thread.is_alive() or snap["writer"]["error"] else result


if __name__ == "__main__":
    raise SystemExit(main())
