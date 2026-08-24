#!/usr/bin/env bash
set -euo pipefail

# build_deb.sh - Build a .deb package for Production Dashboard
# Usage: ./build_deb.sh [version]

VERSION=${1:-1.0.0}
PKGNAME=prod-dashboard
INSTALL_DIR=/opt/${PKGNAME}
PKGDIR=$(pwd)/pkg_build
DEBFILE=${PKGNAME}_${VERSION}_amd64.deb
MAINTAINER="Your Name <you@example.com>"
DESCRIPTION="Production Dashboard - factory production monitoring"

echo "Building ${DEBFILE}"

rm -rf "${PKGDIR}"
mkdir -p "${PKGDIR}${INSTALL_DIR}"

# Copy project files (exclude venv and node_modules, .git)
rsync -a --exclude venv --exclude __pycache__ --exclude .git ./ "${PKGDIR}${INSTALL_DIR}/"

# Create a wrapper script in /usr/local/bin
mkdir -p "${PKGDIR}/usr/local/bin"
cat > "${PKGDIR}/usr/local/bin/${PKGNAME}" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_DIR}/venv/bin/python" "${INSTALL_DIR}/main.py" "$@"
EOF
chmod 755 "${PKGDIR}/usr/local/bin/${PKGNAME}"

# Ensure a venv will be created on install using postinst (we'll create it here)
# Pre-create venv in package to simplify install: create venv now
python3 -m venv "${PKGDIR}${INSTALL_DIR}/venv"

# Build DEBIAN control
mkdir -p "${PKGDIR}/DEBIAN"
cat > "${PKGDIR}/DEBIAN/control" <<EOF
Package: ${PKGNAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: ${MAINTAINER}
Depends: python3, python3-venv
Description: ${DESCRIPTION}
EOF

# Post-install: install pip requirements into the bundled venv
cat > "${PKGDIR}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
INSTALL_DIR="/opt/prod-dashboard"
if [ -x "$INSTALL_DIR/venv/bin/pip" ]; then
  $INSTALL_DIR/venv/bin/python -m pip install --upgrade pip >/dev/null 2>&1 || true
  if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    $INSTALL_DIR/venv/bin/pip install -r "$INSTALL_DIR/requirements.txt"
  fi
fi
# update desktop database (best-effort)
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 755 "${PKGDIR}/DEBIAN/postinst"

# Optional: add desktop file
mkdir -p "${PKGDIR}/usr/share/applications"
if [ -f "prod-dashboard.desktop" ]; then
  cp prod-dashboard.desktop "${PKGDIR}/usr/share/applications/"
else
  cat > "${PKGDIR}/usr/share/applications/prod-dashboard.desktop" <<EOF
[Desktop Entry]
Name=Production Dashboard
Comment=Factory production monitoring dashboard
Exec=/usr/local/bin/prod-dashboard
Icon=${INSTALL_DIR}/assets/icon.svg
Terminal=false
Type=Application
Categories=Utility;Education;
StartupWMClass=Production Dashboard
EOF
fi

# Optional: install icon
if [ -d assets ]; then
  mkdir -p "${PKGDIR}${INSTALL_DIR}/assets"
  cp -a assets/* "${PKGDIR}${INSTALL_DIR}/assets/"
fi

# Set proper permissions
# control files should be readable; make postinst executable and control dir 755
find "${PKGDIR}/DEBIAN" -type f -exec chmod 644 {} +
chmod 755 "${PKGDIR}/DEBIAN" || true
chmod 755 "${PKGDIR}/DEBIAN/postinst" || true
find "${PKGDIR}${INSTALL_DIR}" -type d -exec chmod 755 {} +
find "${PKGDIR}${INSTALL_DIR}" -type f -exec chmod 644 {} +

# Build the deb
dpkg-deb --build "${PKGDIR}" "${DEBFILE}"

echo "Built ${DEBFILE}"

# Done
