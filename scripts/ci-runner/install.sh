#!/usr/bin/env bash
# Install the Home Server's self-hosted GitHub Actions runner (ADR-194) as an unprivileged systemd service.
#
# Run as your own user (not root). The script asks sudo only for the system steps: creating the
# runner user, unpacking the pinned runner and installing the service. The registration token
# comes from your authenticated gh CLI, is passed through stdin and is never printed.
# A rerun applies a changed unit file and restarts the service, but refuses while a job runs.
# It refuses a repository that is not private. That check runs only here: before making the
# repository public later, run uninstall.sh.
# Overrides: RUNNER_REPO (default DungeonLeiz/local-assistant), RUNNER_NAME, RUNNER_VERSION, RUNNER_SHA256.
#
#   scripts/ci-runner/install.sh            install and start the runner
#   scripts/ci-runner/install.sh --use      also set CI_RUNS_ON so every CI job uses it
set -euo pipefail

REPO="${RUNNER_REPO:-DungeonLeiz/local-assistant}"
RUNNER_VERSION="${RUNNER_VERSION:-2.338.2}"
RUNNER_SHA256="${RUNNER_SHA256:-baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40}"
RUNNER_NAME="${RUNNER_NAME:-aevra-home-1}"
# Fixed on purpose: the unit, uninstall.sh, README, ADR-194 and ci.yml all name these values.
RUNNER_USER="gh-runner"
RUNNER_HOME="/var/lib/gh-runner"
RUNNER_LABEL="aevra-home"
RUNS_ON="[\"self-hosted\",\"${RUNNER_LABEL}\"]"
SERVICE="aevra-gh-runner"
UNIT_PATH="/etc/systemd/system/${SERVICE}.service"
# The runner user sees only this PATH (config.sh freezes it in .path) and no /home.
RUNNER_PATH="/usr/local/bin:/usr/bin:/bin"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() { echo "error: $*" >&2; exit 1; }
step() { echo "==> $*"; }

use=0
for arg in "$@"; do
  case "$arg" in
    --use) use=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

[ "$(id -u)" -ne 0 ] || die "run as your own user; the script calls sudo for the system steps"
command -v gh >/dev/null || die "gh CLI is required"
gh auth status >/dev/null 2>&1 || die "gh is not authenticated (run: gh auth login)"
command -v systemctl >/dev/null || die "systemd is required"
[[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || die "invalid RUNNER_REPO"
[[ "$RUNNER_NAME" =~ ^[A-Za-z0-9_.-]+$ ]] || die "invalid RUNNER_NAME"
[[ "$RUNNER_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid RUNNER_VERSION"
[[ "$RUNNER_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "invalid RUNNER_SHA256"
# ADR-194: a fork pull request on a public repository could run arbitrary code on the Home Server.
# Checked before any sudo step, so it covers registration, a rerun that keeps the tree, and --use.
visibility="$(gh api "repos/${REPO}" --jq .visibility)" \
  || die "cannot read the visibility of ${REPO}; nothing was changed"
[ "$visibility" = private ] \
  || die "${REPO} is ${visibility:-of unknown visibility}, not private; refusing to attach the runner (ADR-194)"

# Print one jq expression evaluated on this runner's entry in the repository's runner list.
runner_field() {
  gh api "repos/${REPO}/actions/runners" --paginate \
    --jq ".runners[] | select(.name == \"${RUNNER_NAME}\") | $1"
}

# The account must be a non-root system account whose home is RUNNER_HOME and owns it.
check_runner_account() {
  local uid
  uid="$(id -u "$RUNNER_USER")"
  [ "$uid" -gt 0 ] && [ "$uid" -lt 1000 ] || die "${RUNNER_USER} has uid ${uid}; expected a non-root system account"
  [ "$(getent passwd "$RUNNER_USER" | cut -d: -f6)" = "$RUNNER_HOME" ] || die "the home of ${RUNNER_USER} is not ${RUNNER_HOME}; refusing"
  if sudo test -e "$RUNNER_HOME"; then
    [ "$(sudo stat -c %u -- "$RUNNER_HOME")" = "$uid" ] || die "${RUNNER_HOME} is not owned by ${RUNNER_USER}; refusing"
  fi
}

step "Checking that the host has the Home Server layout the test jobs expect"
# node is not needed on the host: the test jobs install it with actions/setup-node.
for tool in bwrap ffmpeg ffprobe tesseract pdftotext soffice git; do
  env -i PATH="$RUNNER_PATH" bash -c 'command -v "$1"' _ "$tool" >/dev/null \
    || die "missing tool on ${RUNNER_PATH}: $tool"
done
[ -x /usr/bin/python3.12 ] || die "missing /usr/bin/python3.12"
# The unit hides /run/tailscale only if it exists when the service starts (ADR-194).
if systemctl cat tailscaled.service >/dev/null 2>&1 && ! systemctl is-active --quiet tailscaled.service; then
  die "tailscaled is installed but not running; start it first so the runner unit can hide its LocalAPI socket"
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

step "Creating the unprivileged user ${RUNNER_USER} (sudo)"
if ! getent passwd "$RUNNER_USER" >/dev/null; then
  ! sudo test -e "$RUNNER_HOME" || die "${RUNNER_HOME} exists but ${RUNNER_USER} does not; remove it or check what owns it"
  sudo useradd --system --user-group --home-dir "$RUNNER_HOME" --shell /usr/sbin/nologin "$RUNNER_USER"
fi
check_runner_account
if id -nG "$RUNNER_USER" | tr ' ' '\n' | grep -Eqx 'root|sudo|adm|docker|lxd|libvirt|disk|video|render'; then
  die "${RUNNER_USER} belongs to a privileged group; refusing to continue"
fi
runner_uid="$(id -u "$RUNNER_USER")"
# Root creates only the home itself, whose parent /var/lib job code cannot change. Everything below
# it is job-writable, so a job could replace runner/ or tmp/ with a symlink: those are created, and
# the runner is unpacked, as the runner user. A planted link then reaches only what that user can
# already change, and any other target makes install or tar fail (a permission error for a
# root-owned directory, "File exists" or "Not a directory" for anything else), which stops the
# script under set -e.
sudo install -d -o "$RUNNER_USER" -g "$RUNNER_USER" -m 0750 "$RUNNER_HOME"
sudo -u "$RUNNER_USER" install -d -m 0750 "$RUNNER_HOME/runner" "$RUNNER_HOME/tmp"

step "Blocking a service manager, lingering and cron for ${RUNNER_USER} (sudo)"
# Job code must not get a systemd user manager outside the unit's sandbox and limits, whether
# through lingering or a PAM session. Also clear anything an earlier, less strict install allowed.
sudo systemctl mask "user@${runner_uid}.service"
sudo loginctl disable-linger "$RUNNER_USER"
if sudo crontab -l -u "$RUNNER_USER" >/dev/null 2>&1; then
  sudo crontab -r -u "$RUNNER_USER"
fi

SSHD_DROPIN="/etc/ssh/sshd_config.d/90-aevra-gh-runner.conf"
if command -v sshd >/dev/null 2>&1 && [ -d /etc/ssh/sshd_config.d ]; then
  step "Denying SSH logins as ${RUNNER_USER} (sudo)"
  # A key that job code plants in ~/.ssh would otherwise give an SSH session outside the unit's
  # sandbox: port forwarding to the tailnet and LAN, the system D-Bus and a standing login.
  # Validate the current configuration first, so a failure below can only come from this drop-in.
  sudo sshd -t \
    || die "the current sshd configuration is invalid (see above); fix it and rerun. The DenyUsers drop-in was not changed"
  dropin_line="DenyUsers ${RUNNER_USER}"
  # Rewrite only a missing or different drop-in. On a rejection, put back exactly what was there
  # before: an earlier install's denial is restored, never dropped; only a new file is removed.
  if ! sudo test -f "$SSHD_DROPIN" || [ "$(sudo cat -- "$SSHD_DROPIN")" != "$dropin_line" ]; then
    had_dropin=0
    if sudo test -e "$SSHD_DROPIN"; then
      had_dropin=1
      sudo cp -p -- "$SSHD_DROPIN" "$work/sshd-dropin.prev"
    fi
    printf '%s\n' "$dropin_line" | sudo tee "$SSHD_DROPIN" >/dev/null
    sudo chmod 0644 "$SSHD_DROPIN"
    if ! sudo sshd -t; then
      if [ "$had_dropin" = 1 ]; then
        sudo cp -p -- "$work/sshd-dropin.prev" "$SSHD_DROPIN"
        die "sshd rejected the DenyUsers drop-in; the previous ${SSHD_DROPIN} was restored"
      fi
      sudo rm -f -- "$SSHD_DROPIN"
      die "sshd rejected the DenyUsers drop-in; the new ${SSHD_DROPIN} was removed"
    fi
  fi
  # Capture first: grep -q in a pipe exits at the first match and could kill sshd with SIGPIPE,
  # which pipefail would report as a missing denial.
  sshd_cfg="$(sudo sshd -T -C "user=${RUNNER_USER},host=localhost,addr=127.0.0.1" 2>/dev/null)" \
    || die "sshd -T failed for ${RUNNER_USER}"
  grep -Eqi "^denyusers .*\\b${RUNNER_USER}\\b" <<<"$sshd_cfg" \
    || die "sshd does not read ${SSHD_DROPIN} (no Include of sshd_config.d?); add 'DenyUsers ${RUNNER_USER}' to sshd_config yourself"
  # A socket-activated sshd reads the configuration per connection; a running ssh.service needs a reload.
  if systemctl is-active --quiet ssh.service; then sudo systemctl reload ssh.service; fi
fi

if sudo test -f "$RUNNER_HOME/runner/.runner"; then
  step "A runner is already configured in ${RUNNER_HOME}/runner; keeping it"
  echo "note: the existing runner tree is trusted as-is. To rebuild it from the pinned, verified" \
    "tarball, run uninstall.sh first (it deletes the tree); after a suspected compromise, run" \
    "uninstall.sh --purge (README, Recovery)." >&2
else
  tarball="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
  step "Downloading the pinned runner ${RUNNER_VERSION}"
  curl -fsSL --proto '=https' --tlsv1.2 -o "$work/$tarball" \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${tarball}"
  echo "${RUNNER_SHA256}  $work/$tarball" | sha256sum --check --status || die "runner checksum mismatch"
  echo "checksum verified"

  step "Unpacking the runner as ${RUNNER_USER} (sudo)"
  # The tarball goes through stdin: $work is a 0700 directory the runner user cannot read.
  sudo -u "$RUNNER_USER" tar -xzf - --no-same-owner -C "$RUNNER_HOME/runner" < "$work/$tarball"

  step "Registering ${RUNNER_NAME} with the label ${RUNNER_LABEL} on ${REPO}"
  token="$(gh api -X POST "repos/${REPO}/actions/runners/registration-token" --jq .token)"
  [ -n "$token" ] || die "could not obtain a registration token"
  # The runner reads ACTIONS_RUNNER_INPUT_<NAME> variables as arguments; the token stays off argv.
  printf '%s' "$token" | sudo -u "$RUNNER_USER" -H env -i \
    HOME="$RUNNER_HOME" PATH="$RUNNER_PATH" \
    REPO="$REPO" RUNNER_NAME="$RUNNER_NAME" RUNNER_LABEL="$RUNNER_LABEL" \
    bash -c 'cd "$HOME/runner" && ACTIONS_RUNNER_INPUT_TOKEN="$(cat)" exec ./config.sh --unattended \
      --url "https://github.com/$REPO" --name "$RUNNER_NAME" --labels "$RUNNER_LABEL" \
      --work _work --replace'
  unset token
fi
# The unit starts bin/runsvc.sh from the runner tree; fail here rather than in a restart loop.
sudo test -f "$RUNNER_HOME/runner/bin/runsvc.sh" || die "the runner tree has no bin/runsvc.sh"

step "Installing the ${SERVICE} service (sudo)"
sed -e "s#@RUNNER_USER@#${RUNNER_USER}#g" -e "s#@RUNNER_HOME@#${RUNNER_HOME}#g" \
  "$HERE/${SERVICE}.service" > "$work/${SERVICE}.service"
changed=1
if [ -f "$UNIT_PATH" ] && cmp -s "$work/${SERVICE}.service" "$UNIT_PATH"; then changed=0; fi
if [ "$changed" = 1 ] && systemctl is-active --quiet "$SERVICE"; then
  # Checked before the new file is installed, so an aborted run still restarts on the next try.
  busy="$(runner_field .busy)" || die "cannot read the state of ${RUNNER_NAME} from GitHub; nothing was changed"
  [ "$busy" != "true" ] || die "${RUNNER_NAME} is running a job; rerun when it is idle so the new unit can be applied"
fi
sudo install -m 0644 -o root -g root "$work/${SERVICE}.service" "$UNIT_PATH"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
if [ "$changed" = 1 ]; then
  step "The unit changed; restarting ${SERVICE} so the new settings apply"
  sudo systemctl restart "$SERVICE"
  sleep 5   # let a restarted runner drop its old session before polling
else
  sudo systemctl start "$SERVICE"   # no-op when it is already running
fi

step "Waiting for the runner to come online"
online=0
for _ in $(seq 1 30); do
  status="$(runner_field .status 2>/dev/null || true)"
  if systemctl is-active --quiet "$SERVICE" && [ "$status" = "online" ]; then online=1; break; fi
  sleep 2
done
[ "$online" = 1 ] || die "runner ${RUNNER_NAME} is not online; check: sudo journalctl -u ${SERVICE} -n 50"
main_pid="$(systemctl show -p MainPID --value "$SERVICE")"
grep -Eq '^NoNewPrivs:[[:space:]]+1$' "/proc/${main_pid}/status" \
  || die "${SERVICE} runs without no_new_privs; check the installed unit"
echo "runner ${RUNNER_NAME} is online"

if [ "$use" = 1 ]; then
  labels="$(runner_field '.labels[].name')" || die "cannot read the labels of ${RUNNER_NAME}; CI_RUNS_ON was not set"
  for label in self-hosted "$RUNNER_LABEL"; do
    grep -qixF -- "$label" <<<"$labels" \
      || die "runner ${RUNNER_NAME} is not registered with the label ${label}; CI_RUNS_ON was not set"
  done
  step "Routing every CI job to the self-hosted runner (CI_RUNS_ON)"
  gh variable set CI_RUNS_ON --repo "$REPO" --body "$RUNS_ON"
fi

cat <<EOF

Done. The runner runs as ${RUNNER_USER} with no access to /home (owner files, Vault bootstrap,
models, data/) or the GPU, and no direct connections to the LAN, Docker or k3s networks.
Services listening on loopback stay reachable. Redis (127.0.0.1:6379) accepts every command
without authentication, and sshd on 127.0.0.1:22 accepts password guesses for other accounts.
The unit hides tailscaled's LocalAPI socket; the self-hosted preflight reports it if that mask
is ever lost. See ADR-194, Residual risks.
  Status:         sudo systemctl status ${SERVICE}
  Pause (benchmarks, D87): sudo systemctl stop ${SERVICE}
  Resume:         sudo systemctl start ${SERVICE}
  Use it for CI:  gh variable set CI_RUNS_ON --repo ${REPO} --body '${RUNS_ON}'
  Back to GitHub-hosted: gh variable delete CI_RUNS_ON --repo ${REPO}
EOF
