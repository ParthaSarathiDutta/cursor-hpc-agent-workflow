# Run folder setup (dashboard)

Create a new BLAST run directory on Perlmutter by copying a template, then adjusting **main1.py** checkpoint tolerances, **mcts_restart.tersoff**, and **model.json** search bounds.

## UI

**Streamlit → Create Run Folder** (`ui/pages/3_Create_Run_Folder.py`)

1. Choose template folder and new folder name under `blast_root`.
2. Set checkpoint **percent** thresholds per property stage (lattice, ce, eos, phonon, elastic).
3. Seed **mcts_restart.tersoff** (keep template, copy from another folder, or rank-1 trial from `ho.report`).
4. Choose **model.json** bounds (keep, ±% around restart/trial, merge folders, or paste JSON).
5. **Preview plan** (writes spec to `.cursor/status/run_folder_spec.json`).
6. **Apply** (requires confirm) — rsync copy, remote file writes, manifest check.

After apply, add the folder to `config/ui.yaml` `run_folders` and **Sync** on Run Dashboard.

## Agent Chat

Tools `preview_run_folder_setup` and `save_run_folder_spec` help draft the same spec; they do **not** modify Perlmutter. Apply only from the Create Run Folder page.

## Library

- `blast_lib/run_folder_setup.py` — `RunFolderSpec`, `preview_run_folder_setup`, `apply_run_folder_setup`
- `blast_lib/main1_checkpoints.py` — `apply_checkpoint_percentages`
- `blast_lib/model_json_ops.py` — bounds merge/tighten, `mcts_restart` parse/format

## Required files (manifest)

`1startmodel.sh`, `ak.sh`, `changemodel.json.py`, `main1.py`, `mcts_restart.tersoff`, `model.json`, `ParameterObject.py`, `run.sh`, `RunBOP.py`, `settings.json`, `startmodel.py`

Heavy artifacts (reports, `mctree.restart`, logs) are excluded from rsync by default.
