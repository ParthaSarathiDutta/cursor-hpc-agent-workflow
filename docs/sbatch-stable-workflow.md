# Stable BLAST submit (dashboard / sbatch)

Use **`feature/blast-sbatch-stable`** or **`feature/dashboard-ui`** for the workflow that worked before the autonomous loop experiment.

1. Start dashboard: `./scripts/dashboard-dev.sh start`
2. Open **Submit Next Job** → write `input.txt` for your run folder(s)
3. **Submit batch (sbatch)** (or interactive with your edited Step B)
4. On Perlmutter: `squeue --me`; logs `slurm-runBOP-<jobid>.out` / `.err` in `blast_root`

Details: [agenticblast-submit.md](agenticblast-submit.md).

Multi-cycle autonomous fitting (WIP): branch **`feature/autonomous-iterative-loop`**.
