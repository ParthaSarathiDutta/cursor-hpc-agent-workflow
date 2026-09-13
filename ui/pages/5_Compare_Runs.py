"""Compare best sets across run folders."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _setup  # noqa: F401

import pandas as pd
import streamlit as st

from blast_lib.config import load_config
from blast_lib.run_catalog import load_catalog
from blast_lib.user_session import get_session

config = load_config()
session = get_session()

st.title("Compare Runs")
st.caption("Best set per folder — ranked by how far the best set progressed")

entries = load_catalog(config, session)
if not entries:
    st.warning("No folders on **Run Dashboard**.")
    st.stop()

stage_rank = {"complete": 6, "elastic": 5, "phonon": 4, "eos": 3, "ce": 2, "lattice": 1, "none": 0, "unknown": 0}
entries_sorted = sorted(entries, key=lambda e: stage_rank.get(e.best_stage, 0), reverse=True)

rows = []
for e in entries_sorted:
    rows.append(
        {
            "Folder": e.name,
            "Strategy": e.strategy[:50] + ("..." if len(e.strategy) > 50 else ""),
            "Best set stage": e.best_stage,
            "Best set outcome": (e.best.failure_reason or "—")[:60],
            "Report": "yes" if e.report_exists else "no",
        }
    )

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
