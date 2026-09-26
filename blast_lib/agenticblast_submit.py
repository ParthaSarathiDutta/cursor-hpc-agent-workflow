"""AgenticBLAST submit: input.txt on Perlmutter + salloc/parallel launch commands."""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterator
from dataclasses import dataclass

from blast_lib.config_types import REPO_ROOT, UIConfig
from blast_lib.remote import (
    RemoteError,
    SSHStreamResult,
    ssh_exec,
    ssh_read_file,
    ssh_stream_command,
    ssh_stream_run,
    ssh_write_file,
)


class SubmitPathError(ValueError):
    pass


def _blast_root_norm(config: UIConfig) -> str:
    return config.blast_root.rstrip("/")


def normalize_run_path(config: UIConfig, path_or_name: str) -> str:
    """Absolute run directory under blast_root, no trailing slash."""
    raw = path_or_name.strip().rstrip("/")
    root = _blast_root_norm(config)
    if raw.startswith("/"):
        abs_path = raw
    else:
        abs_path = f"{root}/{raw}"
    if not abs_path.startswith(root + "/") and abs_path != root:
        raise SubmitPathError(f"Path must be under blast_root {root!r}: {abs_path!r}")
    return abs_path


def format_input_txt_lines(folder_paths: list[str]) -> str:
    """One absolute path per line with trailing slash (matches Jupyter.ipynb)."""
    lines: list[str] = []
    seen: set[str] = set()
    for p in folder_paths:
        norm = p.strip().rstrip("/") + "/"
        if norm not in seen:
            seen.add(norm)
            lines.append(norm)
    return "".join(f"{line}\n" for line in lines)


def list_blast_run_dirs(config: UIConfig) -> list[str]:
    """List run directories under blast_root matching run_dir_glob (SSH)."""
    root = shlex.quote(_blast_root_norm(config))
    glob_part = config.run_dir_glob
    cmd = f"ls -d {root}/{glob_part} 2>/dev/null | sort || true"
    out = ssh_exec(config, cmd, timeout=30).strip()
    if not out:
        return []
    return [line.rstrip("/") for line in out.splitlines() if line.strip()]


def read_input_txt(config: UIConfig) -> str:
    """Read {blast_root}/input.txt from Perlmutter."""
    try:
        return ssh_read_file(config, config.input_txt_remote_path)
    except RemoteError as exc:
        if "No such file" in str(exc) or "cannot open" in str(exc).lower():
            return ""
        raise


def write_input_txt(config: UIConfig, folder_paths: list[str]) -> str:
    """
    Write input.txt on Perlmutter login node.
    Returns the file content written.
    """
    if not folder_paths:
        raise SubmitPathError("At least one run folder path is required.")
    normalized = [normalize_run_path(config, p) for p in folder_paths]
    content = format_input_txt_lines(normalized)
    return write_input_txt_content(config, content)


def validate_input_txt_content(config: UIConfig, content: str) -> None:
    """Ensure each non-empty line is a run path under blast_root."""
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    if not lines:
        raise SubmitPathError("input.txt must contain at least one path line.")
    for line in lines:
        normalize_run_path(config, line.rstrip("/"))


def write_input_txt_content(config: UIConfig, content: str) -> str:
    """Write exact input.txt body (user-edited) after path validation."""
    validate_input_txt_content(config, content)
    body = content if content.endswith("\n") else content + "\n"
    ssh_write_file(config, config.input_txt_remote_path, body)
    return body


def format_salloc_command(
    config: UIConfig,
    *,
    nodes: int | None = None,
    salloc_time: str | None = None,
    qos: str | None = None,
    ntasks_per_node: int | None = None,
    gpus_per_task: int | None = None,
    gpus: int | None = None,
    account: str | None = None,
) -> str:
    """Interactive GPU allocation (run from login node after SSH)."""
    parts = [
        "salloc",
        f"--nodes {nodes if nodes is not None else config.salloc_nodes}",
        f"--qos {qos if qos is not None else config.salloc_qos}",
        f"--time {salloc_time if salloc_time is not None else config.salloc_time}",
        f"--ntasks-per-node={ntasks_per_node if ntasks_per_node is not None else config.salloc_ntasks_per_node}",
        "--constraint gpu",
        f"--gpus-per-task={gpus_per_task if gpus_per_task is not None else config.salloc_gpus_per_task}",
        f"--gpus {gpus if gpus is not None else config.salloc_gpus}",
        "--gpu-bind=none",
        f"--account {account if account is not None else config.submit_account}",
    ]
    return " ".join(parts)


def format_env_setup_command(config: UIConfig) -> str:
    """
    Shell snippet (run once before RunBOP.py) that fixes missing shared libs for the
    2020-era LAMMPS build: a scoped shim dir symlinking only libcudart.so.11.0 (avoids
    shadowing the system libstdc++ that Kokkos needs) plus the Shifter Cray-MPICH ABI dir.
    """
    root = _blast_root_norm(config)
    shim_dir = f"{root}/.env_shim"
    cudart_name = config.lammps_cudart_lib.rsplit("/", 1)[-1]
    return (
        f'SHIM="{shim_dir}"; mkdir -p "$SHIM"; '
        f'ln -sf "{config.lammps_cudart_lib}" "$SHIM/{cudart_name}"; '
        f'export LD_LIBRARY_PATH="$SHIM:{config.shifter_mpich_shim_dir}:$LD_LIBRARY_PATH"'
    )


def format_parallel_command(config: UIConfig) -> str:
    """Run RunBOP.py in each folder listed in input.txt (on compute node after salloc)."""
    root = _blast_root_norm(config)
    py = config.blast_python
    inner = f'cd {{}}; rm -rf tmp; {py} {{}}RunBOP.py'
    return (
        f"{format_env_setup_command(config)} && "
        f"cd {root} && cat {config.input_txt_name} | "
        f"parallel {shlex.quote(inner)}"
    )


def get_launch_commands(config: UIConfig) -> dict[str, str]:
    return {
        "step_a_salloc": format_salloc_command(config),
        "step_b_parallel": format_parallel_command(config),
        "working_directory": _blast_root_norm(config),
        "input_txt_path": config.input_txt_remote_path,
    }


def launch_commands_text(config: UIConfig) -> str:
    cmds = get_launch_commands(config)
    return (
        f"Working directory: {cmds['working_directory']}\n"
        f"input.txt: {cmds['input_txt_path']}\n\n"
        f"Step A (login node — request interactive GPUs):\n{cmds['step_a_salloc']}\n\n"
        f"Step B (compute node — after salloc succeeds):\n{cmds['step_b_parallel']}\n\n"
        f"Dashboard one-shot (salloc + Step B):\n{preview_interactive_launch_command(config)}"
    )


def ensure_input_txt_on_pm(config: UIConfig) -> str:
    """Return remote input.txt body or raise."""
    body = read_input_txt(config).strip()
    if not body:
        raise SubmitPathError(
            f"No {config.input_txt_name} on Perlmutter — write input.txt before launching."
        )
    return body


def build_interactive_launch_command(
    config: UIConfig,
    step_b: str,
    *,
    nodes: int | None = None,
    salloc_time: str | None = None,
    qos: str | None = None,
    ntasks_per_node: int | None = None,
    gpus_per_task: int | None = None,
    gpus: int | None = None,
    account: str | None = None,
) -> str:
    """Remote shell command: cd blast_root && salloc ... -- bash -lc 'step_b'."""
    root = _blast_root_norm(config)
    salloc = format_salloc_command(
        config,
        nodes=nodes,
        salloc_time=salloc_time,
        qos=qos,
        ntasks_per_node=ntasks_per_node,
        gpus_per_task=gpus_per_task,
        gpus=gpus,
        account=account,
    )
    inner = step_b.strip()
    if not inner:
        raise SubmitPathError("Step B command is empty.")
    escaped = inner.replace("'", "'\\''")
    return f"cd {shlex.quote(root)} && {salloc} -- bash -lc '{escaped}'"


def preview_interactive_launch_command(
    config: UIConfig,
    step_b: str | None = None,
    **salloc_kwargs: object,
) -> str:
    step = step_b if step_b is not None else format_parallel_command(config)
    return build_interactive_launch_command(config, step, **salloc_kwargs)  # type: ignore[arg-type]


def run_interactive_launch_stream(
    config: UIConfig,
    step_b: str,
    **salloc_kwargs: object,
) -> Iterator[str]:
    ensure_input_txt_on_pm(config)
    remote = build_interactive_launch_command(config, step_b, **salloc_kwargs)  # type: ignore[arg-type]
    yield from ssh_stream_command(
        config,
        remote,
        timeout_sec=config.launch_ssh_timeout_sec,
        allocate_tty=True,
    )


_SALLOC_JOB_RE = re.compile(r"Granted job allocation (\d+)", re.I)


def parse_salloc_job_id(log: str) -> str | None:
    match = _SALLOC_JOB_RE.search(log or "")
    return match.group(1) if match else None


def run_interactive_cycle(
    config: UIConfig,
    *,
    folder_paths: list[str],
    salloc_time: str,
    step_b: str | None = None,
    **salloc_kwargs: object,
) -> SSHStreamResult:
    """Write input.txt, then blocking salloc + Step B (same as Submit Next Job interactive)."""
    write_input_txt(config, folder_paths)
    step = step_b if step_b is not None else format_parallel_command(config)
    return run_interactive_launch(config, step, salloc_time=salloc_time, **salloc_kwargs)  # type: ignore[arg-type]


def run_interactive_launch(
    config: UIConfig,
    step_b: str,
    **salloc_kwargs: object,
) -> SSHStreamResult:
    ensure_input_txt_on_pm(config)
    remote = build_interactive_launch_command(config, step_b, **salloc_kwargs)  # type: ignore[arg-type]
    return ssh_stream_run(
        config,
        remote,
        timeout_sec=config.launch_ssh_timeout_sec,
        allocate_tty=True,
    )


def render_batch_slurm_content(config: UIConfig, *, batch_time: str | None = None) -> str:
    template_path = REPO_ROOT / config.batch_slurm_script
    if not template_path.is_file():
        raise SubmitPathError(f"Missing batch template: {template_path}")
    text = template_path.read_text()
    replacements = {
        "{{SUBMIT_ACCOUNT}}": config.submit_account,
        "{{BATCH_QOS}}": config.batch_qos,
        "{{BATCH_TIME}}": batch_time if batch_time is not None else config.batch_time,
        "{{BATCH_NODES}}": str(config.batch_nodes),
        "{{BATCH_NTASKS_PER_NODE}}": str(config.batch_ntasks_per_node),
        "{{BATCH_GPUS_PER_TASK}}": str(config.batch_gpus_per_task),
        "{{BATCH_GPUS}}": str(config.batch_gpus),
        "{{INPUT_TXT_NAME}}": config.input_txt_name,
        "{{BLAST_PYTHON}}": config.blast_python,
    }
    for key, val in replacements.items():
        text = text.replace(key, val)
    return text


def deploy_batch_slurm_script(config: UIConfig, *, batch_time: str | None = None) -> str:
    """Write rendered sbatch script to blast_root on Perlmutter."""
    content = render_batch_slurm_content(config, batch_time=batch_time)
    ssh_write_file(config, config.batch_slurm_remote_path, content)
    ssh_exec(config, f"chmod +x {shlex.quote(config.batch_slurm_remote_path)}", timeout=60)
    return content


def build_sbatch_remote_command(config: UIConfig) -> str:
    root = shlex.quote(_blast_root_norm(config))
    script = shlex.quote(config.batch_slurm_remote_name)
    return f"cd {root} && sbatch {script}"


@dataclass
class BatchSubmitResult:
    job_id: str
    raw_output: str


def run_batch_submit(
    config: UIConfig,
    *,
    deploy_script: bool = True,
    batch_time: str | None = None,
    folder_paths: list[str] | None = None,
) -> BatchSubmitResult:
    if folder_paths is not None:
        write_input_txt(config, folder_paths)
    ensure_input_txt_on_pm(config)
    if deploy_script:
        deploy_batch_slurm_script(config, batch_time=batch_time)
    out = ssh_exec(config, build_sbatch_remote_command(config), timeout=60)
    match = re.search(r"Submitted batch job (\d+)", out)
    if not match:
        raise RemoteError(out.strip() or "sbatch did not return a job id")
    return BatchSubmitResult(job_id=match.group(1), raw_output=out.strip())
