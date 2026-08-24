#!/usr/bin/env bash
set -euo pipefail

# Simple installer for Production Dashboard on Debian/Ubuntu
# Usage: sudo ./install.sh [install_dir]

INSTALL_DIR=${1:-/opt/prod-dashboard}
APP_NAME=prod-dashboard
SYMLINK=/usr/local/bin/${APP_NAME}
DESKTOP_FILE=/usr/share/applications/${APP_NAME}.desktop

echo "Installing Production Dashboard to ${INSTALL_DIR}"

if [ "$EUID" -ne 0 ]; then
  echo "This installer requires root. Re-run with sudo." >&2
  exit 1
fi

mkdir -p "${INSTALL_DIR}"
rsync -a --exclude venv --exclude __pycache__ ./ "${INSTALL_DIR}/"

# copy optional assets directory if present
mkdir -p "${INSTALL_DIR}/assets"
if [ -d "./assets" ]; then
  rsync -a ./assets/ "${INSTALL_DIR}/assets/"
fi

python3 -m venv "${INSTALL_DIR}/venv"
source "${INSTALL_DIR}/venv/bin/activate"
pip install --upgrade pip
if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
  pip install -r "${INSTALL_DIR}/requirements.txt"
fi
deactivate

cat > "${SYMLINK}" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_DIR}/venv/bin/python" "${INSTALL_DIR}/main.py" "$@"
EOF
chmod +x "${SYMLINK}"

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
if [ -n "${SUDO_USER:-}" ]; then
  USER_HOME=$(eval echo "~${SUDO_USER}")
  USER_DESKTOP_DIR="${USER_HOME}/.local/share/applications"
  mkdir -p "${USER_DESKTOP_DIR}"
  cp "${DESKTOP_FILE}" "${USER_DESKTOP_DIR}/"
  chown ${SUDO_USER}:${SUDO_USER} "${USER_DESKTOP_DIR}/$(basename ${DESKTOP_FILE})"
fi

update-desktop-database 2>/dev/null || true

echo "Installation complete. You can run the app from the applications menu or with: ${SYMLINK}"
echo "To uninstall, remove ${INSTALL_DIR}, ${SYMLINK}, and ${DESKTOP_FILE}" 
