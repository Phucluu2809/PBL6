"""Trainable baseline-to-exposure correction for the frozen ResCNN64 encoder."""

import csv
import hashlib
from pathlib import Path

import numpy as np
import torch
from torch import nn

from robonose_s3.rescnn64 import MODEL_CHANNELS, prepare_trial


CHECKPOINT = Path(__file__).with_name("baseline_corrector.pt")
GROUPED_CHECKPOINT = Path(__file__).with_name("baseline_corrector_grouped.pt")


class BaselineCorrector(nn.Module):
    """Predict bounded offset and slope per channel from all 60 baseline points."""

    def __init__(self, gain=1.0, relative_context=False):
        super().__init__()
        self.gain = gain
        self.relative_context = relative_context
        self.register_buffer("center", torch.zeros(36))
        self.register_buffer("scale", torch.ones(36))
        self.register_buffer("time", torch.linspace(-1, 1, 120))
        self.network = nn.Sequential(nn.Linear(36, 16), nn.Tanh(), nn.Linear(16, 12))
        nn.init.zeros_(self.network[-1].weight)
        nn.init.zeros_(self.network[-1].bias)

    def context(self, baseline):
        if not self.relative_context:
            return baseline
        windows = baseline.unflatten(-1, (6, 6))
        return (windows - windows.mean(dim=-1, keepdim=True)).flatten(-2)

    def forward(self, baseline, exposure):
        features = ((self.context(baseline) - self.center) / self.scale).clamp(-4, 4)
        offset, slope = (.5 * self.network(features).tanh()).unsqueeze(-1).chunk(2, dim=1)
        return exposure + self.gain * (offset + slope * self.time)


def checkpoint_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(folder, encoder):
    exposure, info = prepare_trial(
        folder, baseline_warn=encoder.settings.get("baseline_warn", False),
        compatibility=encoder.artifact.get("compatibility"))
    with (Path(folder) / "raw.csv").open(encoding="utf-8-sig", newline="") as handle:
        baseline = [row for row in csv.DictReader(handle, strict=True) if row["phase"] == "BASELINE"]
    values = np.asarray([[float(row[key]) for row in baseline]
                         for key, _ in MODEL_CHANNELS], dtype=np.float64)
    gas_index = next(i for i, (key, _) in enumerate(MODEL_CHANNELS) if key == "gas_resistance_ohm")
    values[gas_index] = np.log(values[gas_index])
    # Six ten-second windows capture the full trace and its evolution per channel.
    features = values.reshape(6, 6, 10).mean(axis=-1).astype(np.float32).reshape(-1)
    scaled = (exposure - encoder.center) / encoder.scale
    return torch.from_numpy(features), torch.from_numpy(scaled), info


def load_corrector(encoder, path=None):
    path = path or (GROUPED_CHECKPOINT if GROUPED_CHECKPOINT.is_file() else CHECKPOINT)
    state = torch.load(path, map_location="cpu", weights_only=True)
    if (state["schema"] != 1
            or state["encoder_sha256"] != checkpoint_hash(encoder.model_dir / "model.pt")
            or state["settings_sha256"] != checkpoint_hash(encoder.model_dir / "model.json")):
        raise ValueError("Bộ hiệu chỉnh đã học cần đúng checkpoint và chuẩn hóa ResCNN64 gốc.")
    model = BaselineCorrector(**state.get("corrector_options", {}))
    model.load_state_dict(state["weights"], strict=True)
    model.version = state.get("version", "v2-initial")
    return model.eval()


def compare(encoder, reference_id, candidate_ids):
    corrector = load_corrector(encoder)

    def embedding(sample_id):
        baseline, exposure, info = inputs(encoder.resolver.resolve(sample_id), encoder)
        with torch.inference_mode():
            vector = encoder.model.encode(corrector(baseline[None], exposure[None]))
        return vector, info

    result = encoder._compare(reference_id, candidate_ids, embedding)
    result.update(model_id=f"{encoder.model_id}:{corrector.version}",
                  model_backend="RESCNN64_LEARNED_BASELINE_V2",
                  experimental=True, preprocessing_mode="learned_baseline",
                  corrector_version=corrector.version)
    return result
