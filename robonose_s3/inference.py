"""Versioned inference boundary with deterministic mock implementations.

The mock backend exercises orchestration only.  It never claims that a
physical odor or identity was recognized, and it does not inspect or mutate
canonical raw data.  A real preprocessor/model can replace ``MockPredictor``
without changing the web API or acquisition owner.
"""
from collections import deque
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import queue
import threading
import uuid

from .coffee_detection import predict_trial
from models_v3 import COFFEE_ARTIFACT, IDENTITY_ARTIFACT
from models_v3.coffee import predict_trial as predict_smoothed_coffee


PREDICTION_SCHEMA = "robonose.prediction.v1"
COMPARISON_METHODS = {"default": "compare", "baseline_v2": "compare_baseline_v2",
                      "learned_baseline_v2": "compare_learned_baseline_v2",
                      "smoothed_v3": "compare_smoothed_v3"}


def _timestamp():
    return datetime.now(timezone.utc).astimezone().isoformat()


def _score(*parts, low=0.0, high=1.0):
    digest = hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).digest()
    fraction = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)
    return low + (high - low) * fraction


class MockPredictor:
    """Deterministic fake results for UI, storage and failure-path testing."""

    model_id = "mock.identity-embedding.v1"
    backend = "MOCK"
    labels = ("P001", "P002", "P003", "P004")

    def describe(self):
        return {
            "model_id": self.model_id,
            "model_backend": self.backend,
            "synthetic_prediction": True,
            "labels": list(self.labels),
            "unknown_calibrated": False,
            "similarity_threshold": None,
            "margin_threshold": None,
        }

    def predict_identity(self, sample_id):
        sample_id = str(sample_id).strip()
        if not sample_id:
            raise ValueError("sample_id is required")
        digest = hashlib.sha256(sample_id.encode("utf-8")).digest()
        forced_unknown = "unknown" in sample_id.casefold()
        is_unknown = forced_unknown or digest[0] % 7 == 0
        if is_unknown:
            predicted_id = None
            confidence = round(_score(self.model_id, sample_id, "unknown", low=.18, high=.49), 4)
            reason = "mock_unknown_threshold"
        else:
            predicted_id = self.labels[digest[1] % len(self.labels)]
            confidence = round(_score(self.model_id, sample_id, "known", low=.68, high=.96), 4)
            reason = "mock_classification_only"
        ranking = [{"label": label, "similarity": confidence if predicted_id == label else
                    round(_score(self.model_id, sample_id, label, high=confidence), 4)}
                   for label in self.labels]
        ranking.sort(key=lambda item: (-item["similarity"], item["label"]))
        return {
            "schema": PREDICTION_SCHEMA,
            "task": "identity",
            "sample_id": sample_id,
            "model_id": self.model_id,
            "model_backend": self.backend,
            "synthetic_prediction": True,
            "predicted_id": predicted_id,
            "confidence": confidence,
            "is_unknown": is_unknown,
            "status": "UNKNOWN" if is_unknown else "MATCHED",
            "reason": reason,
            "ranking": ranking,
            "created_at": _timestamp(),
        }

    def compare(self, reference_id, candidate_ids):
        reference_id = str(reference_id).strip()
        candidates = [str(value).strip() for value in candidate_ids if str(value).strip()]
        if not reference_id:
            raise ValueError("reference_id is required")
        if len(candidates) < 1:
            raise ValueError("At least one candidate is required")
        if len(set(candidates)) != len(candidates):
            raise ValueError("Candidate UUIDs must be unique")
        ranking = []
        for input_order, candidate_id in enumerate(candidates, 1):
            similarity = 1.0 if candidate_id == reference_id else _score(
                self.model_id, reference_id, candidate_id, low=.42, high=.94)
            ranking.append({"candidate_id": candidate_id, "input_order": input_order,
                            "similarity": round(similarity, 4)})
        ranking.sort(key=lambda item: (-item["similarity"], item["candidate_id"]))
        for rank, item in enumerate(ranking, 1):
            item["rank"] = rank
        return {
            "schema": PREDICTION_SCHEMA,
            "task": "reference_comparison",
            "reference_id": reference_id,
            "model_id": self.model_id,
            "model_backend": self.backend,
            "synthetic_prediction": True,
            "status": "RANKED",
            "ranking": ranking,
            "created_at": _timestamp(),
        }


class InferenceCoordinator:
    """One bounded worker; future real inference cannot block acquisition."""

    def __init__(self, predictor=None, event_sink=None, queue_size=16):
        self.predictor = predictor or MockPredictor()
        self.event_sink = event_sink
        self.queue = queue.Queue(queue_size)
        self.results = deque(maxlen=128)
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, name="inference-worker", daemon=True)
        self.started = False
        self.sequence = 0

    def start(self):
        if not self.started:
            self.started = True
            self.thread.start()

    def _submit(self, task, payload):
        if self.stopping.is_set():
            raise RuntimeError("Inference worker is stopping")
        with self.lock:
            self.sequence += 1
            job = {"sequence": self.sequence, "job_id": str(uuid.uuid4()), "task": task,
                   "state": "QUEUED", "submitted_at": _timestamp(), "payload": deepcopy(payload),
                   "result": None, "error": None}
            self.results.append(job)
        try:
            self.queue.put_nowait(job)
        except queue.Full:
            with self.lock:
                job["state"] = "FAILED"
                job["error"] = "Inference queue full"
            raise RuntimeError("Inference queue full")
        return deepcopy(job)

    def submit_identity(self, sample_id):
        sample_id = str(sample_id or "").strip()
        if not sample_id:
            raise ValueError("sample_id is required")
        return self._submit("identity", {"sample_id": sample_id})

    def submit_coffee(self, sample_id, raw_path, model="default"):
        if model not in ("default", "smoothed_v3") or (model == "smoothed_v3" and not COFFEE_ARTIFACT.is_file()):
            raise ValueError("Model cà phê không khả dụng.")
        return self._submit("coffee", {"sample_id": sample_id, "raw_path": str(raw_path), "model": model})

    @staticmethod
    def _check_coffee(path, predict=predict_trial):
        if path is None:
            return {"status": "UNAVAILABLE", "reason": "Cần mẫu thiết bị đã lưu hoàn chỉnh."}
        try:
            with Path(path).open(encoding="utf-8-sig", newline="") as handle:
                return predict(csv.DictReader(handle, strict=True))
        except (OSError, UnicodeError, csv.Error) as error:
            return {"status": "UNAVAILABLE", "reason": f"Không đọc được tín hiệu. {error}"}

    def submit_comparison(self, reference_id, candidate_ids, model="default"):
        reference_id = str(reference_id or "").strip()
        candidates = [str(value).strip() for value in candidate_ids if str(value).strip()]
        if not reference_id:
            raise ValueError("reference_id is required")
        if len(candidates) < 1:
            raise ValueError("At least one candidate is required")
        if len(set(candidates)) != len(candidates):
            raise ValueError("Candidate UUIDs must be unique")
        if (not isinstance(model, str) or model not in COMPARISON_METHODS
                or not hasattr(self.predictor, COMPARISON_METHODS[model])
                or (model == "smoothed_v3" and not IDENTITY_ARTIFACT.is_file())):
            raise ValueError("Model đối sánh không khả dụng.")
        return self._submit("reference_comparison", {
            "reference_id": reference_id, "candidate_ids": candidates, "model": model})

    def snapshot(self, after=0):
        with self.lock:
            return [deepcopy(item) for item in self.results if item["sequence"] > after]

    def describe(self):
        describe = getattr(self.predictor, "describe", None)
        info = deepcopy(describe()) if describe else {
            "model_id": getattr(self.predictor, "model_id", "unknown"),
            "model_backend": getattr(self.predictor, "backend", "UNKNOWN"),
            "synthetic_prediction": None,
        }
        info["smoothed_v3"] = {
            "coffee": COFFEE_ARTIFACT.is_file(),
            "comparison": IDENTITY_ARTIFACT.is_file() and hasattr(self.predictor, "compare_smoothed_v3"),
        }
        return info

    def _run(self):
        while not self.stopping.is_set() or not self.queue.empty():
            try:
                job = self.queue.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                with self.lock:
                    job["state"] = "PREDICTING"
                if job["task"] == "identity":
                    result = self.predictor.predict_identity(job["payload"]["sample_id"])
                elif job["task"] == "coffee":
                    payload = job["payload"]
                    smoothed = payload["model"] == "smoothed_v3"
                    coffee = (self._check_coffee(payload["raw_path"], predict_smoothed_coffee)
                              if smoothed else self._check_coffee(payload["raw_path"]))
                    result = {
                        "schema": PREDICTION_SCHEMA, "task": "coffee",
                        "sample_id": payload["sample_id"], "model_backend": "COFFEE_LOGISTIC",
                        **coffee, "created_at": _timestamp(),
                    }
                    if result.get("model"):
                        result["model_id"] = result["model"]
                else:
                    compare = getattr(self.predictor, COMPARISON_METHODS[job["payload"]["model"]])
                    result = compare(
                        job["payload"]["reference_id"], job["payload"]["candidate_ids"])
                with self.lock:
                    job["state"] = "SUCCEEDED"
                    job["result"] = result
                    job["completed_at"] = _timestamp()
                if self.event_sink:
                    try:
                        self.event_sink(deepcopy(result))
                    except Exception:
                        # Acquisition safety and the result cache do not depend on optional event logging.
                        pass
            except Exception as error:
                with self.lock:
                    job["state"] = "FAILED"
                    job["error"] = f"{type(error).__name__}: {error}"
                    job["completed_at"] = _timestamp()
            finally:
                self.queue.task_done()

    def close(self, timeout=2):
        self.stopping.set()
        if self.started:
            self.thread.join(timeout)
