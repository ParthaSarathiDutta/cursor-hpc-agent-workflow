#!/usr/bin/env bash
# Download and install NERSC sshproxy for macOS, then obtain a 24-hour SSH key.
# Docs: https://docs.nersc.gov/connect/mfa/
set -euo pipefail

MFA_PORTAL="https://portal.nersc.gov/cfs/mfa/"
INSTALL_DIR="${HOME}/.local/bin"
PKG_DIR="/tmp/nersc-sshproxy"

echo "==> NERSC sshproxy setup"
echo

if command -v sshproxy >/dev/null 2>&1; then
  echo "sshproxy already installed at: $(command -v sshproxy)"
else
  echo "==> Fetching latest macOS package listing from ${MFA_PORTAL}"
  mkdir -p "${PKG_DIR}" "${INSTALL_DIR}"
  PKG_NAME="$(curl -fsSL "${MFA_PORTAL}" | grep -oE 'sshproxy-[0-9.]+-macos-universal\.pkg' | head -1 || true)"

  if [[ -z "${PKG_NAME}" ]]; then
    echo "ERROR: Could not find sshproxy macOS package on ${MFA_PORTAL}"
    echo "Download manually from ${MFA_PORTAL} and install, then re-run this script."
    exit 1
  fi

  PKG_URL="${MFA_PORTAL}${PKG_NAME}"
  echo "==> Downloading ${PKG_NAME}"
  curl -fsSL -o "${PKG_DIR}/${PKG_NAME}" "${PKG_URL}"

  echo "==> Installing to ${INSTALL_DIR} (no sudo required)"
  rm -rf "${PKG_DIR}/expanded"
  pkgutil --expand-full "${PKG_DIR}/${PKG_NAME}" "${PKG_DIR}/expanded"
  cp "${PKG_DIR}/expanded/Payload/usr/local/bin/sshproxy" "${INSTALL_DIR}/sshproxy"
  chmod +x "${INSTALL_DIR}/sshproxy"

  case ":${PATH}:" in
    *":${INSTALL_DIR}:"*) ;;
    *)
      echo "Add ${INSTALL_DIR} to PATH, e.g. in ~/.zshrc:"
      echo '  export PATH="${HOME}/.local/bin:${PATH}"'
      export PATH="${INSTALL_DIR}:${PATH}"
      ;;
  esac

  if ! command -v sshproxy >/dev/null 2>&1; then
    echo "ERROR: sshproxy not found after install."
    exit 1
  fi
fi

echo
echo "==> Obtaining 24-hour NERSC SSH credential"
echo "    You will be prompted for Iris password + OTP."
echo
sshproxy

if [[ -f "${HOME}/.ssh/nersc" ]]; then
  chmod 600 "${HOME}/.ssh/nersc"
  echo
  echo "SUCCESS: ~/.ssh/nersc created."
  echo "Re-run this script daily (or when SSH connections fail)."
else
  echo "ERROR: ~/.ssh/nersc was not created. Check sshproxy output above."
  exit 1
fi
