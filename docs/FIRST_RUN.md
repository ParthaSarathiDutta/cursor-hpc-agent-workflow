# First run (one interactive step)

Everything in this repo is configured except the **NERSC MFA credential**, which only you can provide.

## Do this once (takes ~1 minute)

In a normal Terminal (not Cursor):

```bash
cd /Users/parthasarathidutta/Cursor/IntegrationWithNERSC
./scripts/setup-sshproxy.sh
```

Enter your **Iris password** and **OTP** when prompted. This creates `~/.ssh/nersc` (valid ~24 hours).

Then verify:

```bash
ssh perlmutter
./scripts/verify-connection.sh perlmutter
```

> **Note:** Perlmutter may be down for maintenance. Check https://www.nersc.gov/users/status before connecting.

## Connect Cursor

1. Open Cursor
2. Command Palette → **Remote-SSH: Connect to Host...** → `perlmutter`
3. Platform: **Linux**
4. **File → Open Folder** → clone or copy this repo to Perlmutter, or open your existing BLAST project

## On Perlmutter (Cursor integrated terminal)

```bash
bash scripts/setup-blast-project.sh blast_project
bash scripts/check-home-quota.sh
# Edit YOUR_GPU_ACCOUNT_g in slurm/*.slurm, then:
sbatch slurm/blast_train.slurm
```

Re-run `./scripts/setup-sshproxy.sh` daily or when SSH stops working.
