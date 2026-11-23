#!/usr/bin/env bash
set -euo pipefail
version="${1:-v0.1.0-alpha.3}"
repo="${Aevra_REPO:-Leiz-Workspace/local-assistant}"
base="https://github.com/${repo}/releases/download/${version}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl --fail --location --proto '=https' --tlsv1.2 "$base/SHA256SUMS" -o "$tmp/SHA256SUMS"
archive="local-assistant-${version#v}-$(curl --fail -sS "https://api.github.com/repos/${repo}/releases/tags/${version}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["target_commitish"][:7])').tar.gz"
curl --fail --location --proto '=https' --tlsv1.2 "$base/$archive" -o "$tmp/$archive"
(cd "$tmp" && grep " $archive$" SHA256SUMS | sha256sum -c -)
install_root="${Aevra_INSTALL_ROOT:-$HOME/.local/lib/aevra/$version}"
mkdir -p "$install_root"
tar -xzf "$tmp/$archive" -C "$install_root" --strip-components=1
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/aevra" <<LAUNCH
#!/usr/bin/env bash
exec uv run --offline --project "$install_root" --no-sync aevra "\$@"
LAUNCH
chmod 0755 "$HOME/.local/bin/aevra"
printf 'Installed Aevra %s at %s\n' "$version" "$install_root"
