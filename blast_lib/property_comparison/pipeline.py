"""Build, plot, and validate comparison outputs."""

from __future__ import annotations

from blast_lib.property_comparison.build import build_all
from blast_lib.property_comparison.config import ComparisonConfig
from blast_lib.property_comparison.plot import plot_all
from blast_lib.property_comparison.validate import validate_outputs


def build_outputs(config: ComparisonConfig) -> None:
    build_all(config)


def plot_outputs(config: ComparisonConfig) -> None:
    plot_all(config)


def validate_outputs_strict(config: ComparisonConfig) -> None:
    errors = validate_outputs(config)
    if errors:
        raise ValueError("Validation failed:\n" + "\n".join(errors))
