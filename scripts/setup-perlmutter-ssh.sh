#!/usr/bin/env bash
# Merge NERSC Perlmutter SSH config into ~/.ssh/config
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNIPPET="${REPO_ROOT}/config/ssh-config.snippet"
SSH_CONFIG="${HOME}/.ssh/config"
MARKER="# >>> NERSC Perlmutter (cursor-hpc-agent-workflow) >>>"
END_MARKER="# <<< NERSC Perlmutter (cursor-hpc-agent-workflow) <<<"

mkdir -p "${HOME}/.ssh"
chmod 700 "${HOME}/.ssh"
touch "${SSH_CONFIG}"
chmod 600 "${SSH_CONFIG}"

# Remove previous block if re-running
if grep -q "${MARKER}" "${SSH_CONFIG}" 2>/dev/null; then
  awk -v start="${MARKER}" -v end="${END_MARKER}" '
    $0 == start { skip=1; next }
    $0 == end { skip=0; next }
    !skip { print }
  ' "${SSH_CONFIG}" > "${SSH_CONFIG}.tmp"
  mv "${SSH_CONFIG}.tmp" "${SSH_CONFIG}"
fi

# Remove legacy single-host block if present (uses id_rsa instead of sshproxy)
if grep -q "^Host perlmutter$" "${SSH_CONFIG}" 2>/dev/null; then
  awk '
    /^Host perlmutter$/ { skip=1; next }
    skip && /^Host / { skip=0 }
    skip && /^$/ { next }
    !skip { print }
  ' "${SSH_CONFIG}" > "${SSH_CONFIG}.tmp"
  mv "${SSH_CONFIG}.tmp" "${SSH_CONFIG}"
fi

{
  echo ""
  echo "${MARKER}"
  cat "${SNIPPET}"
  echo "${END_MARKER}"
} >> "${SSH_CONFIG}"

echo "Updated ${SSH_CONFIG} with NERSC Perlmutter entries."
echo
echo "Next steps:"
echo "  1. Run: ${REPO_ROOT}/scripts/setup-sshproxy.sh   (once per day)"
echo "  2. Test: ssh perlmutter"
echo "  3. Cursor: Remote-SSH -> Connect to Host -> perlmutter"
