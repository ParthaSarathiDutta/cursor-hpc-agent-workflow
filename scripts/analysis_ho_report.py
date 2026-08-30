#!/usr/bin/env python3
"""
Parse BLAST ho.report and plot objective score vs iteration.

Default report path: reports/ho.report (relative to --workdir).

Example (Perlmutter, psd env has matplotlib):
  python scripts/analysis_ho_report.py --workdir /path/to/run
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from blast_lib.parser import parse_ho_report


def write_csv(trials: list[dict], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["iteration", "score", "status", "reason"]
        )
        writer.writeheader()
        writer.writerows(trials)


def plot_scores(trials: list[dict], plot_path: Path, title: str) -> None:
    import matplotlib.pyplot as plt

    xs = [t["iteration"] for t in trials if t["score"] is not None]
    ys = [t["score"] for t in trials if t["score"] is not None]

    if not xs:
        raise SystemExit("No scored trials found in report.")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(xs, ys, linewidth=0.8, alpha=0.85, color="#2563eb")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Score (finalObj)")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    scored = [t["score"] for t in trials if t["score"] is not None]
    best = min(scored)
    ax.axhline(best, color="#16a34a", linestyle="--", linewidth=1, label=f"Best = {best:.4g}")
    ax.legend(loc="upper right")

    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(plot_path, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot BLAST ho.report score vs iteration.")
    parser.add_argument("--workdir", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    workdir = args.workdir.resolve()
    report_path = (args.report or workdir / "reports" / "ho.report").resolve()
    plot_path = (args.out or workdir / "reports" / "score_vs_iteration.png").resolve()
    csv_path = plot_path.with_suffix(".csv")

    if not report_path.is_file():
        raise SystemExit(f"Report not found: {report_path}")

    trials = parse_ho_report(report_path)
    write_csv(trials, csv_path)

    scored = [t for t in trials if t["score"] is not None]
    print(f"Report: {report_path}")
    print(f"Trials (input lines): {len(trials)}")
    print(f"Scored trials: {len(scored)}")
    if scored:
        scores = [t["score"] for t in scored]
        print(f"Best score: {min(scores):.6g}")
        print(f"Worst score: {max(scores):.6g}")

    plot_scores(trials, plot_path, title=f"BLAST objective score — {workdir.name}")
    print(f"Wrote CSV: {csv_path}")
    print(f"Wrote plot: {plot_path}")


if __name__ == "__main__":
    main()
