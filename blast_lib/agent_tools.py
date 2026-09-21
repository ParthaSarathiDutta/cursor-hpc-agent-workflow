"""Tools for agentic Agent Chat — fetch ho.report / main1.py data on demand."""

from __future__ import annotations

from blast_lib.config import UIConfig
from blast_lib.main1_checkpoints import format_checkpoint_config, load_main1_checkpoints
from blast_lib.metrics import infer_stage, top_k_trials
from blast_lib.parser import parse_ho_report
from blast_lib.run_catalog import (
    PROPERTY_LADDER,
    find_report_path,
    load_catalog,
)
from blast_lib.trial_details import (
    METRIC_GLOSSARY,
    analyze_trial,
    format_analysis_text,
    format_property_detail,
    format_trial_compact,
    format_trial_params,
)
from blast_lib.user_session import UserRunSession
from blast_lib import agenticblast_submit as abs_submit

STAGES = ("lattice", "ce", "eos", "phonon", "elastic")


def _normalize_stage(name: str) -> str:
    n = name.strip().lower()
    if n in ("cohesive_e", "cohesive", "cohesiveenergy", "cohesive energy"):
        return "ce"
    return n


class AgentToolkit:
    """Read-only tools bound to config + session. Passed to Gemini as callable tools."""

    def __init__(self, config: UIConfig, session: UserRunSession | None = None) -> None:
        self.config = config
        self.session = session
        self._entries: dict[str, object] | None = None

    def _catalog(self) -> dict[str, object]:
        if self._entries is None:
            self._entries = {e.name: e for e in load_catalog(self.config, self.session, load_main1=False)}
        return self._entries

    def _checkpoints(self, entry) -> dict[str, list[str]]:
        if entry.checkpoint_config:
            return entry.checkpoint_config
        return load_main1_checkpoints(self.config, entry.path)

    def _entry(self, folder_name: str):
        catalog = self._catalog()
        key = folder_name.strip()
        if key in catalog:
            return catalog[key]
        lower = key.lower()
        for name, entry in catalog.items():
            if name.lower() == lower or lower in name.lower():
                return entry
        names = ", ".join(sorted(catalog))
        raise ValueError(f"Unknown folder {folder_name!r}. Available: {names}")

    def _top_trials(self, folder_name: str, k: int = 5) -> list[dict]:
        entry = self._entry(folder_name)
        if not entry.report_exists:
            raise ValueError(f"{entry.name}: no ho.report synced — sync from Run Dashboard first.")
        rp = find_report_path(self.config, entry.path)
        trials = parse_ho_report(rp)
        return top_k_trials(trials, k=max(1, int(k)))

    def _trial_at_rank(self, folder_name: str, rank: int) -> dict:
        rank = int(rank)
        top = self._top_trials(folder_name, k=rank)
        if rank < 1 or rank > len(top):
            raise ValueError(f"{folder_name}: rank {rank} out of range (1–{len(top)} in top slice).")
        t = top[rank - 1]
        t["stage"] = t.get("stage") or infer_stage(t.get("reason", ""))
        return t

    @staticmethod
    def system_instruction() -> str:
        return f"""You are the BLAST force-field fitting assistant on a human-in-the-loop dashboard.

You have **tools** to read ho.report trials, metrics, checkpoints, and Tersoff parameters.
**Always use tools** to answer — do not guess or refuse when a tool can fetch the data.

Property ladder (main1.py): {PROPERTY_LADDER} (early exit on failure).
Each folder seeds the next MCTS run from **its own** best trial.
Real files: ho.report, main1.py, model.json, mcts_restart.tersoff.

{METRIC_GLOSSARY.strip()}

Be concise. Cite numbers from tool results.

Job launch on Perlmutter uses input.txt + interactive salloc + parallel RunBOP.py.
Use submit tools to list/write input.txt; get_launch_commands is preview-only (user runs salloc manually).

Run folder setup: preview_run_folder_setup / save_run_folder_spec only — user applies on **Create Run Folder** page."""

    def list_run_folders(self) -> str:
        """List configured BLAST run folders with best stage and trial count."""
        lines = []
        for name, e in sorted(self._catalog().items()):
            status = f"best_stage={e.best_stage}, trials={e.trial_count}" if e.report_exists else "no ho.report"
            lines.append(f"- {name}: {e.strategy} ({status})")
        return "\n".join(lines) if lines else "No run folders configured."

    def get_folder_overview(self, folder_name: str) -> str:
        """Summary for one folder: strategy, best stage, checkpoints from main1.py, best-set outcome."""
        e = self._entry(folder_name)
        lines = [
            f"Folder: {e.name}",
            f"Path: {e.path}",
            f"Strategy: {e.strategy}",
            f"Report synced: {e.report_exists}",
            f"Trials in ho.report: {e.trial_count}",
            f"Best stage (rank 1): {e.best_stage}",
            f"Best score: {e.best_score}",
            f"Best outcome: {e.best.failure_reason or '—'}",
            "",
            format_checkpoint_config(self._checkpoints(e)),
        ]
        if e.best.input_params:
            lines.extend(["", f"Rank-1 params preview: {e.best.input_params[:200]}"])
        return "\n".join(lines)

    def get_checkpoint_thresholds(self, folder_name: str) -> str:
        """Checkpoint rules from main1.py for a folder."""
        e = self._entry(folder_name)
        return format_checkpoint_config(self._checkpoints(e))

    def get_trial_parameters(self, folder_name: str, rank: int = 1) -> str:
        """Tersoff parameter vector from ho.report input line for trial rank (1=best score)."""
        trial = self._trial_at_rank(folder_name, rank)
        e = self._entry(folder_name)
        return (
            f"{e.name} rank {rank} — iteration {trial.get('iteration')}, score={trial.get('score')}, "
            f"stage={trial.get('stage')}\n{format_trial_params(trial)}"
        )

    def get_trial_details(self, folder_name: str, rank: int = 1) -> str:
        """Full metrics, checkpoints, and parameters for one trial rank."""
        trial = self._trial_at_rank(folder_name, rank)
        e = self._entry(folder_name)
        analysis = analyze_trial(trial, e.name)
        return format_analysis_text(e.name, trial, analysis, self._checkpoints(e))

    def get_property_metrics(self, folder_name: str, property_stage: str, rank: int = 1) -> str:
        """Metrics and checkpoints for one property stage on a trial (lattice/ce/eos/phonon/elastic)."""
        stage = _normalize_stage(property_stage)
        if stage not in STAGES:
            raise ValueError(f"Unknown property {property_stage!r}. Use: {', '.join(STAGES)}")
        trial = self._trial_at_rank(folder_name, rank)
        e = self._entry(folder_name)
        analysis = analyze_trial(trial, e.name)
        for s in analysis.get("stages", []):
            if s["stage"] == stage:
                detail = format_property_detail(
                    {"stages": [s], "elastic_constants": analysis.get("elastic_constants")},
                    self._checkpoints(e),
                )
                header = (
                    f"{e.name} rank {rank} iteration {trial.get('iteration')} — **{stage}**\n"
                    f"{format_trial_params(trial)}\n"
                )
                return header + detail
        return f"{e.name} rank {rank}: no {stage} data (trial stopped before this stage)."

    def compare_top_trials(self, folder_name: str, top_k: int = 5) -> str:
        """Compact comparison of top K scored trials in one folder."""
        e = self._entry(folder_name)
        top = self._top_trials(folder_name, k=int(top_k))
        cfg = self._checkpoints(e)
        lines = [f"Top {len(top)} trials for {e.name}", format_checkpoint_config(cfg), ""]
        for i, trial in enumerate(top, start=1):
            trial["stage"] = trial.get("stage") or infer_stage(trial.get("reason", ""))
            if i == 1:
                analysis = analyze_trial(trial, e.name)
                lines.append(format_analysis_text(e.name, trial, analysis, cfg))
            else:
                lines.append(format_trial_compact(e.name, trial, i, cfg))
            lines.append("")
        return "\n".join(lines)

    def find_best_across_folders(self, property_stage: str, top_k: int = 5) -> str:
        """Find best-performing trials for a property across all folders (top K per folder)."""
        stage = _normalize_stage(property_stage)
        if stage not in STAGES:
            raise ValueError(f"Unknown property {property_stage!r}. Use: {', '.join(STAGES)}")

        candidates: list[tuple[float, str, int, dict, str]] = []
        for name in sorted(self._catalog()):
            try:
                top = self._top_trials(name, k=int(top_k))
            except ValueError:
                continue
            for rank, trial in enumerate(top, start=1):
                analysis = analyze_trial(trial, name)
                for s in analysis.get("stages", []):
                    if s["stage"] != stage:
                        continue
                    for block in s.get("blocks") or []:
                        mg = block.get("metric_groups") or {}
                        score = None
                        if stage == "phonon" and "ceil" in mg:
                            score = mg["ceil"].get("maxAE%")
                        elif stage == "elastic" and "values" in mg:
                            score = mg["values"].get("MAE%")
                        elif stage == "eos" and "shape" in mg:
                            score = mg["shape"].get("obj")
                        elif "values" in mg:
                            score = mg["values"].get("maxAE%")
                        if score is not None:
                            candidates.append((float(score), name, rank, trial, block.get("label") or stage))

        if not candidates:
            return f"No {stage} metrics found across folders."

        candidates.sort(key=lambda x: x[0])
        lines = [f"Best {stage} metrics across folders (lower is better for errors/obj):"]
        for score, folder, rank, trial, label in candidates[:8]:
            lines.append(
                f"- {folder} rank {rank} iter {trial.get('iteration')}: {stage} metric={score} "
                f"({label}); params: {(trial.get('input_params') or '')[:100]}"
            )
        return "\n".join(lines)

    def list_blast_run_dirs(self) -> str:
        """List BLAST run directories on Perlmutter under blast_root (SSH, matches notebook glob)."""
        try:
            dirs = abs_submit.list_blast_run_dirs(self.config)
        except Exception as exc:  # noqa: BLE001
            return f"Could not list remote dirs: {exc}"
        if not dirs:
            return "No matching run directories on Perlmutter."
        return "\n".join(f"- {d}" for d in dirs)

    def read_input_txt(self) -> str:
        """Read AgenticBLAST input.txt on Perlmutter (folder paths for parallel RunBOP)."""
        try:
            body = abs_submit.read_input_txt(self.config)
        except Exception as exc:  # noqa: BLE001
            return f"Could not read input.txt: {exc}"
        path = self.config.input_txt_remote_path
        if not body.strip():
            return f"{path} is empty or missing."
        return f"{path}:\n{body}"

    def write_input_txt(self, folder_paths: list[str]) -> str:
        """Write input.txt on Perlmutter login node (one absolute path per line, trailing slash)."""
        try:
            content = abs_submit.write_input_txt(self.config, folder_paths)
        except Exception as exc:  # noqa: BLE001
            return f"Write failed: {exc}"
        return f"Wrote {self.config.input_txt_remote_path}:\n{content}"

    def get_launch_commands(self) -> str:
        """Preview salloc + parallel commands for RunBOP (user must run on Perlmutter; do not execute)."""
        return abs_submit.launch_commands_text(self.config)

    def preview_interactive_launch(self, step_b: str = "") -> str:
        """Preview one-shot SSH command: salloc + Step B (dashboard launch; do not execute from chat)."""
        step = step_b.strip() or abs_submit.format_parallel_command(self.config)
        return abs_submit.preview_interactive_launch_command(self.config, step)

    def preview_run_folder_setup(
        self,
        new_folder_name: str,
        template_path: str,
        checkpoint_pct_json: str = "{}",
        seed_mode: str = "keep_template",
        seed_from_folder: str = "",
        bounds_mode: str = "tighten_around_restart",
        tighten_pct: float = 10.0,
    ) -> str:
        """Preview rsync + seed + model.json + main1 edits for a new run folder (does not apply)."""
        import json

        from blast_lib.run_folder_setup import RunFolderSpec, preview_run_folder_setup

        try:
            pct = json.loads(checkpoint_pct_json) if checkpoint_pct_json.strip() else {}
        except json.JSONDecodeError as exc:
            return f"Invalid checkpoint_pct_json: {exc}"
        spec = RunFolderSpec(
            new_folder_name=new_folder_name.strip(),
            template_path=template_path.strip(),
            checkpoint_pct={k: float(v) for k, v in pct.items()},
            seed_mode=seed_mode,  # type: ignore[arg-type]
            seed_from_folder=seed_from_folder.strip() or None,
            bounds_mode=bounds_mode,  # type: ignore[arg-type]
            tighten_pct=float(tighten_pct),
        )
        try:
            return preview_run_folder_setup(self.config, spec)
        except Exception as exc:  # noqa: BLE001
            return f"Preview failed: {exc}"

    def save_run_folder_spec(
        self,
        new_folder_name: str,
        template_path: str,
        checkpoint_pct_json: str = "{}",
        seed_mode: str = "keep_template",
        seed_from_folder: str = "",
        bounds_mode: str = "tighten_around_restart",
        tighten_pct: float = 10.0,
    ) -> str:
        """Save run-folder spec locally for the Create Run Folder page (does not apply on Perlmutter)."""
        import json

        from blast_lib.run_folder_setup import RunFolderSpec, save_run_folder_spec as _save

        try:
            pct = json.loads(checkpoint_pct_json) if checkpoint_pct_json.strip() else {}
        except json.JSONDecodeError as exc:
            return f"Invalid checkpoint_pct_json: {exc}"
        spec = RunFolderSpec(
            new_folder_name=new_folder_name.strip(),
            template_path=template_path.strip(),
            checkpoint_pct={k: float(v) for k, v in pct.items()},
            seed_mode=seed_mode,  # type: ignore[arg-type]
            seed_from_folder=seed_from_folder.strip() or None,
            bounds_mode=bounds_mode,  # type: ignore[arg-type]
            tighten_pct=float(tighten_pct),
        )
        _save(spec)
        return f"Saved spec for {spec.new_folder_name!r} → .cursor/status/run_folder_spec.json"

    def tool_functions(self) -> list:
        return [
            self.list_run_folders,
            self.get_folder_overview,
            self.get_checkpoint_thresholds,
            self.get_trial_parameters,
            self.get_trial_details,
            self.get_property_metrics,
            self.compare_top_trials,
            self.find_best_across_folders,
            self.list_blast_run_dirs,
            self.read_input_txt,
            self.write_input_txt,
            self.get_launch_commands,
            self.preview_interactive_launch,
            self.preview_run_folder_setup,
            self.save_run_folder_spec,
        ]


def build_toolkit(config: UIConfig, session: UserRunSession | None = None) -> AgentToolkit:
    return AgentToolkit(config, session)
