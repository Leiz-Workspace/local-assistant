#!/usr/bin/env bash
# Install the Home Server's shared self-hosted GitHub Actions runners (ADR-194, ADR-196): RUNNER_COUNT
# organization-level runner instances for RUNNER_ORG, each an unprivileged systemd service in one slice.
#
# Run as your own user (not root). The script asks sudo only for the system steps: creating the
# runner user, unpacking the pinned runner and installing the services. The registration token
# comes from your authenticated gh CLI (needs the admin:org scope) or, without that scope, from a
# prompt where you paste the token shown at
# https://github.com/organizations/<org>/settings/actions/runners/new; it is passed through stdin
# and never printed. A rerun applies changed unit files and restarts the instances when they are idle.
# It refuses an organization that holds a repository that is not private. That check runs only
# here: before making any repository of the organization public, run uninstall.sh.
# A runner from the earlier single-repository install (ADR-194 v1) is stopped, deregistered and
# removed. Overrides: RUNNER_ORG (default Leiz-Workspace), RUNNER_COUNT (default 3),
# RUNNER_USE_REPOS, RUNNER_V1_REPO, RUNNER_VERSION, RUNNER_SHA256.
#
#   scripts/ci-runner/install.sh            install and start the runners
#   scripts/ci-runner/install.sh --use      also set CI_RUNS_ON in RUNNER_USE_REPOS
set -euo pipefail

ORG="${RUNNER_ORG:-Leiz-Workspace}"
COUNT="${RUNNER_COUNT:-3}"
USE_REPOS="${RUNNER_USE_REPOS:-local-assistant web-cloner-template Mirrix}"
# The repository the v1 runner was registered to (it moved into the organization with it).
V1_REPO="${RUNNER_V1_REPO:-${ORG}/local-assistant}"
RUNNER_VERSION="${RUNNER_VERSION:-2.338.2}"
RUNNER_SHA256="${RUNNER_SHA256:-baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40}"
# Fixed on purpose: the units, uninstall.sh, README, ADR-194/196 and the workflows name these values.
RUNNER_USER="gh-runner"
RUNNER_HOME="/var/lib/gh-runner"
RUNNER_LABEL="aevra-home"
NAME_PREFIX="aevra-home-"
RUNS_ON="[\"self-hosted\",\"${RUNNER_LABEL}\"]"
TEMPLATE="aevra-gh-runner@"
SLICE="system-ghrunners.slice"
V1_SERVICE="aevra-gh-runner"
# The runner user sees only this PATH (config.sh freezes it in .path) and no /home.
RUNNER_PATH="/usr/local/bin:/usr/bin:/bin"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

die() { echo "error: $*" >&2; exit 1; }
step() { echo "==> $*"; }

use=0
for arg in "$@"; do
  case "$arg" in
    --use) use=1 ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

[ "$(id -u)" -ne 0 ] || die "run as your own user; the script calls sudo for the system steps"
command -v gh >/dev/null || die "gh CLI is required"
gh auth status >/dev/null 2>&1 || die "gh is not authenticated (run: gh auth login)"
command -v systemctl >/dev/null || die "systemd is required"
[[ "$ORG" =~ ^[A-Za-z0-9_.-]+$ ]] || die "invalid RUNNER_ORG"
[[ "$COUNT" =~ ^[1-9]$ ]] || die "RUNNER_COUNT must be 1-9"
[[ "$V1_REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || die "invalid RUNNER_V1_REPO"
for repo in $USE_REPOS; do [[ "$repo" =~ ^[A-Za-z0-9_.-]+$ ]] || die "invalid name in RUNNER_USE_REPOS: $repo"; done
[[ "$RUNNER_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid RUNNER_VERSION"
[[ "$RUNNER_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "invalid RUNNER_SHA256"

# ADR-194/196: a fork pull request on a public repository could run arbitrary code on the Home Server,
# and an organization-level runner serves every repository the runner group allows. Checked before any
# sudo step, so it covers registration, a rerun that keeps the trees, and --use.
nonprivate="$(gh api "orgs/${ORG}/repos?type=all" --paginate --jq '.[] | select(.visibility != "private") | .full_name')" \
  || die "cannot list the repositories of ${ORG}; nothing was changed"
[ -z "$nonprivate" ] || die "${ORG} has repositories that are not private (${nonprivate//$'\n'/, }); refusing (ADR-196)"
# With admin:org the Default runner group must also refuse public repositories; without it the
# repository check above is the guard (GitHub's default for a runner group is to refuse them).
if group_public="$(gh api "orgs/${ORG}/actions/runner-groups" --jq '.runner_groups[] | select(.default) | .allows_public_repositories' 2>/dev/null)"; then
  [ "$group_public" = false ] || die "the Default runner group of ${ORG} allows public repositories; turn that off first"
  admin_org=1
else
  admin_org=0
  echo "note: gh has no admin:org scope; the registration token will be asked for, and runner status is read from the journal"
fi

# Print one jq expression for every organization runner whose name starts with NAME_PREFIX (needs admin:org).
org_runners() {
  gh api "orgs/${ORG}/actions/runners" --paginate --jq ".runners[] | select(.name | startswith(\"${NAME_PREFIX}\")) | $1"
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

# True when a job runs in the unit: a Runner.Worker process sits in its cgroup. Read locally, so it
# needs no API scope and no trust in job-writable files.
unit_busy() {
  local cg pid
  cg="$(systemctl show -p ControlGroup --value "$1" 2>/dev/null)"
  [ -n "$cg" ] && [ -r "/sys/fs/cgroup${cg}/cgroup.procs" ] || return 1
  while read -r pid; do
    [ "$(cat "/proc/${pid}/comm" 2>/dev/null)" = "Runner.Worker" ] && return 0
  done < "/sys/fs/cgroup${cg}/cgroup.procs"
  return 1
}

user_procs() { pgrep -u "$RUNNER_USER" >/dev/null || pgrep -U "$RUNNER_USER" >/dev/null; }

step "Checking that the host has the Home Server layout the test jobs expect"
# node is not needed on the host: the jobs install it with actions/setup-node.
for tool in bwrap ffmpeg ffprobe tesseract pdftotext soffice git jq gh; do
  env -i PATH="$RUNNER_PATH" bash -c 'command -v "$1"' _ "$tool" >/dev/null \
    || die "missing tool on ${RUNNER_PATH}: $tool"
done
[ -x /usr/bin/python3.12 ] || die "missing /usr/bin/python3.12"
# Mirrix's Linux smoke test runs Electron under xvfb-run, and the runners have no sudo to install it.
if [ "$use" = 1 ] && [[ " $USE_REPOS " == *" Mirrix "* ]]; then
  env -i PATH="$RUNNER_PATH" bash -c 'command -v xvfb-run' >/dev/null \
    || die "missing xvfb-run for Mirrix's Linux smoke test: run 'sudo apt install xvfb', or leave Mirrix out of RUNNER_USE_REPOS"
fi
# The units hide /run/tailscale only if it exists when a service starts (ADR-194).
if systemctl cat tailscaled.service >/dev/null 2>&1 && ! systemctl is-active --quiet tailscaled.service; then
  die "tailscaled is installed but not running; start it first so the runner units can hide its LocalAPI socket"
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Which instances need a fresh runner tree. Before the pool's template unit exists, every tree under
# runners/ is untrusted (job code of the v1 runner could write there) and is rebuilt.
pool_installed=0
[ -f "/etc/systemd/system/${TEMPLATE}.service" ] && pool_installed=1
v1_present=0
if [ -f "/etc/systemd/system/${V1_SERVICE}.service" ] || sudo test -e "$RUNNER_HOME/runner"; then v1_present=1; fi
to_configure=()
for i in $(seq 1 "$COUNT"); do
  if [ "$pool_installed" = 0 ] || ! sudo test -f "$RUNNER_HOME/runners/$i/.runner"; then to_configure+=("$i"); fi
done

# Everything that can fail without changing the host comes first: the download and the token. A
# rejected token or a failed download then leaves the v1 runner, and CI, as they were.
tarball="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
token=""
if [ "${#to_configure[@]}" -gt 0 ]; then
  step "Downloading the pinned runner ${RUNNER_VERSION}"
  curl -fsSL --proto '=https' --tlsv1.2 -o "$work/$tarball" \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${tarball}"
  echo "${RUNNER_SHA256}  $work/$tarball" | sha256sum --check --status || die "runner checksum mismatch"
  echo "checksum verified"
  if [ "$admin_org" = 1 ]; then
    token="$(gh api -X POST "orgs/${ORG}/actions/runners/registration-token" --jq .token)" || token=""
  fi
  if [ -z "$token" ]; then
    echo "Open https://github.com/organizations/${ORG}/settings/actions/runners/new, copy the token" \
      "from its ./config.sh line (the value after --token), and paste it here (input hidden; valid for one hour):" >&2
    read -rs token </dev/tty || die "no registration token was read; nothing was changed"
    echo >&2
  fi
  [[ "$token" =~ ^[A-Za-z0-9]{20,}$ ]] || die "that does not look like a registration token; nothing was changed"
fi

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

step "Blocking a service manager, lingering and cron for ${RUNNER_USER} (sudo)"
# Job code must not get a systemd user manager outside the units' sandbox and limits, whether
# through lingering or a PAM session. Also clear anything an earlier, less strict install allowed.
sudo systemctl mask "user@${runner_uid}.service"
sudo loginctl disable-linger "$RUNNER_USER"
if sudo crontab -l -u "$RUNNER_USER" >/dev/null 2>&1; then
  sudo crontab -r -u "$RUNNER_USER"
fi

SSHD_DROPIN="/etc/ssh/sshd_config.d/90-aevra-gh-runner.conf"
if command -v sshd >/dev/null 2>&1 && [ -d /etc/ssh/sshd_config.d ]; then
  step "Denying SSH logins as ${RUNNER_USER} (sudo)"
  # A key that job code plants in ~/.ssh would otherwise give an SSH session outside the units'
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
  # which pipefail would report as a missing denial. The user name must be a whole word there.
  sshd_cfg="$(sudo sshd -T -C "user=${RUNNER_USER},host=localhost,addr=127.0.0.1" 2>/dev/null)" \
    || die "sshd -T failed for ${RUNNER_USER}"
  grep -Eqi "^denyusers( .*)? ${RUNNER_USER}( |\$)" <<<"$sshd_cfg" \
    || die "sshd does not read ${SSHD_DROPIN} (no Include of sshd_config.d?); add 'DenyUsers ${RUNNER_USER}' to sshd_config yourself"
  # A socket-activated sshd reads the configuration per connection; a running ssh.service needs a reload.
  if systemctl is-active --quiet ssh.service; then sudo systemctl reload ssh.service; fi
fi

if [ "$v1_present" = 1 ]; then
  step "Stopping the single-repository runner of the earlier install (ADR-194 v1)"
  if systemctl is-active --quiet "$V1_SERVICE" && unit_busy "${V1_SERVICE}.service"; then
    die "the v1 runner is running a job; rerun when it is idle"
  fi
  if [ -f "/etc/systemd/system/${V1_SERVICE}.service" ]; then
    sudo systemctl disable --now "$V1_SERVICE"
    sudo rm -f "/etc/systemd/system/${V1_SERVICE}.service"
    sudo systemctl daemon-reload
  fi
fi

if [ "${#to_configure[@]}" -gt 0 ]; then
  # config.sh and the runner it starts come from a tree that running jobs could rewrite, and that
  # code would run here outside the units' sandbox. So nothing of the runner user may run meanwhile.
  step "Stopping every runner instance and process of ${RUNNER_USER} before configuring runners (sudo)"
  units="$(systemctl list-units --all --plain --no-legend "${TEMPLATE}*.service" | awk '{print $1}')"
  for unit in $units; do
    if systemctl is-active --quiet "$unit" && unit_busy "$unit"; then
      die "${unit} is running a job; rerun when the runners are idle"
    fi
  done
  for unit in $units; do sudo systemctl stop "$unit"; done
  if user_procs; then
    sudo pkill -KILL -u "$RUNNER_USER" || [ "$?" -eq 1 ]
    sudo pkill -KILL -U "$RUNNER_USER" || [ "$?" -eq 1 ]
  fi
  for _ in $(seq 1 20); do user_procs || break; sleep 0.5; done
  ! user_procs || die "processes of ${RUNNER_USER} are still running; nothing was configured"
fi
# Job code could rewrite these trees, credentials included; they are deleted, never executed. rm
# removes a symlink planted in their place, not its target.
if [ "$v1_present" = 1 ]; then sudo rm -rf --one-file-system -- "$RUNNER_HOME/runner"; fi
if [ "$pool_installed" = 0 ]; then sudo rm -rf --one-file-system -- "$RUNNER_HOME/runners"; fi

if [ "$v1_present" = 1 ]; then
  step "Deregistering the v1 runner from ${V1_REPO}"
  # The id comes from GitHub, never from the job-writable runner tree; repository admin is enough.
  ids="$(gh api "repos/${V1_REPO}/actions/runners" --paginate --jq ".runners[] | select(.name == \"${NAME_PREFIX}1\") | .id")" \
    || die "cannot read the runners of ${V1_REPO}; the v1 service is stopped and its tree deleted, rerun to finish"
  for id in $ids; do
    [[ "$id" =~ ^[0-9]+$ ]] || die "unexpected runner id from the GitHub API"
    gh api -X DELETE "repos/${V1_REPO}/actions/runners/${id}" >/dev/null \
      || die "could not deregister the v1 runner ${id} from ${V1_REPO}; rerun to finish"
  done
fi

# Root creates only the home itself, whose parent /var/lib job code cannot change. Everything below
# it is job-writable, so a job could replace runners/ or tmp/ with a symlink: those are created, and
# the runner is unpacked, as the runner user. A planted link then reaches only what that user can
# already change, and any other target makes install or tar fail (a permission error for a
# root-owned directory, "File exists" or "Not a directory" for anything else), which stops the
# script under set -e.
sudo install -d -o "$RUNNER_USER" -g "$RUNNER_USER" -m 0750 "$RUNNER_HOME"
sudo -u "$RUNNER_USER" install -d -m 0750 "$RUNNER_HOME/runners" "$RUNNER_HOME/tmp"
for i in $(seq 1 "$COUNT"); do
  sudo -u "$RUNNER_USER" install -d -m 0750 "$RUNNER_HOME/tmp/$i"
done

for i in "${to_configure[@]}"; do
  name="${NAME_PREFIX}${i}"
  dir="$RUNNER_HOME/runners/$i"
  step "Unpacking a fresh runner for ${name} as ${RUNNER_USER} (sudo)"
  # Delete as the runner user: a symlink planted in runners/ then reaches nothing that user cannot
  # already change.
  sudo -u "$RUNNER_USER" rm -rf -- "$dir"
  sudo -u "$RUNNER_USER" install -d -m 0750 "$dir"
  # The tarball goes through stdin: $work is a 0700 directory the runner user cannot read.
  sudo -u "$RUNNER_USER" tar -xzf - --no-same-owner -C "$dir" < "$work/$tarball"
  step "Registering ${name} with the label ${RUNNER_LABEL} in the ${ORG} organization"
  # The runner reads ACTIONS_RUNNER_INPUT_<NAME> variables as arguments; the token stays off argv.
  printf '%s' "$token" | sudo -u "$RUNNER_USER" -H env -i \
    HOME="$RUNNER_HOME" PATH="$RUNNER_PATH" \
    ORG="$ORG" NAME="$name" LABEL="$RUNNER_LABEL" DIR="$dir" \
    bash -c 'cd "$DIR" && ACTIONS_RUNNER_INPUT_TOKEN="$(cat)" exec ./config.sh --unattended \
      --url "https://github.com/$ORG" --name "$NAME" --labels "$LABEL" \
      --runnergroup Default --work _work --replace'
done
unset token
for i in $(seq 1 "$COUNT"); do
  # The units start bin/runsvc.sh from each tree; fail here rather than in a restart loop.
  sudo test -f "$RUNNER_HOME/runners/$i/bin/runsvc.sh" || die "the runner tree $i has no bin/runsvc.sh"
done

step "Installing ${SLICE} and the ${TEMPLATE}.service template (sudo)"
render() { sed -e "s#@RUNNER_USER@#${RUNNER_USER}#g" -e "s#@RUNNER_HOME@#${RUNNER_HOME}#g" "$HERE/$1" > "$work/$1"; }
render "$SLICE"
render "${TEMPLATE}.service"
changed=0
for f in "$SLICE" "${TEMPLATE}.service"; do
  cmp -s "$work/$f" "/etc/systemd/system/$f" 2>/dev/null || changed=1
done
if [ "$changed" = 1 ]; then
  # Checked before the new files are installed, so an aborted run still restarts on the next try.
  for i in $(seq 1 "$COUNT"); do
    unit="${TEMPLATE}${i}.service"
    if systemctl is-active --quiet "$unit" && unit_busy "$unit"; then
      die "${NAME_PREFIX}${i} is running a job; rerun when the runners are idle so the new units can be applied"
    fi
  done
fi
sudo install -m 0644 -o root -g root "$work/$SLICE" "/etc/systemd/system/$SLICE"
sudo install -m 0644 -o root -g root "$work/${TEMPLATE}.service" "/etc/systemd/system/${TEMPLATE}.service"
sudo systemctl daemon-reload
for i in $(seq 1 "$COUNT"); do
  unit="${TEMPLATE}${i}.service"
  sudo systemctl enable "$unit"
  if [ "$changed" = 1 ]; then sudo systemctl restart "$unit"; else sudo systemctl start "$unit"; fi
done
# Instances above COUNT from an earlier, larger install are left alone; uninstall.sh removes them.
for unit in $(systemctl list-units --all --plain --no-legend "${TEMPLATE}*.service" | awk '{print $1}'); do
  n="${unit#"${TEMPLATE}"}"; n="${n%.service}"
  if [[ "$n" =~ ^[0-9]+$ ]] && [ "$n" -gt "$COUNT" ]; then
    echo "note: ${unit} is above RUNNER_COUNT=${COUNT}; stop it with uninstall.sh or rerun with a larger count" >&2
  fi
done

step "Waiting for the runners to come online"
for i in $(seq 1 "$COUNT"); do
  unit="${TEMPLATE}${i}.service"
  name="${NAME_PREFIX}${i}"
  online=0
  for _ in $(seq 1 45); do
    if systemctl is-active --quiet "$unit"; then
      if [ "$admin_org" = 1 ]; then
        [ "$(org_runners "select(.name == \"${name}\") | .status" 2>/dev/null)" = online ] && { online=1; break; }
      else
        # The runner prints this once per start, so read the current invocation's journal only;
        # Restart=on-failure starts a new invocation, so the id is read on every poll.
        inv="$(systemctl show -p InvocationID --value "$unit")"
        if [ -n "$inv" ] && sudo journalctl "_SYSTEMD_INVOCATION_ID=${inv}" --no-pager -q 2>/dev/null | grep -q "Listening for Jobs"; then
          online=1; break
        fi
      fi
    fi
    sleep 2
  done
  [ "$online" = 1 ] || die "runner ${name} is not online; check: sudo journalctl -u ${unit} -n 50"
  main_pid="$(systemctl show -p MainPID --value "$unit")"
  grep -Eq '^NoNewPrivs:[[:space:]]+1$' "/proc/${main_pid}/status" \
    || die "${unit} runs without no_new_privs; check the installed unit"
  echo "runner ${name} is online"
done

if [ "$use" = 1 ]; then
  if [ "$admin_org" = 1 ]; then
    for i in $(seq 1 "$COUNT"); do
      labels="$(org_runners "select(.name == \"${NAME_PREFIX}${i}\") | .labels[].name")" \
        || die "cannot read the labels of ${NAME_PREFIX}${i}; CI_RUNS_ON was not set"
      for label in self-hosted "$RUNNER_LABEL"; do
        grep -qixF -- "$label" <<<"$labels" \
          || die "runner ${NAME_PREFIX}${i} is not registered with the label ${label}; CI_RUNS_ON was not set"
      done
    done
  fi
  step "Routing CI jobs of ${USE_REPOS} to the shared runners (CI_RUNS_ON)"
  for repo in $USE_REPOS; do
    gh variable set CI_RUNS_ON --repo "${ORG}/${repo}" --body "$RUNS_ON"
  done
fi

cat <<EOF

Done. ${COUNT} runners run as ${RUNNER_USER} in ${SLICE}, with no access to /home (owner files,
Vault bootstrap, models, data/) or the GPU, and no direct connections to the LAN, Docker or k3s
networks. Every repository of ${ORG} that the Default runner group allows can use them, and jobs
of all those repositories share one user (ADR-196). Services listening on loopback stay
reachable. Redis (127.0.0.1:6379) accepts every command without authentication, and sshd on
127.0.0.1:22 accepts password guesses for other accounts. The units hide tailscaled's LocalAPI
socket; the self-hosted preflight reports it if that mask is ever lost. See ADR-194/196.
  Status:         systemctl status '${TEMPLATE}*' ${SLICE}
  Pause (benchmarks, D87): sudo systemctl stop '${TEMPLATE}*'
  Resume:         sudo systemctl start ${TEMPLATE}{1..${COUNT}}
  Use it for CI:  gh variable set CI_RUNS_ON --repo ${ORG}/<repo> --body '${RUNS_ON}'
  Back to GitHub-hosted: gh variable delete CI_RUNS_ON --repo ${ORG}/<repo>
EOF
