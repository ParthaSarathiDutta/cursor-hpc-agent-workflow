"""Data models for read-only result analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blast_lib.result_analysis.phonon_parser import PhononStageResult


@dataclass
class PropertyResult:
    property_name: str
    target: float | None
    predicted: float | None
    absolute_error: float | None
    percent_error: float | None
    unit: str
    category: str  # lattice | cohesive_energy | elastic


@dataclass
class SetAnalysisResult:
    iteration: int
    final_obj: float | None
    properties: list[PropertyResult]
    source_file: str
    input_params: str = ""
    phonon: PhononStageResult | None = None


@dataclass
class ComparisonResult:
    sets: list[SetAnalysisResult]
    property_names: list[str]
    error_matrix: list[list[float | None]]  # rows=properties, cols=sets; % or abs
    heatmap_path: str | None = None
    heatmap_metric: str = "percent_error"
