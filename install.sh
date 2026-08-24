#!/usr/bin/env bash
set -euo pipefail

# Simple installer for Production Dashboard on Debian/Ubuntu
# Usage: sudo ./install.sh [install_dir]



APP_NAME=prod-dashboard

# CLI parsing: support --user and --system flags and help
REQUESTED_MODE="auto"   # auto | user | system
POSITIONAL=()
print_usage() {
  cat <<USAGE
Usage: $0 [--user|--system] [install_dir]

Options:
  --user     Install for the current (or invoking) user (no sudo required). Installs to ~/.local/share/prod-dashboard by default.
  --system   Install system-wide under /opt/prod-dashboard (requires sudo/root). Creates /usr/local/bin and system desktop entry.
  -h, --help Show this help message

If no flag is provided the installer infers mode from how it's run: use sudo for system installs, otherwise user install.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      REQUESTED_MODE="user"
      shift
      ;;
    --system)
      REQUESTED_MODE="system"
      shift
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*|
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done
set -- "${POSITIONAL[@]}"

# determine mode
if [ "$REQUESTED_MODE" = "system" ]; then
  if [ "$EUID" -ne 0 ]; then
    echo "System install requires root. Re-run with sudo: sudo $0 --system [install_dir]" >&2
    exit 1
  fi
  INSTALL_DIR=${1:-/opt/${APP_NAME}}
  SYMLINK=/usr/local/bin/${APP_NAME}
  DESKTOP_FILE=/usr/share/applications/${APP_NAME}.desktop
  INSTALL_MODE=system
elif [ "$REQUESTED_MODE" = "user" ]; then
  # If invoked under sudo but user asked for --user, use SUDO_USER as target if available
  if [ "$EUID" -eq 0 ]; then
    if [ -n "${SUDO_USER:-}" ]; then
      USER_HOME=$(eval echo "~${SUDO_USER}")
    else
      echo "Cannot determine target user when running as root. Run installer as the target user without sudo." >&2
      exit 1
    fi
    INSTALL_DIR=${1:-${USER_HOME}/.local/share/${APP_NAME}}
    SYMLINK=${USER_HOME}/.local/bin/${APP_NAME}
    DESKTOP_FILE=${USER_HOME}/.local/share/applications/${APP_NAME}.desktop
  else
    INSTALL_DIR=${1:-${HOME}/.local/share/${APP_NAME}}
    SYMLINK=${HOME}/.local/bin/${APP_NAME}
    DESKTOP_FILE=${HOME}/.local/share/applications/${APP_NAME}.desktop
  fi
  INSTALL_MODE=user
else
  # auto-detect based on EUID
  if [ "$EUID" -eq 0 ]; then
    INSTALL_DIR=${1:-/opt/${APP_NAME}}
    SYMLINK=/usr/local/bin/${APP_NAME}
    DESKTOP_FILE=/usr/share/applications/${APP_NAME}.desktop
    INSTALL_MODE=system
  else
    INSTALL_DIR=${1:-${HOME}/.local/share/${APP_NAME}}
    SYMLINK=${HOME}/.local/bin/${APP_NAME}
    DESKTOP_FILE=${HOME}/.local/share/applications/${APP_NAME}.desktop
    INSTALL_MODE=user
  fi
fi

echo "Installing Production Dashboard to ${INSTALL_DIR} (mode=${INSTALL_MODE})"

mkdir -p "${INSTALL_DIR}"
rsync -a --exclude venv --exclude __pycache__ --exclude .git ./ "${INSTALL_DIR}/"

# copy optional assets directory if present
mkdir -p "${INSTALL_DIR}/assets"
if [ -d "./assets" ]; then
  rsync -a ./assets/ "${INSTALL_DIR}/assets/"
fi

# create venv and install requirements
python3 -m venv "${INSTALL_DIR}/venv"
# ensure venv bin scripts are executable
chmod -R u+rx "${INSTALL_DIR}/venv/bin" || true

# Bootstrap/upgrade pip inside venv. Some systems have pip/packaging inconsistencies
# so try upgrade, fall back to ensurepip, then retry.
VENV_PY="${INSTALL_DIR}/venv/bin/python"
echo "Bootstrapping pip in venv (${VENV_PY})"
if ! "${VENV_PY}" -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1; then
  echo "pip upgrade failed; trying ensurepip fallback"
  if "${VENV_PY}" -m ensurepip --upgrade >/dev/null 2>&1; then
    echo "ensurepip succeeded; upgrading pip packages"
    "${VENV_PY}" -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1 || true
  else
    echo "ensurepip failed; pip may be unavailable in venv — installer will attempt to continue" >&2
  fi
fi

if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
  echo "Installing Python requirements into venv"
  if ! "${VENV_PY}" -m pip install -r "${INSTALL_DIR}/requirements.txt"; then
    echo "Warning: venv pip failed; attempting fallback using system pip to install into venv site-packages"
    # determine venv site-packages path
    VENV_SITE=$("${VENV_PY}" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])') || VENV_SITE="${INSTALL_DIR}/venv/lib/python3.12/site-packages"
    echo "Target venv site-packages: ${VENV_SITE}"
    if command -v python3 >/dev/null 2>&1 && python3 -m pip --version >/dev/null 2>&1; then
      echo "Using system pip to install into venv site-packages (may require network)"
      if python3 -m pip install --upgrade pip setuptools wheel --target "${VENV_SITE}"; then
        if python3 -m pip install -r "${INSTALL_DIR}/requirements.txt" --target "${VENV_SITE}"; then
          echo "Installed requirements into venv site-packages via system pip"
        else
          echo "Fallback install into venv failed. Please run manually:" >&2
          echo "  ${VENV_PY} -m pip install -r ${INSTALL_DIR}/requirements.txt" >&2
        fi
      else
        echo "Failed to bootstrap packages into venv via system pip." >&2
        echo "Please install requirements manually or fix pip in the target venv." >&2
      fi
    else
      echo "System pip not available. Please install python3-pip and retry, or install requirements manually:" >&2
      echo "  ${VENV_PY} -m pip install -r ${INSTALL_DIR}/requirements.txt" >&2
    fi
  fi
fi

mkdir -p "$(dirname "${SYMLINK}")"
cat > "${SYMLINK}" <<'EOF'
#!/usr/bin/env bash
# Launcher wrapper: prefer venv python, but if venv python is not executable
# run system python3 and add the venv site-packages at runtime using site.addsitedir()
APP_DIR="__INSTALL_DIR__"
VENV_PY="$APP_DIR/venv/bin/python"
if [ -x "$VENV_PY" ]; then
  exec "$VENV_PY" "$APP_DIR/main.py" "$@"
fi
# locate venv site-packages
SITE=""
for p in "$APP_DIR"/venv/lib/python*/site-packages; do
  if [ -d "$p" ]; then
    SITE="$p"
    break
  fi
done
if [ -n "$SITE" ] && command -v python3 >/dev/null 2>&1; then
  # use python3 to execute a small bootstrap that adds SITE to sys.path then runs main.py
  exec python3 - <<PYCODE
import site, runpy, sys
site.addsitedir('${SITE}')
runpy.run_path('${APP_DIR}/main.py', run_name='__main__')
PYCODE
fi
echo "Failed to start Production Dashboard: cannot execute venv python and no fallback available." >&2
exit 1
EOF
# replace placeholder with actual path
sed -i "s|__INSTALL_DIR__|${INSTALL_DIR}|g" "${SYMLINK}"
chmod +x "${SYMLINK}"

# If system install and a invoking sudo user exists, also write a user-scoped desktop file

cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Name=Production Dashboard
Comment=Factory production monitoring dashboard
Exec=${SYMLINK}
Icon=${INSTALL_DIR}/assets/icon.svg
Terminal=false
Type=Application
Categories=Utility;Education;
StartupWMClass=Production Dashboard
EOF

chmod 644 "${DESKTOP_FILE}"

# Also install a user-scoped desktop entry for the invoking user if available
if [ "${INSTALL_MODE}" = "system" ] && [ -n "${SUDO_USER:-}" ]; then
  USER_HOME=$(eval echo "~${SUDO_USER}")
  USER_DESKTOP_DIR="${USER_HOME}/.local/share/applications"
  USER_BIN_DIR="${USER_HOME}/.local/bin"
  mkdir -p "${USER_DESKTOP_DIR}" "${USER_BIN_DIR}"
  # copy desktop entry to user scope
  cp "${DESKTOP_FILE}" "${USER_DESKTOP_DIR}/"
  chown ${SUDO_USER}:${SUDO_USER} "${USER_DESKTOP_DIR}/$(basename ${DESKTOP_FILE})"

  # make the installed tree owned by the invoking user so they can run/edit without sudo
  chown -R ${SUDO_USER}:${SUDO_USER} "${INSTALL_DIR}" || true

  # create a per-user launcher in ~/.local/bin that mirrors the system wrapper but is writable by user
  USER_LAUNCHER="${USER_BIN_DIR}/$(basename ${SYMLINK})"
  cat > "${USER_LAUNCHER}" <<'EOF'
#!/usr/bin/env bash
APP_DIR="__INSTALL_DIR__"
VENV_PY="$APP_DIR/venv/bin/python"
if [ -x "$VENV_PY" ]; then
  exec "$VENV_PY" "$APP_DIR/main.py" "$@"
fi
SITE=""
for p in "$APP_DIR"/venv/lib/python*/site-packages; do
  if [ -d "$p" ]; then
    SITE="$p"
    break
  fi
done
if [ -n "$SITE" ] && command -v python3 >/dev/null 2>&1; then
  exec python3 - <<PYCODE
import site, runpy
site.addsitedir('${SITE}')
runpy.run_path('${APP_DIR}/main.py', run_name='__main__')
PYCODE
fi
echo "Failed to start Production Dashboard: cannot execute venv python and no fallback available." >&2
exit 1
EOF
  # replace placeholder with actual path and set ownership
  sed -i "s|__INSTALL_DIR__|${INSTALL_DIR}|g" "${USER_LAUNCHER}"
  chown ${SUDO_USER}:${SUDO_USER} "${USER_LAUNCHER}"
  chmod 755 "${USER_LAUNCHER}"
fi

update-desktop-database 2>/dev/null || true

echo "Installation complete. You can run the app from the applications menu or with: ${SYMLINK}"
echo "To uninstall, remove ${INSTALL_DIR}, ${SYMLINK}, and ${DESKTOP_FILE}" 
