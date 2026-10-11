# Autonomous iterative fitting loop

Single BLAST run folder, repeated **interactive GPU RunBOP** cycles with **Range** (changemodel + `mcts_restart.tersoff`) between cycles.

## Architecture (current — NERSC orchestrator)

| Piece | Role |
|-------|------|
| **OrchestratorSubmitAgent** | One SSH session: deploy runtime, write `input.txt`, init `workflow.json`, **`sbatch -q cron`** orchestrator |
| **Orchestrator job** | Login-pool **cron QOS** process runs `scripts/agentic_loop_orchestrator.py` |
| **Per cycle** | One blocking **`salloc --qos interactive --constraint gpu`**, Step B RunBOP, then **local** `range_core` (no Range sbatch) |
| **Dashboard** | Start submits orchestrator; **Refresh** mirrors NERSC `workflow.json` |

**Mac is not required after Start.** No long-lived SSH, no pre-chained batch GPU jobs.

### Cycle sequence (N cycles)

At most **one** interactive GPU allocation is submitted or running at any time:

```
for cycle in 1..N:
  record trial count → unset SLURM_* → salloc interactive → RunBOP → validate → Range
  on Range failure → FAILED (no next salloc)
after cycle N Range → COMPLETED
```

### Range validation (unchanged science)

1. `sacct` Elapsed for the interactive allocation ≥ requested walltime − **5 s** slack  
2. Scored trial count in `reports/ho.report` **increased** vs baseline  
3. Best trial = minimum `finalObj`  
4. `changemodel.json.py` + `mcts_restart.tersoff` update  

### Authoritative state (NERSC)

`<run_folder>/.agentic_loop/`:

- `workflow.json` — status, **phase**, orchestrator job id, interactive allocation ids, cycles, scores  
- `cycle_N_before.json`, `cycle_N_range_result.json`  
- `logs/orch-<jobid>.out`  

### Accounts / QOS

- Orchestrator: **`m4597`** (or `orchestrator_cron_account` in config), **`-q cron -C cron`**
- GPU cycles: **`m4597_g`** (or `gpu_account` / `submit_account`), **`salloc --qos interactive`**

### Inspect / stop on Perlmutter

```bash
squeue --me
cat <run_folder>/.agentic_loop/workflow.json
sacct -j <orchestrator_or_interactive_job_id> -X --format=JobID,JobName,State,Elapsed,ExitCode -P
```

**Stop (dashboard):** `scancel` orchestrator + current interactive id; `workflow.json` → `STOPPED`.

---

## Legacy: batch Slurm chain

Previous design: pre-submitted **gpu_regular** + **shared** dependency chain (`BatchSubmitAgent`). Code remains for reference; **UI Start uses the orchestrator path**.

## Legacy: Mac-tethered interactive

**SubmitAgent** + `./scripts/iterative-loop-dev.sh` — development only.
