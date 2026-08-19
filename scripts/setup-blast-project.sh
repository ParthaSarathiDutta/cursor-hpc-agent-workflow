#!/usr/bin/env bash
# Run on Perlmutter (login node) to set up recommended BLAST project layout.
# Keeps heavy data on $SCRATCH, source code in $HOME or scratch project dir.
#
# Usage (from Cursor terminal after Remote SSH to perlmutter):
#   bash scripts/setup-blast-project.sh [project_name]

set -euo pipefail

PROJECT_NAME="${1:-blast_project}"
SCRATCH_ROOT="${SCRATCH:-${PSCRATCH:-}}"
HOME_PROJECT="${HOME}/${PROJECT_NAME}"

if [[ -z "${SCRATCH_ROOT}" ]]; then
  echo "ERROR: SCRATCH/PSCRATCH not set. Are you on Perlmutter?"
  exit 1
fi

SCRATCH_PROJECT="${SCRATCH_ROOT}/${PROJECT_NAME}"

echo "==> Creating project layout"
echo "    Source/config: ${HOME_PROJECT}"
echo "    Data/output:   ${SCRATCH_PROJECT}"

mkdir -p "${HOME_PROJECT}"/{configs,scripts,slurm,logs}
mkdir -p "${SCRATCH_PROJECT}"/{datasets,checkpoints,results}

# Symlink heavy dirs to scratch
for dir in datasets checkpoints results; do
  ln -sfn "${SCRATCH_PROJECT}/${dir}" "${HOME_PROJECT}/${dir}"
done

cat > "${HOME_PROJECT}/README.txt" <<EOF
BLAST project on NERSC Perlmutter
=================================
Source & configs: ${HOME_PROJECT}
Heavy data:       ${SCRATCH_PROJECT}

Open this folder in Cursor: File -> Open Folder -> ${HOME_PROJECT}

Submit jobs from integrated terminal:
  sbatch slurm/blast_train.slurm
  squeue --me
EOF

echo
echo "SUCCESS. Open in Cursor: ${HOME_PROJECT}"
ls -la "${HOME_PROJECT}"
