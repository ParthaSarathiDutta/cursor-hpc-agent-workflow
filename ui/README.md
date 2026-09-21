# BLAST Dashboard (local UI)

Human-in-the-loop dashboard: view run folders and best sets, chat with the agent, submit the next job.

## Setup

```bash
cd /path/to/cursor-hpc-agent-workflow
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-ui.txt
pip install google-generativeai   # optional — for Agent Chat
export GOOGLE_API_KEY=...         # optional — for Agent Chat
# GEMINI_MODEL=gemini-3.1-flash-lite   # optional — default; or gemini-3.6-flash, gemini-3.1-pro-preview
cp config/ui.yaml.example config/ui.yaml
```

## Run

**Dev mode (recommended)** — start once, stays running, auto-reloads on save:

```bash
./scripts/dashboard-dev.sh start    # background — no terminal needed after this
./scripts/dashboard-dev.sh status
./scripts/dashboard-dev.sh open     # open browser
./scripts/dashboard-dev.sh stop     # when done for the day
```

In **Cursor**: Command Palette → **Tasks: Run Task** → **Dashboard: Start (background)**.

Then open the app from Cursor's **Ports** panel (port 8501 → globe icon), or Safari/Chrome at http://127.0.0.1:8501.

**First time / connection refused:** Command Palette → **Tasks: Run Task** → **Dashboard: Start (background)**, then reload the browser tab. The dashboard also auto-starts when you open this workspace (see `.vscode/tasks.json`).

Save changes in `ui/` or `blast_lib/` — Streamlit reloads automatically (`runOnSave` in `ui/.streamlit/config.toml`). No terminal restart.

**One-shot** (foreground, closes when terminal stops):

```bash
./scripts/run-dashboard.sh
```

## Pages

| Page | Purpose |
|------|---------|
| **Run Dashboard** | All folders — strategy, best set, stage, parameters |
| **Agent Chat** | Ask questions; agent reads synced ho.report context |
| **Create Run Folder** | Copy template on Perlmutter; checkpoints, seed, model.json (see `docs/run-folder-setup.md`) |
| **Submit Next Job** | Write `input.txt`; launch interactive (salloc+Step B) or batch sbatch from dashboard |
| Run Detail / Compare | Plots and top-k trials |
| Jobs | Slurm queue |
| Agent Activity | Cursor agent status |

## Flow

1. **Run Dashboard** → Sync all folders from Perlmutter  
2. **Agent Chat** → discuss findings and next steps  
3. **Create Run Folder** (optional) → new run dir from template before submit  
4. **Submit Next Job** → select folders, write `input.txt`, run salloc + parallel on Perlmutter (see `docs/agenticblast-submit.md`)  

Configure default folders in `config/ui.yaml` under `run_folders`.

## Troubleshooting

See previous sections: SSH via `./scripts/setup-sshproxy.sh`, use external browser not Cursor preview.
