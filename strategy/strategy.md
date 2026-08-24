# Force-field fitting strategy

Summary of BLAST Tersoff fitting runs under AgenticBLAST, what each taught us, and where we go next.

**Location on Perlmutter:** `/global/cfs/cdirs/m4597/partha/AgenticBLAST/`

**Objective:** Fit a Tersoff (Sb–Sb) potential for antimonene that passes the full BLAST property ladder (lattice → cohesive energy → EOS → phonon → elastic). No run has completed all stages yet; best scores are still in the penalty range (~996k–997k).

---

## Run folders

| Folder | Polymorph strategy (`main1.py`) | Status |
|---|---|---|
| `ML-Tersoff-1_PE` | `[0]` only — single structure for all stages | Completed search (~3.4k trials) |
| `ML-Tersoff-1_PE_12` | `[0, 1]` — both structures for all stages | Completed search (~3.4k trials) |
| `ML-Tersoff-1_PE_hybrid` | `[0]` for lattice/EOS/phonon/elastic; `[0, 1]` for **ce only** | **Created, not run yet** |

All three share the same training catalog and LAMMPS settings in `settings.json`. Differences are mainly `main1.py` polymorph selection, search bounds in `model.json`, and search history in `ho.report`.

---

## How we analyze a folder (important)

**Most trials in a run folder are expected to be bad.** MCTS (or any search) tries thousands of parameter sets; early exit and penalty scores (~1e6) are normal. We do **not** study the full parameter distribution or try to understand how “typical” failed sets look.

**We only care about the top few trials** — those with the lowest `finalObj` that get furthest through the property ladder.

| Focus on | Ignore |
|---|---|
| Best 1–5 trials by `finalObj` | Bulk of ~1e6 penalty trials |
| Which **stage** the best trials reach (lattice, ce, phonon, elastic) | Mean/median score across all trials |
| Parameters in **`mcts_restart.tersoff`** and top `ho.report` lines | Random failed `input` lines |
| Whether top trials **improve over prior folders** | Per-folder failure counts as a quality metric |

**Practical tools:**

- **`reports/ho.report`** — sort/filter by `finalObj`; read the best lines and their failure reason (or “completed all stages”).
- **`mcts_restart.tersoff`** — single-line seed = current best-known parameters for that folder.
- **`startmodel.py`** — uses top *k* trials (e.g. `k=3`) from `ho.report` to tighten `model.json` bounds; explicitly a **top-k** view, not all trials.
- **`scripts/analysis_ho_report.py`** — score vs iteration; watch the **best-so-far** curve, not every point.

A folder with 3,000+ trials and only ~24 near-elastic is **acceptable** if those top trials carry useful seeds for the next run. Search quality is judged by **best performers**, not by the majority failing.

---

## Performance by folder

### `ML-Tersoff-1_PE` (single polymorph)

| Metric | Value |
|---|---|
| Trials scored | 3,407 |
| Best `finalObj` | **995,823** (best across all folders) |
| Completed all stages | 0 |
| Trials below 999k | ~47% |
| Deepest stage reached | **Elastic** (24 trials) |

**Failure breakdown (approx.):** lattice 1,795 · ce 1,291 · phonon 273 · eos 24 · elastic 24  
*(Most of these are discarded; only the ~24 elastic-stage and ~273 phonon-stage trials matter for ranking top candidates.)*

**Best trial died at:** elastic (MAE% > 25)

**`mcts_restart.tersoff`:** Matches best trial in this folder’s `ho.report` (same params within rounding).

---

### `ML-Tersoff-1_PE_12` (two polymorphs everywhere)

| Metric | Value |
|---|---|
| Trials scored | 3,400 |
| Best `finalObj` | 997,476 |
| Completed all stages | 0 |
| Trials below 999k | ~11% |
| Deepest stage reached | Phonon (35 trials); none to elastic |

**Failure breakdown (approx.):** lattice **3,004** · ce 361 · phonon 35  
*(Expected for a strict dual-polymorph run; only the top ~35 phonon-stage trials are worth comparing to PE.)*

**Best trial died at:** phonon stage

**`mcts_restart.tersoff`:** Matches best trial **in this folder only** — different params from PE, worse score.

---

### `ML-Tersoff-1_PE_hybrid` (hybrid — current strategy)

| Metric | Value |
|---|---|
| Trials scored | — (no `ho.report` yet) |
| Status | Folder created; `main1.py` patched; empty `reports/` |
| Seed | `mcts_restart.tersoff` copied from **PE** best (not yet re-optimized for hybrid objective) |

See [`ML-Tersoff-1_PE_hybrid/STRATEGY.md`](file:///global/cfs/cdirs/m4597/partha/AgenticBLAST/ML-Tersoff-1_PE_hybrid/STRATEGY.md) on Perlmutter for the one-line objective split.

---

## What we learned

### From `ML-Tersoff-1_PE`

- Single-polymorph search **explores much deeper** — almost half of trials get past early penalties; some reach phonon and elastic.
- The **bottleneck after lattice is cohesive energy** (1,291 ce failures vs 1,795 lattice).
- Best candidate got furthest (**elastic**) but still failed MAE checkpoint — the potential is close on some properties but not converged.
- **`mcts_restart.tersoff` in this folder is the global best seed** across completed runs.

### From `ML-Tersoff-1_PE_12`

- Requiring **both polymorphs in lattice (and all stages)** is much stricter — ~88% of trials fail at lattice alone.
- Relative **energy ordering** across polymorphs is enforced from the start; search spends most budget dying early.
- Few trials reach phonon/elastic; best score is **worse** than PE despite similar trial count.
- Confirms that “more structures everywhere” is not free — it changes the searchable landscape dramatically.

### From comparing PE vs PE_12

- Trade-off is clear: **depth of search** (PE) vs **polymorph ordering constraint** (PE_12).
- Neither alone has finished the full ladder; next step should **combine strengths**, not rerun the same MCTS with fresh bounds.
- **`mcts_restart.tersoff` is per-folder best**, not cross-folder best — only PE’s restart holds the globally best parameters so far.

---

## Current strategy: `ML-Tersoff-1_PE_hybrid`

**Idea:** Don’t require dual-polymorph lattice (PE_12’s main cost). Do require dual-polymorph **cohesive energy and ordering** (the physics PE skips with one structure).

```python
polymorphs_single = list(all_polymorphs[i] for i in [0])   # lattice, eos, phonon, elastic
polymorphs_ce     = list(all_polymorphs[i] for i in [0, 1]) # ce + ordering only
```

**Why this is the active line of work:**

1. PE proved the search can reach phonon/elastic with one structure in the ladder.
2. PE_12 proved ce/ordering across two polymorphs matters but full dual lattice kills exploration.
3. Hybrid targets the ce gap in PE without PE_12’s lattice collapse.

**Seed:** Start from PE’s best parameters and bounds (already in `mcts_restart.tersoff` / copied `model.json`).

---

## Next steps (to fulfill the objective)

1. **Run `ML-Tersoff-1_PE_hybrid`** — submit MCTS (`RunBOP.py`) on a compute node; target ~500–1,000 trials for first comparison (not another full 3.4k blind search unless needed).
2. **Extract top-k only** from each folder’s `ho.report` (best `finalObj`, furthest stage). Compare those parameter sets across PE, PE_12, and hybrid — not the full trial pool.
3. **Compare top trials** against PE and PE_12:
   - Do hybrid top trials reach phonon/elastic like PE’s best?
   - Does ce ordering improve vs PE’s top set without PE_12’s lattice collapse?
4. **Refine from winners:** use `startmodel.py` / `changemodel.json.py` on **top-k** trials to narrow bounds; update `mcts_restart.tersoff` from the single best line.
5. **If hybrid top trials still fail at elastic:** focus the next search window on parameters that affect elastic, seeded from PE’s best (already at elastic).
6. **Longer term:** plug a **genetic algorithm** into the same `main1.py` objective — selection on top performers only, same evaluator (see `constitution/` and `.cursor/skills/force-field-fitting/`).

---

## Success criteria

- **`finalObj` well below penalty (~1e6)** for at least one **top trial** that **completes all stages** (`completed all stages` in `ho.report`).
- That winning parameter set passes lattice, ce (including ordering across polymorphs), eos, phonon, and elastic checkpoints.
- **`mcts_restart.tersoff`** updated to that trial; optional export of final `model.json` / force field file.
- We do **not** require most trials in a folder to be good — only that the **best few** progress the fit.

---

## Related docs

| Doc | Purpose |
|---|---|
| [`skills/Force Field Fitting.General.md`](../skills/Force%20Field%20Fitting.General.md) | Quick recollection notes |
| [`constitution/General framework for Tersoff force field fitting using BLAST.md`](../constitution/General%20framework%20for%20Tersoff%20force%20field%20fitting%20using%20BLAST.md) | General BLAST run framework |
| [`scripts/analysis_ho_report.py`](../scripts/analysis_ho_report.py) | Parse and plot `ho.report` |

---

*Last updated from analysis of PE and PE_12 runs (Aug 2026). Hybrid folder created; run pending. Analysis focuses on top-k trials only, not full parameter distributions.*
