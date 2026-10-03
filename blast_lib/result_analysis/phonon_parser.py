"""Parse phonon stage data from ho.report trial stage_lines (read-only)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from blast_lib.result_analysis.metrics import absolute_error, percent_error
from blast_lib.trial_details import parse_property_blocks, _score_block_lines

_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
_PHONON_COMPONENTS = ("neg", "gap", "gap_lo", "shape", "ceil", "gamma")


@dataclass
class PhononComponentMetrics:
    obj: float | None = None
    mae_pct: float | None = None
    max_ae_pct: float | None = None
    npt: int | None = None


@dataclass
class PhononStageResult:
    checkpoint_metric: str | None = None
    checkpoint_threshold: float | None = None
    checkpoint_actual: str | None = None
    passed: bool | None = None
    components: dict[str, PhononComponentMetrics] = field(default_factory=dict)
    nneg_t: float | None = None
    nneg_p: float | None = None
    gap_t: float | None = None
    gap_p: float | None = None
    gap_lo_t: float | None = None
    gap_lo_p: float | None = None
    ceil_t: list[float] = field(default_factory=list)
    ceil_p: list[float] = field(default_factory=list)
    gamma_t: list[float] = field(default_factory=list)
    gamma_p: list[float] = field(default_factory=list)
    band_shape_scores: list[tuple[int, int, float, float]] = field(default_factory=list)


def _parse_scalar(block: list[str], key: str) -> float | None:
    marker = f"| {key} ="
    for line in block:
        if marker not in line:
            continue
        tail = line.split(marker, 1)[1].strip()
        nums = _FLOAT_RE.findall(tail.split("±")[0])
        if nums:
            return float(nums[0])
    return None


def _parse_vector(block: list[str], key: str) -> list[float]:
    marker = f"| {key} ="
    start: int | None = None
    for i, line in enumerate(block):
        if marker in line:
            start = i
            break
    if start is None:
        return []

    parts: list[str] = [block[start].split(marker, 1)[1]]
    if "[" in parts[0] and "]" not in parts[0]:
        for line in block[start + 1 :]:
            if not line.strip().startswith("|"):
                break
            if any(x in line for x in ("| gap_", "| ceil_", "| gamma_", "| Nneg_", "score:", "return")):
                if "|" in line and "=" in line and key not in line:
                    break
            parts.append(line.lstrip("| "))
            if "]" in line:
                break

    blob = " ".join(parts).split("±")[0].split("(")[0]
    return [float(x) for x in _FLOAT_RE.findall(blob)]


def _parse_checkpoint(checkpoints: list[dict]) -> tuple[str | None, float | None, str | None, bool | None]:
    if not checkpoints:
        return None, None, None, None
    cp = checkpoints[0]
    rule = cp.get("rule") or ""
    actual = cp.get("actual") or ""
    passed = cp.get("result") == "pass"
    metric: str | None = None
    threshold: float | None = None
    m = re.match(r"^(.+?)\s*<=\s*([\d.]+)\s*$", rule.strip())
    if m:
        metric = m.group(1).strip()
        threshold = float(m.group(2))
    return metric, threshold, actual, passed


def _component_metrics(flat: dict) -> dict[str, PhononComponentMetrics]:
    out: dict[str, PhononComponentMetrics] = {}
    for name in _PHONON_COMPONENTS:
        obj = flat.get(f"{name}.obj")
        if obj is None and flat.get(f"{name}.MAE%") is None:
            continue
        npt_raw = flat.get(f"{name}.Npt")
        out[name] = PhononComponentMetrics(
            obj=float(obj) if obj is not None else None,
            mae_pct=float(flat[f"{name}.MAE%"]) if f"{name}.MAE%" in flat else None,
            max_ae_pct=float(flat[f"{name}.maxAE%"]) if f"{name}.maxAE%" in flat else None,
            npt=int(npt_raw) if npt_raw is not None else None,
        )
    return out


def _parse_band_shape_scores(block: list[str]) -> list[tuple[int, int, float, float]]:
    """Internal shape_score table (not physical frequencies)."""
    rows: list[tuple[int, int, float, float]] = []
    in_table = False
    for line in block:
        if "band_t band_p" in line.lower():
            in_table = True
            continue
        if not in_table:
            continue
        if not line.strip().startswith("|"):
            break
        if "ceil_" in line or "gamma_" in line or line.strip().lower().startswith("| return"):
            break
        nums = _FLOAT_RE.findall(line)
        if len(nums) >= 4:
            rows.append((int(float(nums[0])), int(float(nums[1])), float(nums[2]), float(nums[3])))
    return rows


def phonon_from_trial(trial: dict) -> PhononStageResult | None:
    """Build phonon summary from one trial; None if no phonon block."""
    lines = trial.get("stage_lines") or []
    blocks = [b for b in parse_property_blocks(lines) if b.get("stage") == "phonon" and not b.get("missing")]
    if not blocks:
        return None

    last = blocks[-1]
    flat = last.get("metrics") or {}
    block_lines = _score_block_lines(lines, "phonon")
    if not block_lines:
        return None

    metric, threshold, actual, passed = _parse_checkpoint(last.get("checkpoints") or [])

    return PhononStageResult(
        checkpoint_metric=metric,
        checkpoint_threshold=threshold,
        checkpoint_actual=actual,
        passed=passed,
        components=_component_metrics(flat),
        nneg_t=_parse_scalar(block_lines, "Nneg_t"),
        nneg_p=_parse_scalar(block_lines, "Nneg_p"),
        gap_t=_parse_scalar(block_lines, "gap_t"),
        gap_p=_parse_scalar(block_lines, "gap_p"),
        gap_lo_t=_parse_scalar(block_lines, "gap_lo_t"),
        gap_lo_p=_parse_scalar(block_lines, "gap_lo_p"),
        ceil_t=_parse_vector(block_lines, "ceil_t"),
        ceil_p=_parse_vector(block_lines, "ceil_p"),
        gamma_t=_parse_vector(block_lines, "gamma_t"),
        gamma_p=_parse_vector(block_lines, "gamma_p"),
        band_shape_scores=_parse_band_shape_scores(block_lines),
    )


def format_phonon_sections(phonon: PhononStageResult) -> str:
    """Section A (component scores) + Section B (6-point checkpoint-frequency comparison)."""
    lines: list[str] = []
    lines.append("")
    lines.append("## Phonon score summary")
    lines.append("Component | Objective | MAE % | MaxAE % | Npt")
    lines.append("---|---|---|---|---")
    for name in _PHONON_COMPONENTS:
        comp = phonon.components.get(name)
        if not comp:
            lines.append(f"{name} | — | — | — | —")
            continue
        lines.append(
            f"{name} | {comp.obj if comp.obj is not None else '—'} | "
            f"{comp.mae_pct if comp.mae_pct is not None else '—'} | "
            f"{comp.max_ae_pct if comp.max_ae_pct is not None else '—'} | "
            f"{comp.npt if comp.npt is not None else '—'}"
        )

    lines.append("")
    lines.append("Checkpoint metric | Threshold | Actual | Result")
    lines.append("---|---|---|---")
    pass_label = "PASS" if phonon.passed is True else "FAIL" if phonon.passed is False else "—"
    lines.append(
        f"{phonon.checkpoint_metric or '—'} | "
        f"{phonon.checkpoint_threshold if phonon.checkpoint_threshold is not None else '—'} | "
        f"{phonon.checkpoint_actual or '—'} | {pass_label}"
    )

    lines.append("")
    lines.append("## 6-point phonon checkpoint-frequency comparison (not full dispersion)")
    lines.append("Property | Target | Predicted | Absolute Error | Error % | Unit")
    lines.append("---|---|---|---|---|---")

    def row(name: str, t: float | None, p: float | None, unit: str) -> None:
        if t is None and p is None:
            return
        ae = absolute_error(t, p) if t is not None and p is not None else None
        pe = percent_error(t, p) if t is not None and p is not None else None
        pe_s = "N/A" if pe is None else f"{pe:.4f}"
        lines.append(
            f"{name} | {t if t is not None else '—'} | {p if p is not None else '—'} | "
            f"{ae if ae is not None else '—'} | {pe_s} | {unit}"
        )

    row("Nneg", phonon.nneg_t, phonon.nneg_p, "count")
    row("gap", phonon.gap_t, phonon.gap_p, "THz")
    row("gap_lo", phonon.gap_lo_t, phonon.gap_lo_p, "THz")
    for i in range(6):
        t = phonon.ceil_t[i] if i < len(phonon.ceil_t) else None
        p = phonon.ceil_p[i] if i < len(phonon.ceil_p) else None
        row(f"ceil_{i}", t, p, "THz")
    for i in range(6):
        t = phonon.gamma_t[i] if i < len(phonon.gamma_t) else None
        p = phonon.gamma_p[i] if i < len(phonon.gamma_p) else None
        row(f"gamma_{i}", t, p, "THz")

    if phonon.band_shape_scores:
        lines.append("")
        lines.append("## Internal phonon shape metric (not physical frequencies)")
        lines.append("band_t | band_p | shape_score | weight")
        lines.append("---|---|---|---")
        for bt, bp, sc, wt in phonon.band_shape_scores:
            lines.append(f"{bt} | {bp} | {sc} | {wt}")

    return "\n".join(lines)
