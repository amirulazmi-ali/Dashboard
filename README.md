# Dashboard
production dashboard for production.
# Production Dashboard — Installation (Debian / Ubuntu)

This project can be installed system-wide on Debian/Ubuntu using the included `install.sh`.

Prerequisites
- Python 3.8+ (system `python3`)
- `python3-venv` package (for virtualenv creation)

Install steps (run as root):

```bash
sudo ./install.sh /opt/prod-dashboard
```

User-scoped install (no sudo)
-----------------------------

You can install the app for a single user without root. Run the installer as your regular user (do not use `sudo`) — it will install into `~/.local/share/prod-dashboard`, create a launcher in `~/.local/bin`, and a desktop entry in `~/.local/share/applications`:

```bash
./install.sh
# then ensure ~/.local/bin is on your PATH, e.g.
export PATH="$HOME/.local/bin:$PATH"
# run the app
prod-dashboard
```

This method avoids requiring root privileges to run the application.

What the installer does
- Copies the project into `/opt/prod-dashboard`
- Creates a virtualenv at `/opt/prod-dashboard/venv` and installs `requirements.txt`
- Creates a launcher `/usr/local/bin/prod-dashboard`
- Creates a desktop entry `/usr/share/applications/prod-dashboard.desktop` so the app appears in application menus

Uninstall

```bash
sudo rm -rf /opt/prod-dashboard /usr/local/bin/prod-dashboard /usr/share/applications/prod-dashboard.desktop
```

Notes
- If you prefer a packaged `.deb`, use `fpm` or `dpkg-deb` to create a Debian package from `/opt/prod-dashboard` after running the installer.
- For headless systems, run under `xvfb-run` or enable a display server.

CI Multi-arch builds
--------------------

This repository includes GitHub Actions workflows to build multi-architecture packages (amd64 and arm64) using QEMU and `fpm`.

- Workflow: `.github/workflows/multiarch-packages.yml` — runs on tagged pushes (v*). It builds `.deb` packages for each target architecture and uploads them as artifacts.
- Workflow: `.github/workflows/release-artifacts.yml` — runs on GitHub Releases and attempts to attach previously built artifacts to the release using the `gh` CLI.

How it works
------------

- The build job installs `ruby`, `fpm` (via `gem`), and `rsync` on the runner, sets up QEMU for cross-architecture emulation, and runs `./build_fpm.sh` with `FPM_ARCH` set to either `amd64` or `arm64`.
- Artifacts are uploaded by `actions/upload-artifact` and can be downloaded from the workflow run UI.

Triggering
----------

- Push a tag like `v1.0.0` to trigger the build workflow:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Notes
-----
- Cross-building with QEMU is convenient for CI but for production multi-arch packages you should verify the package on native hardware or use dedicated runners for each architecture.
- The `gh` CLI is optional in the release workflow; if not available the workflow will print instructions for manual upload.
