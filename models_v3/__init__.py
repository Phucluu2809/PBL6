"""Offline trial models with light, phase-local smoothing."""

from pathlib import Path


DIRECTORY = Path(__file__).parent
IDENTITY_ARTIFACT = DIRECTORY / "identity_corrector.pt"
COFFEE_ARTIFACT = DIRECTORY / "coffee_model.json"
