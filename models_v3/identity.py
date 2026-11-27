"""ResCNN64 with an exposure filter and a separately retrained baseline corrector."""

import torch

from models_v2.learned import inputs as v2_inputs, load_corrector
from models_v3 import IDENTITY_ARTIFACT as ARTIFACT
from models_v3.smoothing import smooth


def filter_exposure(exposure, method):
    # V2 QC and fixed baseline normalizations have already run. A linear filter
    # here preserves their reference and avoids mixing baseline with exposure.
    return exposure.new_tensor([smooth(channel.tolist(), method) for channel in exposure])


def compare(encoder, reference_id, candidate_ids):
    corrector = load_corrector(encoder, ARTIFACT)
    method = corrector.version.removeprefix("v3-smoothed-")

    def embedding(sample_id):
        baseline, exposure, info = v2_inputs(encoder.resolver.resolve(sample_id), encoder)
        with torch.inference_mode():
            corrected = corrector(baseline[None], filter_exposure(exposure, method)[None])
            return encoder.model.encode(corrected), info

    result = encoder._compare(reference_id, candidate_ids, embedding)
    result.update(model_id=f"{encoder.model_id}:{corrector.version}",
                  model_backend="RESCNN64_SMOOTHED_V3", experimental=True,
                  preprocessing_mode="smoothed_v3", smoothing=method, corrector_version=corrector.version)
    return result
