# Autonomous iterative fitting loop

Single BLAST run folder, repeated **interactive salloc + RunBOP** cycles with **changemodel.json.py** between allocations.

## Components

| Piece | Role |
|-------|------|
| **SubmitAgent** | `input.txt` + blocking **`salloc` → Step B / parallel RunBOP.py** (same as Submit Next Job interactive) |
| **RangeAgent** | Sync `ho.report`, best trial (`top_k_trials`), remote `changemodel.json.py`, update `mcts_restart.tersoff` |
| **IterativeRunController** | State machine; state in `.cursor/status/iterative_loop.json` |
| **Runner** | `./scripts/iterative-loop-dev.sh start` — holds SSH during each allocation; polls between cycles |

**No batch sbatch** in this loop (`run_batch_submit` is not used).

## Agentic vs deterministic

| Layer | Agentic? | What it does |
|-------|----------|--------------|
| **Agent Chat** (`blast_lib/agent_chat.py`) | Yes — **Gemini** + function calling | Reads synced `ho.report` via `blast_lib/agent_tools.py`; can read/write `input.txt` and preview salloc commands; does not launch GPU jobs from chat. |
| **SubmitAgent / RangeAgent** | No — fixed rules | SubmitAgent: interactive `salloc` + RunBOP. RangeAgent: best trial = lowest `finalObj`, `changemodel.json.py`, `mcts_restart.tersoff`. Names reserved for future LLM policy. |
| **IterativeRunController + runner** | No — state machine | Phases in `.cursor/status/iterative_loop.json`; `./scripts/iterative-loop-dev.sh`. |
| **Cursor hooks + Agent Activity page** | N/A | Shows **Cursor IDE** agent status (`.cursor/hooks.json`), not Gemini or the iterative loop. |

Dashboard **Strategy** column on runs is a folder-name heuristic (`run_catalog`), not an LLM.

## UI

**Autonomous Iterative Fitting**: folder, walltime, number of runs → **Start**. **Stop** sets `stop_requested` during an interactive run (will not start another cycle; tries `scancel` on the allocation id when known).

## Job completion

When the SSH interactive session ends, the controller syncs `ho.report`. A cycle succeeds only if **scored trial count increased** vs before that allocation.

## Recovery

If the runner dies while `RUNNING_INTERACTIVE` and `interactive_launch_started=true`, the workflow **FAILs** on restart (no automatic second salloc). Check `squeue --me`, then reset state before restarting.

## Manual commands

```bash
./scripts/iterative-loop-dev.sh start
./scripts/iterative-loop-dev.sh status
./scripts/iterative-loop-dev.sh stop
./scripts/iterative-loop-dev.sh logs
```

## Config

`iterative_loop_state_path`, `iterative_loop_poll_sec`, plus the same `salloc_*` / `submit_account` / `blast_python` fields as **Submit Next Job**.
