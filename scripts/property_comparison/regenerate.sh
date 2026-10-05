#!/usr/bin/env bash
# Regenerate comparison CSVs and bar plots (no LAMMPS).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="${1:-${REPO_ROOT}/scripts/property_comparison/examples/tersoff_4pot_comparison.json}"
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"
PY="${PY:-python3}"
exec "${PY}" -m blast_lib.property_comparison regenerate --config "${CONFIG}"
