# Autonomous iterative fitting loop

Single BLAST run folder, repeated **batch sbatch** cycles with **changemodel.json.py** between jobs.

## Components

| Piece | Role |
|-------|------|
| **SubmitAgent** | `input.txt` + deploy `agenticblast_runBOP.slurm` with your walltime + `sbatch` |
| **RangeAgent** | Sync `ho.report`, best trial (`top_k_trials`), remote `changemodel.json.py`, update `mcts_restart.tersoff` |
| **IterativeRunController** | State machine; state in `.cursor/status/iterative_loop.json` |
| **Runner** | `./scripts/iterative-loop-dev.sh start` — polls controller every 30s (configurable) |

## UI

**Autonomous Iterative Fitting** page: set folder, walltime, number of runs → **Start**.

The dashboard shows phase, cycle, job ID, and best score. Closing the browser does **not** stop the loop if the runner is up.

## Job completion

When the Slurm job leaves the queue, the controller syncs `ho.report`. A cycle succeeds only if **scored trial count increased** vs before that submit. Slurm `COMPLETED` vs `TIMEOUT` is not used as the gate.

## Manual commands

```bash
./scripts/iterative-loop-dev.sh start   # background runner
./scripts/iterative-loop-dev.sh status
./scripts/iterative-loop-dev.sh stop    # stops runner only; use UI Stop to mark workflow STOPPED
./scripts/iterative-loop-dev.sh logs
```

## Config

`config/ui.yaml`:

- `iterative_loop_state_path` (default `.cursor/status/iterative_loop.json`)
- `iterative_loop_poll_sec` (default `30`)

Uses the same `submit_account`, `blast_python`, and batch Slurm settings as **Submit Next Job**.
