#!/usr/bin/env bash
set -euo pipefail
version="${1:-0.1.0-alpha.3}"
out="${2:-dist}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
pkg="aevra-desktop"
base="$work/${pkg}_${version}_amd64"
mkdir -p "$base/DEBIAN" "$base/usr/lib/aevra" "$base/usr/bin" "$base/usr/share/applications"
cat > "$base/DEBIAN/control" <<CTRL
Package: $pkg
Version: $version
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Aevra project
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1, uv
Description: Aevra native desktop
 Local Assistant desktop using the pinned local Qwen/llama.cpp web UI.
CTRL
cp -a "$root/apps" "$root/src" "$root/pyproject.toml" "$root/uv.lock" "$base/usr/lib/aevra/"
mkdir -p "$base/usr/lib/aevra/data"
cp -a "$root/data/ui" "$base/usr/lib/aevra/data/"
mkdir -p "$base/usr/lib/aevra/apps/branding/assets"
cp -a "$root/apps/branding/assets/." "$base/usr/lib/aevra/apps/branding/assets/"
cat > "$base/usr/bin/aevra-desktop" <<'LAUNCH'
#!/usr/bin/env bash
set -euo pipefail
exec uv run --offline --no-project --python /usr/bin/python3 python /usr/lib/aevra/apps/desktop/main.py "$@"
LAUNCH
chmod 0755 "$base/usr/bin/aevra-desktop"
cat > "$base/usr/share/applications/aevra.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Aevra
Comment=Local Assistant desktop
Exec=aevra-desktop
Terminal=false
Categories=Utility;
DESKTOP
mkdir -p "$out"
dpkg-deb --build --root-owner-group "$base" "$out/${pkg}_${version}_amd64.deb" >/dev/null
sha256sum "$out/${pkg}_${version}_amd64.deb"
