#!/usr/bin/env bash
set -euo pipefail

# build_fpm.sh - Build packages using fpm (deb/rpm)
# Usage: ./build_fpm.sh [version] [type]
# type: deb (default) or rpm

VERSION=${1:-1.0.0}
PKGTYPE=${2:-deb}
# fpm package architecture (override via env FPM_ARCH)
FPM_ARCH=${FPM_ARCH:-amd64}
NAME=prod-dashboard
INSTALL_ROOT=/opt/${NAME}

echo "Building ${NAME} ${VERSION} (${PKGTYPE}) using fpm"

command -v fpm >/dev/null 2>&1 || {
  echo "fpm not found. Attempting to install via gem (requires ruby and rubygems)."
  if ! command -v gem >/dev/null 2>&1; then
    echo "Please install Ruby and rubygems first: sudo apt install ruby ruby-dev build-essential" >&2
    exit 1
  fi
  gem install --user-install fpm || {
    echo "Failed to install fpm via gem. Please install fpm manually." >&2
    exit 1
  }
  # ensure ~/.gem/ruby/*/bin is on PATH
  GEM_BIN_DIR=$(ruby -e 'print Gem.user_dir')/bin
  export PATH="$GEM_BIN_DIR:$PATH"
}

TMPDIR=$(mktemp -d)
PKGDIR=${TMPDIR}/package_root
mkdir -p "${PKGDIR}${INSTALL_ROOT}"

# copy project
rsync -a --exclude venv --exclude __pycache__ --exclude .git ./ "${PKGDIR}${INSTALL_ROOT}/"

# create launcher
mkdir -p "${PKGDIR}/usr/local/bin"
cat > "${PKGDIR}/usr/local/bin/${NAME}" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_ROOT}/venv/bin/python" "${INSTALL_ROOT}/main.py" "$@"
EOF
chmod 0755 "${PKGDIR}/usr/local/bin/${NAME}"

# desktop file
mkdir -p "${PKGDIR}/usr/share/applications"
cat > "${PKGDIR}/usr/share/applications/${NAME}.desktop" <<EOF
[Desktop Entry]
Name=Production Dashboard
Comment=Factory production monitoring dashboard
Exec=/usr/local/bin/${NAME}
Icon=${INSTALL_ROOT}/assets/icon.svg
Terminal=false
Type=Application
Categories=Utility;Education;
StartupWMClass=Production Dashboard
EOF

# assets
if [ -d assets ]; then
  mkdir -p "${PKGDIR}${INSTALL_ROOT}/assets"
  rsync -a assets/ "${PKGDIR}${INSTALL_ROOT}/assets/"
fi

# postinstall script to create venv and install requirements
POSTINST=${TMPDIR}/postinst.sh
cat > "${POSTINST}" <<'EOF'
#!/bin/sh
set -e
INSTALL_DIR="/opt/prod-dashboard"
if [ ! -x "$INSTALL_DIR/venv/bin/python" ]; then
  python3 -m venv "$INSTALL_DIR/venv"
fi
if [ -x "$INSTALL_DIR/venv/bin/pip" ]; then
  "$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip >/dev/null 2>&1 || true
  if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
  fi
fi
exit 0
EOF
chmod 0755 "${POSTINST}"

# build with fpm
FPM_OPTS=( -s dir -t ${PKGTYPE} -n ${NAME} -v ${VERSION} --prefix=/ --architecture ${FPM_ARCH} )
FPM_OPTS+=( --description "Production Dashboard - factory monitoring" )
FPM_OPTS+=( --url "" )
FPM_OPTS+=( --maintainer "Your Name <you@example.com>" )
FPM_OPTS+=( --after-install "${POSTINST}" )

echo "Running fpm..."
fpm "${FPM_OPTS[@]}" -C "${PKGDIR}" .

echo "Package built in current directory. Cleaning up..."
rm -rf "${TMPDIR}"
echo "Done."
