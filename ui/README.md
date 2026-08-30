# BLAST Dashboard (local UI)

Streamlit dashboard for agent activity, BLAST run analysis, Slurm jobs, and strategy suggestions.

## Setup (one time)

```bash
cd /path/to/cursor-hpc-agent-workflow
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-ui.txt
cp config/ui.yaml.example config/ui.yaml   # edit paths/account if needed
```

## Run

**Recommended** — use the launcher (sets PYTHONPATH and venv automatically):

```bash
./scripts/run-dashboard.sh
```

Or manually:

```bash
source .venv/bin/activate
streamlit run ui/app.py
```

Open **http://127.0.0.1:8501** in **Safari or Chrome**.

> **Do not use Cursor's built-in browser** (Simple Browser / Preview). Streamlit uses WebSockets and often shows *Connection error* inside Cursor. The launcher opens Safari automatically on macOS.

## Troubleshooting

### "Connection error" or blank page inside Cursor

Open **http://127.0.0.1:8501** in **Safari or Chrome** instead.

### Browser says "Connection refused"

The dashboard is **not running yet**. Start it with `./scripts/run-dashboard.sh` and keep that terminal open.

### Sidebar shows "Perlmutter SSH: failed"

The UI itself is working; SSH to NERSC is not. Fix SSH first:

```bash
./scripts/setup-sshproxy.sh
ssh perlmutter echo ok
```

Then refresh the dashboard. Sync and Jobs pages need working SSH.

### Pages show errors or blank content

Always run from the **repo root**, not from inside `ui/`:

```bash
./scripts/run-dashboard.sh   # correct
```

### No run data on Overview / Detail pages

Click **Sync from Perlmutter** in the sidebar (requires SSH). First sync can take ~30 seconds.

### Agent Activity shows "Idle"

Restart Cursor so project hooks in `.cursor/hooks.json` load. Hooks write live status to `.cursor/status/board.json`.

## Agent activity hooks

Project hooks in `.cursor/hooks.json` write live status to `.cursor/status/board.json`.
Restart Cursor after cloning if hooks do not load.

## Sync run data manually

```bash
rsync -az perlmutter:/global/cfs/cdirs/m4597/partha/AgenticBLAST/ML-Tersoff-1_PE/reports/ ~/blast-runs-cache/ML-Tersoff-1_PE/reports/
```
