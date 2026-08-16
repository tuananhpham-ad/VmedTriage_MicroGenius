"""Build the demo-only Vietnamese triage dataset for five symptom groups."""

from .builder import build_dataset
from .validator import validate_dataset

__all__ = ["build_dataset", "validate_dataset"]
