# AgenticBLAST job submit (Perlmutter)

Verified workflow under `blast_root` (default `/global/cfs/cdirs/m4597/partha/AgenticBLAST`).

## Files on Perlmutter

| File | Role |
|------|------|
| `Jupyter.ipynb` | Optional: builds `input.txt` via glob `ML-Tersoff*` |
| `input.txt` | One absolute run-directory path per line (trailing `/`) |
| `agenticblast_runBOP.slurm` | Batch script (deployed by dashboard before sbatch) |

Each run folder contains `RunBOP.py` (MCTS search), `main1.py` (objective), `reports/ho.report`, etc.

## Three ways to launch

### A. Dashboard — interactive (salloc + Step B)

1. **Submit Next Job** → edit/write `input.txt`.
2. Tune Step A fields and Step B command (or use defaults).
3. Confirm checkbox → **Launch interactive (salloc + Step B)**.

The Mac runs SSH with a TTY and executes:

`cd blast_root && salloc [options] -- bash -lc '[Step B]'`

Live output appears in the page. Queue wait can take a long time (`launch_ssh_timeout_sec` in config, default 4h).

### B. Dashboard — batch (sbatch)

Same page → **Submit batch (sbatch)**. The dashboard:

1. Renders [`slurm/agenticblast_runBOP.slurm`](slurm/agenticblast_runBOP.slurm) with your config.
2. Writes it to `{blast_root}/agenticblast_runBOP.slurm`.
3. Runs `sbatch` and shows the **job ID**.

Logs on Perlmutter: `slurm-runBOP-<jobid>.out` / `.err` in `blast_root`.

### C. Manual SSH (copy-paste)

1. SSH to Perlmutter.
2. Create `input.txt` (notebook or dashboard write).
3. **Step A (login node):** `salloc ...` (see UI or config).
4. **Step B (compute node):** `cd blast_root && cat input.txt | parallel "..."`.

## Agent Chat

Tools: `list_blast_run_dirs`, `read_input_txt`, `write_input_txt`, `get_launch_commands`, `preview_interactive_launch` (preview only — no auto GPU launch from chat).

## Config (`config/ui.yaml`)

See `config/ui.yaml.example`: `input_txt_*`, `blast_python`, `submit_account`, `salloc_*`, `batch_*`, `launch_ssh_timeout_sec`.

After code changes, restart the dashboard: `./scripts/dashboard-dev.sh restart` (`runOnSave` is off).

## Notes

- Closing the browser does not always stop an in-flight interactive SSH launch; check `squeue --me` on Perlmutter.
- GPU work runs on **compute nodes** (inside salloc/sbatch), not on the login node.
