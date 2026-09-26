"""Pure RunBOP Step B + env shim strings (no SSH; safe on Perlmutter orchestrator)."""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from blast_lib.config_types import UIConfig


@dataclass(frozen=True)
class RunBopLaunchSettings:
    blast_root: str
    blast_python: str
    input_txt_name: str = "input.txt"
    lammps_cudart_lib: str = (
        "/global/cfs/cdirs/m1917/blast_ff/bin/miniconda3/lib/libcudart.so.11.0"
    )
    shifter_mpich_shim_dir: str = "/usr/lib/shifter/mpich-2.2"


def settings_from_ui_config(config: UIConfig) -> RunBopLaunchSettings:
    return RunBopLaunchSettings(
        blast_root=config.blast_root.rstrip("/"),
        blast_python=config.blast_python,
        input_txt_name=config.input_txt_name,
        lammps_cudart_lib=config.lammps_cudart_lib,
        shifter_mpich_shim_dir=config.shifter_mpich_shim_dir,
    )


def settings_from_workflow(wf) -> RunBopLaunchSettings:
    return RunBopLaunchSettings(
        blast_root=(wf.blast_root or "").rstrip("/"),
        blast_python=wf.blast_python,
    )


def format_env_setup_command(settings: RunBopLaunchSettings) -> str:
    root = settings.blast_root.rstrip("/")
    shim_dir = f"{root}/.env_shim"
    cudart_name = settings.lammps_cudart_lib.rsplit("/", 1)[-1]
    mpich = settings.shifter_mpich_shim_dir.rstrip("/")
    return (
        f'SHIM="{shim_dir}"; mkdir -p "$SHIM"; '
        f'ln -sf "{settings.lammps_cudart_lib}" "$SHIM/{cudart_name}"; '
        f'for _lib in "{mpich}"/libmpi_gnu_91.so.12 "{mpich}"/libmpi_gtl_cuda.so.0; do '
        f'[ -e "$_lib" ] && ln -sf "$_lib" "$SHIM/$(basename "$_lib")"; done; '
        f'export LD_LIBRARY_PATH="$SHIM:{mpich}:$LD_LIBRARY_PATH"'
    )


def format_parallel_runbop_command(settings: RunBopLaunchSettings) -> str:
    """Run RunBOP.py for each path in input.txt (inside interactive allocation)."""
    root = settings.blast_root.rstrip("/")
    py = settings.blast_python
    env = format_env_setup_command(settings)
    inner = f"{env} && cd {{}} && rm -rf tmp && {py} {{}}RunBOP.py"
    return (
        f"{env} && "
        f"cd {root} && cat {settings.input_txt_name} | "
        f"parallel -j 1 {shlex.quote(inner)}"
    )
