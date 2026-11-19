"""Read-only ResCNN64 inference for finalized RoboNose dataset-v1 trials.

The implementation mirrors the preprocessing and architecture shipped with
the imported training artifact.  It deliberately refuses to invent missing
samples, relax validity flags, or claim an identity before independent
Unknown thresholds have been supplied.
"""
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import uuid

import numpy as np

from .inference import PREDICTION_SCHEMA
from .signals import CHANNELS, flag as _flag, validity


MODEL_CHANNELS = tuple((key, sensor) for key, _, _, sensor in CHANNELS if key in {
    "tgs2602_voltage_v", "mq3_1_voltage_v", "mq135_2_voltage_v",
    "mq3_2_voltage_v", "gas_resistance_ohm", "humidity_pct",
})
PHASE_COUNTS = {"BASELINE": 60, "EXPOSURE": 120}
DRIFT_LIMIT = 5.0


def _timestamp():
    return datetime.now(timezone.utc).astimezone().isoformat()


def _validity(row, key, sensor):
    return validity(row, key, sensor, modern=True)


def _phase_values(rows, phase, count):
    selected = [row for row in rows if row.get("phase") == phase]
    if len(selected) != count:
        raise ValueError(f"{phase}: expected {count} rows, found {len(selected)}")
    times = np.asarray([float(row["mono_s"]) for row in selected], dtype=np.float64)
    if not np.isfinite(times).all() or not np.all(np.abs(np.diff(times) - 1) <= 0.1):
        raise ValueError(f"{phase}: timestamps are not uniformly sampled at 1 Hz")
    return selected, times


def _values(rows, phase):
    output = []
    for key, sensor in MODEL_CHANNELS:
        if any(_validity(row, key, sensor) is not True for row in rows):
            raise ValueError(f"{phase}: {key} has missing/invalid/unknown data")
        output.append([float(row[key]) for row in rows])
    result = np.asarray(output, dtype=np.float64)
    if np.any(result[:5] <= 0) or np.any((result[5] < 0) | (result[5] > 100)):
        raise ValueError(f"{phase}: signal outside the model's physical domain")
    return result


def _unstable(trace, times):
    centered = times - times.mean()
    denominator = np.dot(centered, centered)
    if denominator <= 0:
        raise ValueError("Cannot calculate baseline drift from identical timestamps")
    slope = (trace @ centered) / denominator
    median = np.median(trace, axis=1)
    return np.maximum(abs(slope) * 60, np.ptp(trace, axis=1)) * 100 / median


def _check_compatibility(metadata, expected):
    if not expected:
        return
    config = metadata.get("config")
    if not isinstance(config, dict):
        raise ValueError("Model compatibility cannot be verified: metadata.config is missing")
    device = config.get("device_configuration")
    if not isinstance(device, dict):
        device = {}
    actual = {
        "schema": metadata.get("schema"),
        "sampling_hz": config.get("sampling_hz"),
        "pump_pwm_pct": config.get("pump_pwm_pct"),
        "channel_map": config.get("channel_map"),
        "ads_lsb_v": config.get("ads_lsb_v", device.get("ads_lsb_v")),
        "divider_factor": config.get("divider_factor", device.get("divider_factor")),
        "profile_id": device.get("profile_id", metadata.get("profile_id")),
        "heater_requested_c": device.get("heater_requested_c"),
        "heater_requested_ms": device.get("heater_requested_ms"),
        "os_t_applied": device.get("os_t_applied"),
        "os_h_applied": device.get("os_h_applied"),
        "os_p_applied": device.get("os_p_applied"),
    }
    mismatches = [key for key, value in expected.items() if actual.get(key) != value]
    if mismatches:
        details = ", ".join(f"{key}={actual.get(key)!r} (expected {expected[key]!r})"
                            for key in mismatches)
        raise ValueError(f"Trial is incompatible with the model artifact: {details}")


def prepare_trial(folder, *, baseline_warn=False, compatibility=None):
    """Convert one immutable trial export to the model's (6, 120) tensor."""
    folder = Path(folder).resolve(strict=True)
    raw = folder / "raw.csv"
    metadata_path = folder / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    if not isinstance(metadata, dict):
        raise ValueError("metadata.json must contain an object")
    with raw.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, strict=True))
    schema = metadata.get("schema") or (rows[0].get("schema") if rows else None)
    if schema != "robonose.dataset.v1" or metadata.get("status") != "COMPLETE":
        raise ValueError(f"Unsupported schema/status: {schema}/{metadata.get('status')}")
    if not all(metadata.get(key) for key in ("trial_id", "session_id", "started_at")):
        raise ValueError("metadata is missing trial_id, session_id, or started_at")
    _check_compatibility(metadata, compatibility)

    baseline, baseline_times = _phase_values(rows, "BASELINE", PHASE_COUNTS["BASELINE"])
    exposure, exposure_times = _phase_values(rows, "EXPOSURE", PHASE_COUNTS["EXPOSURE"])
    period = np.asarray([float(row["mono_s"]) for row in rows], dtype=np.float64)
    if not np.isfinite(period).all() or np.any(np.diff(period) <= 0):
        raise ValueError("Trial timestamps are not strictly increasing")
    baseline_values = _values(baseline, "BASELINE")
    exposure_values = _values(exposure, "EXPOSURE")
    if np.any(np.ptp(exposure_values[:5], axis=1) == 0):
        raise ValueError("A gas channel is constant throughout EXPOSURE")

    reference = np.median(baseline_values[:, -30:], axis=1)
    drift = _unstable(baseline_values[:5, -30:], baseline_times[-30:])
    warnings = []
    if np.any(drift > DRIFT_LIMIT):
        message = "Baseline drift/range exceeds 5% in the final 30 seconds"
        if not baseline_warn:
            raise ValueError(message)
        warnings.append(message)
    pre = [row for row, mono in zip(rows, period)
           if exposure_times[0] - 30 <= mono < exposure_times[0]
           and row.get("phase") in ("BASELINE", "WAIT_EXPOSURE")]
    if len(pre) >= 24:
        try:
            before = _values(pre, "PRE_EXPOSURE")
            before_times = np.asarray([float(row["mono_s"]) for row in pre], dtype=np.float64)
            if np.any(_unstable(before[:5], before_times) > DRIFT_LIMIT):
                warnings.append("Signals are still drifting immediately before EXPOSURE")
            if np.any(abs(np.median(before[:5], axis=1) / reference[:5] - 1) > 0.05):
                warnings.append("Pre-exposure signal differs by more than 5% from baseline")
        except ValueError as error:
            warnings.append(str(error))
    if any(_flag(row.get("context_straddled")) is True for row in exposure):
        warnings.append("An EXPOSURE row straddles a context transition")

    delta = exposure_values - reference[:, None]
    delta[4] = np.log(exposure_values[4] / reference[4])
    info = {
        "trial_id": metadata["trial_id"],
        "session_id": metadata["session_id"],
        "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "warnings": warnings,
        "baseline_drift_pct": dict(zip((key for key, _ in MODEL_CHANNELS[:5]), drift.round(3).tolist())),
    }
    return delta.astype(np.float32), info


class TrialResolver:
    """Resolve UUIDs only inside explicitly configured read-only roots."""
    def __init__(self, roots):
        self.roots = tuple(Path(root).resolve() for root in roots)
        if not self.roots:
            raise ValueError("At least one sample root is required")

    def resolve(self, trial_id):
        try:
            wanted = str(uuid.UUID(str(trial_id).strip()))
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError("sample_id must be a full trial UUID") from error
        matches = []
        for root in self.roots:
            if not root.is_dir():
                continue
            for metadata_path in root.rglob("metadata.json"):
                folder = metadata_path.parent.resolve()
                try:
                    folder.relative_to(root)
                except ValueError:
                    continue
                if not (folder / "raw.csv").is_file():
                    continue
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
                except (OSError, UnicodeError, ValueError):
                    continue
                if isinstance(metadata, dict) and metadata.get("trial_id") == wanted:
                    matches.append(folder)
        unique = tuple(dict.fromkeys(matches))
        if not unique:
            raise FileNotFoundError(f"Trial UUID not found in configured sample roots: {wanted}")
        if len(unique) > 1:
            raise ValueError(f"Trial UUID is duplicated across sample roots: {wanted}")
        return unique[0]


def _build_rescnn64(torch, classes):
    nn = torch.nn
    functional = torch.nn.functional

    class ResidualBlock(nn.Module):
        def __init__(self, in_channels, out_channels, kernel, stride):
            super().__init__()
            self.body = nn.Sequential(
                nn.Conv1d(in_channels, out_channels, kernel, stride, kernel // 2, bias=False),
                nn.GroupNorm(8, out_channels), nn.GELU(),
                nn.Conv1d(out_channels, out_channels, kernel, padding=kernel // 2, bias=False),
                nn.GroupNorm(8, out_channels),
            )
            self.skip = (nn.Identity() if in_channels == out_channels and stride == 1 else
                         nn.Conv1d(in_channels, out_channels, 1, stride, bias=False))

        def forward(self, value):
            return functional.gelu(self.body(value) + self.skip(value))

    class ResCNN64(nn.Module):
        def __init__(self):
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv1d(6, 32, 7, padding=3, bias=False), nn.GroupNorm(8, 32), nn.GELU(),
                ResidualBlock(32, 32, 5, 1),
                ResidualBlock(32, 64, 5, 2),
                ResidualBlock(64, 128, 3, 2),
            )
            self.embedding = nn.Sequential(
                nn.Linear(256, 128), nn.GELU(), nn.Dropout(0.2), nn.Linear(128, 64))
            self.classifier = nn.Linear(64, classes, bias=False)

        def encode(self, value):
            features = self.features(value)
            pooled = torch.cat((features.mean(dim=-1), features.amax(dim=-1)), dim=1)
            return functional.normalize(self.embedding(pooled), dim=1)

        def forward(self, value):
            return 12 * (self.encode(value) @ functional.normalize(self.classifier.weight, dim=1).T)

    return ResCNN64()


class ResCNN64Predictor:
    """One encoder for identity-gallery matching and X-to-A–E ranking."""
    backend = "RESCNN64_TORCH"

    def __init__(self, model_dir, sample_roots, *, similarity_threshold=None,
                 margin_threshold=None, torch_module=None):
        if (similarity_threshold is None) != (margin_threshold is None):
            raise ValueError("similarity_threshold and margin_threshold must be supplied together")
        if similarity_threshold is not None and not -1 <= float(similarity_threshold) <= 1:
            raise ValueError("similarity_threshold must be in [-1, 1]")
        if margin_threshold is not None and not 0 <= float(margin_threshold) <= 2:
            raise ValueError("margin_threshold must be in [0, 2]")
        self.model_dir = Path(model_dir).resolve(strict=True)
        self.similarity_threshold = None if similarity_threshold is None else float(similarity_threshold)
        self.margin_threshold = None if margin_threshold is None else float(margin_threshold)
        self.resolver = TrialResolver(sample_roots)
        self._verify_artifact()
        self.settings = json.loads((self.model_dir / "model.json").read_text(encoding="utf-8"))
        expected_channels = [key for key, _ in MODEL_CHANNELS]
        if (self.settings.get("version") != 1 or self.settings.get("architecture") != "rescnn64"
                or self.settings.get("channels") != expected_channels):
            raise ValueError("Model metadata is incompatible with the ResCNN64 dataset-v1 adapter")
        self.labels = tuple(str(label) for label in self.settings.get("labels", ()))
        if len(self.labels) < 2 or len(set(self.labels)) != len(self.labels):
            raise ValueError("Model labels must contain at least two unique identities")
        self.center = np.asarray(self.settings["center"], dtype=np.float32)[:, None]
        self.scale = np.asarray(self.settings["scale"], dtype=np.float32)[:, None]
        if self.center.shape != (6, 1) or self.scale.shape != (6, 1) or np.any(self.scale <= 0):
            raise ValueError("Model center/scale are invalid")
        if torch_module is None:
            try:
                import torch as torch_module
            except ImportError as error:
                raise RuntimeError("PyTorch is required for the selected ResCNN64 model backend") from error
        self.torch = torch_module
        try:
            checkpoint = self.torch.load(
                self.model_dir / "model.pt", map_location="cpu", weights_only=True)
        except TypeError as error:
            raise RuntimeError("This backend requires torch.load(..., weights_only=True)") from error
        if not isinstance(checkpoint, dict) or set(checkpoint) < {"weights", "gallery"}:
            raise ValueError("model.pt does not contain weights and gallery")
        self.model = _build_rescnn64(self.torch, len(self.labels))
        self.model.load_state_dict(checkpoint["weights"], strict=True)
        self.model.eval()
        self.gallery = checkpoint["gallery"].detach().to("cpu")
        if tuple(self.gallery.shape) != (len(self.labels), 64) or not self.torch.isfinite(self.gallery).all():
            raise ValueError("Model gallery has an invalid shape or non-finite values")
        self.model_id = self.artifact.get("model_id", f"rescnn64:{self.model_dir.name}")
        self.cache = {}

    def _verify_artifact(self):
        artifact_path = self.model_dir / "artifact.json"
        self.artifact = (json.loads(artifact_path.read_text(encoding="utf-8"))
                         if artifact_path.is_file() else {})
        for name, expected in self.artifact.get("files", {}).items():
            path = self.model_dir / name
            if not path.is_file():
                raise FileNotFoundError(path)
            actual = hashlib.sha256(path.read_bytes()).hexdigest().upper()
            if actual != str(expected).upper():
                raise ValueError(f"Artifact hash mismatch: {name}")

    @property
    def calibrated(self):
        return self.similarity_threshold is not None and self.margin_threshold is not None

    def describe(self):
        return {
            "model_id": self.model_id,
            "model_backend": self.backend,
            "synthetic_prediction": False,
            "labels": list(self.labels),
            "unknown_calibrated": self.calibrated,
            "similarity_threshold": self.similarity_threshold,
            "margin_threshold": self.margin_threshold,
            "sample_roots": [str(root) for root in self.resolver.roots],
        }

    def _embedding(self, sample_id):
        folder = self.resolver.resolve(sample_id)
        tensor, info = prepare_trial(
            folder, baseline_warn=self.settings.get("baseline_warn", False),
            compatibility=self.artifact.get("compatibility"))
        cached = self.cache.get(info["raw_sha256"])
        if cached is not None:
            return cached, info
        scaled = (tensor - self.center) / self.scale
        with self.torch.inference_mode():
            vector = self.model.encode(self.torch.as_tensor(scaled[None], dtype=self.torch.float32))
        vector = vector.detach().to("cpu")
        self.cache[info["raw_sha256"]] = vector
        return vector, info

    def _rank_gallery(self, vector):
        with self.torch.inference_mode():
            scores = (vector @ self.gallery.T).clamp(-1, 1).flatten().tolist()
        ranking = sorted(({"label": label, "similarity": round(float(score), 6)}
                          for label, score in zip(self.labels, scores)),
                         key=lambda item: (-item["similarity"], item["label"]))
        for rank, item in enumerate(ranking, 1):
            item["rank"] = rank
        return ranking

    def predict_identity(self, sample_id):
        sample_id = str(uuid.UUID(str(sample_id).strip()))
        vector, info = self._embedding(sample_id)
        ranking = self._rank_gallery(vector)
        best = ranking[0]
        margin = best["similarity"] - ranking[1]["similarity"]
        if not self.calibrated:
            status, predicted_id, is_unknown, reason = (
                "RANKED_ONLY", None, None, "unknown_thresholds_not_calibrated")
        else:
            accepted = (best["similarity"] >= self.similarity_threshold
                        and margin >= self.margin_threshold)
            status = "MATCHED" if accepted else "UNKNOWN"
            predicted_id = best["label"] if accepted else None
            is_unknown = not accepted
            reason = "thresholds_accepted" if accepted else "thresholds_rejected"
        return {
            "schema": PREDICTION_SCHEMA,
            "task": "identity",
            "sample_id": sample_id,
            "model_id": self.model_id,
            "model_backend": self.backend,
            "synthetic_prediction": False,
            "predicted_id": predicted_id,
            "top_candidate": best["label"],
            "similarity": best["similarity"],
            "margin": round(margin, 6),
            "similarity_threshold": self.similarity_threshold,
            "margin_threshold": self.margin_threshold,
            "is_unknown": is_unknown,
            "status": status,
            "reason": reason,
            "ranking": ranking,
            "warnings": info["warnings"],
            "raw_sha256": info["raw_sha256"],
            "embedding_dims": 64,
            "created_at": _timestamp(),
        }

    def compare(self, reference_id, candidate_ids):
        reference_id = str(uuid.UUID(str(reference_id).strip()))
        candidates = [str(uuid.UUID(str(value).strip())) for value in candidate_ids]
        if len(candidates) < 1:
            raise ValueError("At least one candidate is required")
        if len(candidates) > 4:
            raise ValueError("At most four candidates are supported")
        if len(set(candidates)) != len(candidates):
            raise ValueError("Candidate UUIDs must be unique")
        reference, reference_info = self._embedding(reference_id)
        ranking = []
        for input_order, candidate_id in enumerate(candidates, 1):
            candidate, info = self._embedding(candidate_id)
            with self.torch.inference_mode():
                similarity = (reference @ candidate.T).clamp(-1, 1).item()
            ranking.append({
                "candidate_id": candidate_id,
                "input_order": input_order,
                "similarity": round(float(similarity), 6),
                "warnings": info["warnings"],
            })
        ranking.sort(key=lambda item: (-item["similarity"], item["candidate_id"]))
        for rank, item in enumerate(ranking, 1):
            item["rank"] = rank
        return {
            "schema": PREDICTION_SCHEMA,
            "task": "reference_comparison",
            "reference_id": reference_id,
            "model_id": self.model_id,
            "model_backend": self.backend,
            "synthetic_prediction": False,
            "status": "RANKED",
            "ranking": ranking,
            "reference_warnings": reference_info["warnings"],
            "embedding_dims": 64,
            "created_at": _timestamp(),
        }
