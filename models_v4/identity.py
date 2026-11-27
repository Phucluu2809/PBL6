"""Similarity fusion with one frozen ResCNN64 encoder."""

import math

import torch

from models_v2.learned import BaselineCorrector, checkpoint_hash, inputs
from models_v3.identity import filter_exposure
from models_v4 import IDENTITY_ARTIFACT


def encode(encoder, baseline, exposure, corrected, filtered, method):
    smoothed = torch.stack([filter_exposure(item, method) for item in exposure])
    with torch.inference_mode():
        return (
            encoder.model.encode(exposure),
            encoder.model.encode(corrected(baseline, exposure)),
            encoder.model.encode(filtered(baseline, smoothed)),
        )


def fuse(views, weights):
    # Concatenation with sqrt weights gives the weighted sum of the three
    # cosine scores when the component embeddings have unit norm.
    return torch.cat([vector * math.sqrt(weight)
                      for vector, weight in zip(views, weights, strict=True)], dim=-1)


def load(encoder):
    saved = torch.load(IDENTITY_ARTIFACT, map_location="cpu", weights_only=True)
    if (saved["schema"] != 1
            or saved["encoder_sha256"] != checkpoint_hash(encoder.model_dir / "model.pt")
            or saved["settings_sha256"] != checkpoint_hash(encoder.model_dir / "model.json")):
        raise ValueError("Checkpoint V4 không tương thích với ResCNN64 hiện tại.")
    models = []
    for branch in ("corrected", "filtered"):
        model = BaselineCorrector(**saved[branch]["options"])
        model.load_state_dict(saved[branch]["weights"], strict=True)
        models.append(model.eval())
    return saved, *models


def compare(encoder, reference_id, candidate_ids):
    saved, corrected, filtered = load(encoder)

    def embedding(sample_id):
        baseline, exposure, info = inputs(encoder.resolver.resolve(sample_id), encoder)
        views = encode(encoder, baseline[None], exposure[None], corrected, filtered, saved["smoothing"])
        return fuse(views, saved["fusion_weights"]), info

    result = encoder._compare(reference_id, candidate_ids, embedding)
    result.update(model_id=f"{encoder.model_id}:v4-fusion", model_backend="RESCNN64_FUSION_V4",
                  experimental=True, embedding_dims=192, fusion_weights=saved["fusion_weights"],
                  smoothing=saved["smoothing"], preprocessing_mode="fusion_v4")
    return result
