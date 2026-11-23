#!/usr/bin/env bash
set -euo pipefail
version="${1:-0.1.0-alpha.3}"
out="${2:-dist}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
pkg="aevra-desktop"
base="$work/${pkg}_${version}_amd64"
mkdir -p -m 0755 "$base/DEBIAN" "$base/usr/lib/aevra" "$base/usr/bin" "$base/usr/share/applications"
cat > "$base/DEBIAN/control" <<CTRL
Package: $pkg
Version: $version
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Aevra project
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1
Description: Aevra native desktop
 Local Assistant desktop using the pinned local Qwen/llama.cpp web UI.
CTRL
if [[ ! -x "$root/.venv/bin/python" ]]; then
  echo "Build requires a prepared .venv; run uv sync --locked --no-dev first" >&2
  exit 2
fi
cp -a "$root/apps" "$root/src" "$root/.venv" "$base/usr/lib/aevra/"
# Replace the build-machine Python symlink with a real interpreter binary.
python_target="$(readlink -f "$root/.venv/bin/python")"
if [[ ! -x "$python_target" ]]; then
  echo "Could not resolve the build Python binary" >&2
  exit 2
fi
cp --remove-destination "$python_target" "$base/usr/lib/aevra/.venv/bin/aevra-python"
# uv creates a private venv; normalize it for the unprivileged desktop user.
find "$base/usr/lib/aevra/.venv" -type d -exec chmod 0755 {} +
find "$base/usr/lib/aevra/.venv" -type f -exec chmod 0644 {} +
find "$base/usr/lib/aevra/.venv/bin" -type f -exec chmod 0755 {} +
mkdir -p "$base/usr/lib/aevra/data"
cp -a "$root/data/ui" "$base/usr/lib/aevra/data/"
mkdir -p "$base/usr/lib/aevra/apps/branding/assets"
cp -a "$root/apps/branding/assets/." "$base/usr/lib/aevra/apps/branding/assets/"
# Source trees may inherit umask 027 on the self-hosted runner; the desktop user must read code and icons.
find "$base/usr/lib/aevra" -type d -exec chmod 0755 {} +
find "$base/usr/lib/aevra" -type f -exec chmod 0644 {} +
find "$base/usr/lib/aevra/.venv/bin" -type f -exec chmod 0755 {} +
chmod 0755 "$base/DEBIAN" "$base/usr/bin" "$base/usr/share/applications"
cat > "$base/usr/bin/aevra-desktop" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
exec /usr/lib/aevra/.venv/bin/aevra-python /usr/lib/aevra/apps/desktop/launcher.py "$@"
LAUNCH
chmod 0755 "$base/usr/bin/aevra-desktop"
cat > "$base/usr/share/applications/aevra.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Aevra
Comment=Local Assistant desktop
Exec=aevra-desktop
Icon=/usr/lib/aevra/apps/branding/assets/icon.png
Terminal=false
Categories=Utility;
DESKTOP
mkdir -p "$out"
chmod 0644 "$base/DEBIAN/control" "$base/usr/share/applications/aevra.desktop"
output="$out/aevra-linux-amd64_v${version}.deb"
dpkg-deb --build --root-owner-group "$base" "$output" >/dev/null
sha256sum "$output"
