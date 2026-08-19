# cursor-hpc-agent-workflow

Agent-assisted development workflow for scientific computing on NERSC Perlmutter — **Cursor Remote SSH**, **Slurm** job orchestration, and HPC-aware agent rules for BLAST force-field workflows.

## Quick start

### 1. SSH (once per day)

```bash
./scripts/setup-sshproxy.sh      # Iris password + OTP → ~/.ssh/nersc
./scripts/setup-perlmutter-ssh.sh # merges config into ~/.ssh/config (already run if you cloned this)
ssh perlmutter
```

### 2. Cursor Remote SSH

1. Command Palette → **Remote-SSH: Connect to Host...** → `perlmutter`
2. Platform: **Linux**
3. Open this repo or your BLAST project on Perlmutter

Remote SSH settings are already in your Cursor user `settings.json` (`connectTimeout`, `useFlock`).

If connection hangs on first install:

```bash
ssh perlmutter 'bash -s' < scripts/reset-cursor-server.sh
```

### 3. BLAST project on Perlmutter

From Cursor integrated terminal (after Remote SSH):

```bash
bash scripts/setup-blast-project.sh blast_project
# Open: ~/blast_project (datasets/checkpoints symlinked to $SCRATCH)
```

### 4. Submit jobs

Edit `YOUR_GPU_ACCOUNT_g` in `slurm/*.slurm`, then:

```bash
sbatch slurm/blast_train.slurm
squeue --me
./scripts/monitor-jobs.sh <job_id>
```

Interactive GPU session:

```bash
export NERSC_GPU_ACCOUNT=m1234_g
./slurm/blast_interactive.sh
```

## Verify setup

```bash
./scripts/verify-connection.sh perlmutter
bash scripts/check-home-quota.sh   # run on Perlmutter
```

## Repository layout

```
config/           SSH and Cursor setting snippets
configs/          Example BLAST YAML config
docs/             Data/AI policy checklist
scripts/          Setup, verify, monitor, quota helpers
slurm/            Batch and interactive job templates
.cursor/rules/    Agent conventions for Perlmutter + BLAST
```

## Important rules

- **Login node**: edit code, git, small sanity checks only
- **Compute node**: BLAST training, GPU, LAMMPS, large runs via Slurm
- **HOME quota**: keep heavy data on `$SCRATCH`; see [docs/data-policy-checklist.md](docs/data-policy-checklist.md)

## References

- [NERSC MFA / sshproxy](https://docs.nersc.gov/connect/mfa/)
- [NERSC VS Code Remote SSH](https://docs.nersc.gov/connect/vscode/)
- [Perlmutter running jobs](https://docs.nersc.gov/systems/perlmutter/running-jobs/)
- [NERSC system status](https://www.nersc.gov/users/status)

## Placeholders to customize

| Placeholder | Replace with |
|-------------|--------------|
| `pdutta3` | Your NERSC username (in `config/ssh-config.snippet`) |
| `YOUR_GPU_ACCOUNT_g` | Your GPU Slurm account |
| BLAST env/modules | Your `module load` / `conda activate` in Slurm scripts |
