# Project context — cursor-hpc-agent-workflow

Repo: https://github.com/ParthaSarathiDutta/cursor-hpc-agent-workflow  
**Branch:** `feature/autonomous-iterative-loop` (latest agentic UI + iterative loop; `main` is older until merged).

After `git clone`, run `git checkout feature/autonomous-iterative-loop && git pull` before deep work. Do not merge to `main` unless I ask.

## What this repo is

Agent-assisted BLAST Tersoff force-field fitting on **NERSC Perlmutter**:
- **Cursor / SSH:** edit and submit from login nodes only; GPU work via Slurm.
- **Local Streamlit dashboard** (`ui/`, `blast_lib/`) for runs, agent chat, job submit, and the new autonomous loop.
- **Remote BLAST** lives on Perlmutter (run folders, `RunBOP.py`, `ho.report`, `changemodel.json.py` inside each run folder).

Read first:
- `README.md`, `ui/README.md`
- `docs/autonomous-iterative-loop.md` — canonical design for the loop
- `.cursor/rules/perlmutter-blast.mdc` — never train on login nodes; GPU account `*_g`; data on `$SCRATCH`

## Architecture (keep it simple)

**One BLAST run folder**, repeated cycles:

1. **SubmitAgent** — write `input.txt`, then blocking **interactive `salloc` → Step B / RunBOP** (reuse `blast_lib/agenticblast_submit.py`, same as UI "Submit Next Job" interactive path). **No batch sbatch** in this loop.
2. When allocation ends — sync `ho.report`; cycle OK only if **scored trial count increased** (ignore Slurm COMPLETED vs TIMEOUT).
3. **RangeAgent** — best trial = **lowest `finalObj`** (same as dashboard `top_k_trials(..., k=1)`); run remote **`changemodel.json.py`** (not `startmodel.py`); update **`mcts_restart.tersoff`** for antimony (preserve `Sb Sb Sb 1` prefix, replace 13 Tersoff params from best trial).
4. **IterativeRunController** + headless **runner** — `./scripts/iterative-loop-dev.sh start|status|stop|logs`; state in `.cursor/status/iterative_loop.json`.

**UI:** `ui/pages/7_Autonomous_Iterative_Fitting.py` — folder, walltime, number of cycles; Start/Stop.

**Safety (already implemented — preserve):**
- Runner crash while `RUNNING_INTERACTIVE` + `interactive_launch_started=true` → **FAIL on restart**, no second salloc (duplicate GPU risk).
- Stop during interactive run → do not start next cycle; `scancel` allocation when id is known.

**Tests:** `tests/test_iterative_controller.py`, `tests/test_range_agent.py`

## Code map

| Area | Path |
|------|------|
| Loop | `blast_lib/iterative_loop/` (controller, runner, submit_agent, range_agent, state) |
| Submit / salloc | `blast_lib/agenticblast_submit.py` |
| Parsing / trials | `blast_lib/` parser, run catalog, trial details |
| Model ops | `blast_lib/model_json_ops.py`, `run_folder_setup.py` |

## Constraints

- Do **not** redesign the dashboard or duplicate existing submit/parse logic — extend and reuse.
- Do **not** hardcode secrets; `.env` is local only.
- Do **not** auto-submit Slurm jobs after code changes unless I explicitly ask — I start tests from the UI.
- When changing force-field fitting behavior, append brief bullets to `skills/Force Field Fitting.General.md` if you learn something reusable (see `.cursor/skills/force-field-fitting/SKILL.md`).

## My immediate task

[PASTE HERE — e.g. "Run smoke test: run folder ML-Tersoff-1_PE, walltime 00:10:00, 3 cycles from UI and debug if ho.report doesn't grow" OR "Fix X on page 7" OR "Continue supervisor UI inputs: model / optimizer / training data / outputs"]

## How to work

1. Read the files above before editing.
2. Match existing style; minimal diffs.
3. Run unit tests locally after changes.
4. Only commit when I ask.
