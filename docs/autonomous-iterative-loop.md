# Autonomous iterative fitting loop

Single BLAST run folder, repeated **GPU RunBOP** cycles with **Range** (changemodel + `mcts_restart.tersoff`) between cycles.

## Architecture (current — NERSC batch)

| Piece | Role |
|-------|------|
| **BatchSubmitAgent** | One SSH session: deploy scripts, write `input.txt`, init `<run_folder>/.agentic_loop/workflow.json`, run `submit_chain.sh` (`sbatch --parsable` chain) |
| **GPU job** | Batch RunBOP (`agenticblast_loop_gpu.slurm` + `scripts/agentic_loop_gpu.py`); records `cycle_N_before.json` |
| **Range job** | CPU shared job (`agenticblast_loop_range.slurm` + `scripts/agentic_loop_range.py`); local `range_core` — no SSH |
| **Dashboard** | Start submits chain; **Refresh** mirrors NERSC `workflow.json` to `.cursor/status/iterative_loop.json` |

**Mac is not required after Start.** No long-lived SSH, no `salloc`, no background runner for batch mode.

### Slurm dependencies (N cycles)

For each cycle `i`:

1. **GPU** `i` — depends on **Range** `i-1` with `--dependency=afterok:` (cycle 1 has no dependency).
2. **Range** `i` — depends on **GPU** `i` with `--dependency=afterany:`.

Example (3 cycles):

```
gpu1 → range1(afterany gpu1) → gpu2(afterok range1) → range2(afterany gpu2) → gpu3(afterok range2) → range3(afterany gpu3)
```

| Edge | Dependency | Why |
|------|------------|-----|
| GPU → Range | `afterany` | GPU may end at walltime (`TIMEOUT`); Range still validates science |
| Range → next GPU | `afterok` | Next GPU only if Range passed trials + walltime + changemodel |

### Range validation (unchanged science)

1. `sacct` Elapsed for the GPU job ≥ requested walltime − **5 s** slack  
2. Scored trial count in `reports/ho.report` **increased** vs `cycle_N_before.json`  
3. Best trial = minimum `finalObj` (same as dashboard `top_k_trials(..., k=1)`)  
4. `changemodel.json.py` with extracted Tersoff parameters  
5. Update `mcts_restart.tersoff` (preserve prefix e.g. `Sb Sb Sb 1`)

On failure, Range exits non-zero → next GPU never becomes eligible (`afterok`).

### Authoritative state (NERSC)

`<run_folder>/.agentic_loop/`:

- `workflow.json` — status (`QUEUED` / `RUNNING` / `COMPLETED` / `FAILED` / `CANCELLED`), cycles, job ids, scores  
- `cycle_N_before.json`, `cycle_N_range_result.json`  
- `logs/gpu_cN_*.out`, `logs/range_cN_*.out`  
- `submit_chain.sh` — generated submit script (audit)

Dashboard **Refresh** reads `workflow.json` over SSH (mirror only).

### GPU resources

Reuses **batch** settings from config: `batch_nodes`, `batch_gpus`, `batch_qos`, `submit_account`, etc.  
Per-cycle walltime = user **GPU time per cycle** (`HH:MM:SS`).

Range jobs: `range_qos` (default `shared`), `range_time` (default `01:00:00`).

### Inspect / stop on Perlmutter

```bash
squeue --me
sacct -j <jobid> -X --format=JobID,JobName,State,Elapsed,ExitCode -P
cat <run_folder>/.agentic_loop/workflow.json
```

**Stop (dashboard or code):** `scancel` on job ids recorded in `workflow.json`; status → `CANCELLED`.

---

## Legacy: interactive `salloc` (Mac-tethered)

Previous design: **SubmitAgent** blocking `salloc` + runner `./scripts/iterative-loop-dev.sh start|chain`.  
State machine in `IterativeRunController` + `.cursor/status/iterative_loop.json`.  
Still available in code for development (`runner --chain`); **UI Start uses batch mode**.

---

## Tests (local, no NERSC)

```bash
pytest tests/test_batch_chain.py tests/test_range_core.py tests/test_remote_workflow.py \
  tests/test_iterative_controller.py tests/test_range_agent.py
```

## Config

`loop_gpu_slurm_script`, `loop_range_slurm_script`, `range_qos`, `range_time`, plus existing `batch_*` and `blast_python` fields.
