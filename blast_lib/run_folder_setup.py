"""Create and configure BLAST run folders on Perlmutter."""

from __future__ import annotations

import json
import shlex
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from blast_lib.agenticblast_submit import SubmitPathError, normalize_run_path
from blast_lib.config import REPO_ROOT, UIConfig
from blast_lib.main1_checkpoints import (
    apply_checkpoint_limits,
    apply_checkpoint_percentages,
    load_main1_text,
)
from blast_lib.metrics import top_k_trials
from blast_lib.model_json_ops import (
    _model_block,
    format_mcts_restart_line,
    load_model_json,
    merge_search_bounds,
    parse_mcts_restart_line,
    read_mcts_restart_text,
    render_model_json,
    searchable_keys,
    tighten_bounds_around_vector,
    tighten_bounds_from_trial,
)
from blast_lib.parser import parse_ho_report
from blast_lib.remote import RemoteError, ssh_exec, ssh_read_file, ssh_write_file
from blast_lib.run_catalog import find_report_path
from blast_lib.user_session import local_cache_dir

RUN_FOLDER_REQUIRED_FILES = (
    "1startmodel.sh",
    "ak.sh",
    "changemodel.json.py",
    "main1.py",
    "mcts_restart.tersoff",
    "model.json",
    "ParameterObject.py",
    "run.sh",
    "RunBOP.py",
    "settings.json",
    "startmodel.py",
)

RSYNC_EXCLUDES = (
    "reports/",
    "mctree.restart",
    "analytics.dat",
    "blast.log",
    "__pycache__/",
    ".ipynb_checkpoints/",
    "*.png",
    "phonon_p.txt",
    "phonon_t.txt",
    "phonon_p.yaml",
    "Cv_p.txt",
    "total_dos.dat",
    "current.data",
    "treestructure.nh",
)

SPEC_PATH = REPO_ROOT / ".cursor" / "status" / "run_folder_spec.json"

SeedMode = Literal["keep_template", "copy_restart_file", "from_ho_report_trial"]
BoundsMode = Literal[
    "copy_template",
    "merge",
    "tighten_around_restart",
    "tighten_around_trial",
    "manual_json",
]


@dataclass
class RunFolderSpec:
    new_folder_name: str
    template_path: str
    checkpoint_pct: dict[str, float] = field(default_factory=dict)
    checkpoint_limits: dict[str, float] = field(default_factory=dict)
    seed_mode: SeedMode = "keep_template"
    seed_from_folder: str | None = None
    seed_rank: int = 1
    copy_mctree_restart: bool = False
    bounds_mode: BoundsMode = "tighten_around_restart"
    bounds_source_folders: list[str] = field(default_factory=list)
    tighten_pct: float = 10.0
    tighten_rank: int = 1
    tighten_source_folder: str | None = None
    manual_model_json: str | None = None
    exclude_heavy: bool = True


@dataclass
class ApplyResult:
    ok: bool
    new_folder_path: str
    messages: list[str]


def save_run_folder_spec(spec: RunFolderSpec) -> None:
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(json.dumps(asdict(spec), indent=2))


def load_run_folder_spec() -> RunFolderSpec | None:
    if not SPEC_PATH.is_file():
        return None
    raw = json.loads(SPEC_PATH.read_text())
    return RunFolderSpec(**raw)


def _folder_path(config: UIConfig, name_or_path: str) -> str:
    return normalize_run_path(config, name_or_path)


def validate_run_folder_remote(config: UIConfig, folder_path: str) -> list[str]:
    remote = _folder_path(config, folder_path)
    cached = local_cache_dir(config, remote)
    if cached.is_dir():
        local_missing = [f for f in RUN_FOLDER_REQUIRED_FILES if not (cached / f).is_file()]
        if not local_missing:
            return []

    script = "\n".join(
        f"test -f {shlex.quote(remote + '/' + fname)} || echo {fname}"
        for fname in RUN_FOLDER_REQUIRED_FILES
    )
    try:
        out = ssh_exec(config, script, timeout=45)
    except RemoteError:
        return list(RUN_FOLDER_REQUIRED_FILES)
    return [line.strip() for line in out.splitlines() if line.strip()]


def _trial_from_folder(config: UIConfig, folder: str, rank: int) -> dict:
    remote = _folder_path(config, folder)
    rp = find_report_path(config, remote)
    if not rp.is_file():
        cached = local_cache_dir(config, remote) / "reports" / "ho.report"
        if cached.is_file():
            rp = cached
        else:
            raise SubmitPathError(f"No ho.report for {folder} — sync first.")
    trials = parse_ho_report(rp)
    top = top_k_trials(trials, k=rank)
    if rank < 1 or rank > len(top):
        raise SubmitPathError(f"Rank {rank} out of range for {folder}")
    return top[rank - 1]


def _remote_rsync_copy(config: UIConfig, template: str, new_path: str) -> None:
    t = shlex.quote(template)
    n = shlex.quote(new_path)
    excludes = " ".join(f"--exclude={shlex.quote(x)}" for x in RSYNC_EXCLUDES)
    cmd = f"test ! -e {n} && rsync -a {excludes} {t}/ {n}/"
    ssh_exec(config, cmd, timeout=120)


def preview_run_folder_setup(config: UIConfig, spec: RunFolderSpec) -> str:
    lines: list[str] = []
    template = _folder_path(config, spec.template_path)
    new_path = _folder_path(config, spec.new_folder_name)
    lines.append(f"New folder: {new_path}")
    lines.append(f"Template: {template}")
    lines.append("")
    tmpl_missing = validate_run_folder_remote(config, template)
    if tmpl_missing:
        lines.append(f"ERROR template missing files: {', '.join(tmpl_missing)}")
        return "\n".join(lines)
    lines.append("Steps:")
    lines.append("  1. rsync copy template → new folder (exclude reports/history)")
    lines.append(f"  2. Seed ({spec.seed_mode})")
    if spec.seed_mode == "copy_restart_file":
        lines.append(f"     copy mcts_restart from {spec.seed_from_folder}")
    elif spec.seed_mode == "from_ho_report_trial":
        lines.append(f"     ho.report rank {spec.seed_rank} from {spec.seed_from_folder}")
    lines.append(f"  3. model.json bounds mode: {spec.bounds_mode}")
    if spec.bounds_mode == "merge":
        lines.append(f"     merge: {spec.bounds_source_folders}")
    elif spec.bounds_mode == "tighten_around_restart":
        lines.append(f"     ±{spec.tighten_pct}% around mcts_restart in new folder")
    elif spec.bounds_mode == "tighten_around_trial":
        src = spec.tighten_source_folder or spec.seed_from_folder
        lines.append(f"     ±{spec.tighten_pct}% around trial rank {spec.tighten_rank} in {src}")
    lines.append(f"  4. main1.py checkpoint %: {spec.checkpoint_pct}")
    if spec.checkpoint_limits:
        lines.append(f"     absolute limits: {spec.checkpoint_limits}")
    if spec.checkpoint_pct or spec.checkpoint_limits:
        main1 = load_main1_text(config, template) or ""
        if main1:
            patched, missing = apply_checkpoint_percentages(main1, spec.checkpoint_pct)
            patched, missing_lim = apply_checkpoint_limits(patched, spec.checkpoint_limits)
            lines.append("")
            lines.append("main1.py checkpoints (in the new folder after Apply):")
            if patched != main1:
                lines.append("  → threshold values differ from template; main1.py will be edited on Apply.")
            else:
                lines.append("  → same as template (no checkpoint edits).")
            if missing:
                lines.append(f"  WARNING maxAE% stages not found in template: {missing}")
            if missing_lim:
                lines.append(f"  WARNING limit keys not found in template: {missing_lim}")
    lines.append("")
    lines.append("After apply: validate required file manifest on new folder.")
    return "\n".join(lines)


def apply_run_folder_setup(config: UIConfig, spec: RunFolderSpec) -> ApplyResult:
    messages: list[str] = []
    template = _folder_path(config, spec.template_path)
    new_path = _folder_path(config, spec.new_folder_name)
    if not new_path.startswith(config.blast_root.rstrip("/") + "/"):
        raise SubmitPathError("New folder must be under blast_root")

    missing = validate_run_folder_remote(config, template)
    if missing:
        raise SubmitPathError(f"Template missing required files: {', '.join(missing)}")

    try:
        ssh_exec(config, f"test ! -e {shlex.quote(new_path)}", timeout=15)
    except RemoteError as exc:
        raise SubmitPathError(f"Folder already exists or check failed: {exc}") from exc

    _remote_rsync_copy(config, template, new_path)
    messages.append(f"Copied template → {new_path}")

    # Seed
    if spec.seed_mode == "copy_restart_file":
        if not spec.seed_from_folder:
            raise SubmitPathError("seed_from_folder required for copy_restart_file")
        src = _folder_path(config, spec.seed_from_folder)
        ssh_exec(
            config,
            f"cp {shlex.quote(src + '/mcts_restart.tersoff')} {shlex.quote(new_path + '/mcts_restart.tersoff')}",
            timeout=20,
        )
        messages.append(f"Copied mcts_restart.tersoff from {src}")
    elif spec.seed_mode == "from_ho_report_trial":
        if not spec.seed_from_folder:
            raise SubmitPathError("seed_from_folder required for from_ho_report_trial")
        trial = _trial_from_folder(config, spec.seed_from_folder, spec.seed_rank)
        nums = parse_mcts_restart_line(trial.get("input_params", ""))
        body = format_mcts_restart_line(nums)
        ssh_write_file(config, f"{new_path}/mcts_restart.tersoff", body)
        messages.append(f"Wrote mcts_restart from trial rank {spec.seed_rank}")

    if spec.copy_mctree_restart and spec.seed_from_folder:
        src = _folder_path(config, spec.seed_from_folder)
        ssh_exec(
            config,
            f"cp {shlex.quote(src + '/mctree.restart')} {shlex.quote(new_path + '/mctree.restart')} 2>/dev/null || true",
            timeout=20,
        )
        messages.append("Copied mctree.restart (if present)")
    elif not spec.copy_mctree_restart:
        ssh_exec(config, f"rm -f {shlex.quote(new_path + '/mctree.restart')}", timeout=15)
        messages.append("Removed mctree.restart for fresh MCTS")

    # model.json
    if spec.bounds_mode == "manual_json" and spec.manual_model_json:
        ssh_write_file(config, f"{new_path}/model.json", spec.manual_model_json)
        messages.append("Wrote manual model.json")
    elif spec.bounds_mode == "merge":
        if not spec.bounds_source_folders:
            raise SubmitPathError("bounds_source_folders required for merge")
        models = [load_model_json(config, f) for f in spec.bounds_source_folders]
        merged = merge_search_bounds(models)
        ssh_write_file(config, f"{new_path}/model.json", render_model_json(merged))
        messages.append("Merged model.json bounds")
    elif spec.bounds_mode == "tighten_around_restart":
        restart = read_mcts_restart_text(config, new_path)
        model = load_model_json(config, new_path)
        n_keys = len(searchable_keys(_model_block(model)))
        vec = parse_mcts_restart_line(restart, searchable_count=n_keys)
        tightened = tighten_bounds_around_vector(model, vec, spec.tighten_pct)
        ssh_write_file(config, f"{new_path}/model.json", render_model_json(tightened))
        messages.append(f"Tightened model.json ±{spec.tighten_pct}% around restart")
    elif spec.bounds_mode == "tighten_around_trial":
        src = spec.tighten_source_folder or spec.seed_from_folder
        if not src:
            raise SubmitPathError("tighten_source_folder or seed_from_folder required")
        trial = _trial_from_folder(config, src, spec.tighten_rank)
        model = load_model_json(config, new_path)
        tightened = tighten_bounds_from_trial(model, trial.get("input_params", ""), spec.tighten_pct)
        ssh_write_file(config, f"{new_path}/model.json", render_model_json(tightened))
        messages.append(f"Tightened model.json ±{spec.tighten_pct}% around trial")

    # main1.py
    if spec.checkpoint_pct or spec.checkpoint_limits:
        main1 = ssh_read_file(config, f"{new_path}/main1.py")
        patched, missing_st = apply_checkpoint_percentages(main1, spec.checkpoint_pct)
        patched, missing_lim = apply_checkpoint_limits(patched, spec.checkpoint_limits)
        if patched != main1:
            ssh_write_file(config, f"{new_path}/main1.py", patched)
            messages.append("Updated main1.py checkpoint tolerances")
        else:
            messages.append("main1.py checkpoints unchanged (same as template)")
        if missing_st:
            messages.append(f"Warning: maxAE% stages not patched: {missing_st}")
        if missing_lim:
            messages.append(f"Warning: limit keys not patched: {missing_lim}")

    post_missing = validate_run_folder_remote(config, new_path)
    if post_missing:
        raise SubmitPathError(f"New folder missing files after setup: {', '.join(post_missing)}")

    messages.append("Manifest validation OK")
    return ApplyResult(ok=True, new_folder_path=new_path, messages=messages)


def spec_from_tool_args(
    new_folder_name: str,
    template_path: str,
    checkpoint_pct: dict[str, float] | None = None,
    seed_mode: str = "keep_template",
    seed_from_folder: str = "",
    seed_rank: int = 1,
    bounds_mode: str = "tighten_around_restart",
    bounds_source_folders: list[str] | None = None,
    tighten_pct: float = 10.0,
    tighten_rank: int = 1,
    tighten_source_folder: str = "",
    copy_mctree_restart: bool = False,
) -> RunFolderSpec:
    return RunFolderSpec(
        new_folder_name=new_folder_name,
        template_path=template_path,
        checkpoint_pct=checkpoint_pct or {},
        seed_mode=seed_mode,  # type: ignore[arg-type]
        seed_from_folder=seed_from_folder or None,
        seed_rank=int(seed_rank),
        copy_mctree_restart=bool(copy_mctree_restart),
        bounds_mode=bounds_mode,  # type: ignore[arg-type]
        bounds_source_folders=bounds_source_folders or [],
        tighten_pct=float(tighten_pct),
        tighten_rank=int(tighten_rank),
        tighten_source_folder=tighten_source_folder or None,
    )
