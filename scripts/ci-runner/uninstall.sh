#!/usr/bin/env bash
# Remove the Home Server's self-hosted GitHub Actions runner (ADR-194).
#
# Run as your own user (not root); sudo is used for the system steps.
#   scripts/ci-runner/uninstall.sh           delete CI_RUNS_ON, stop the service, kill every process of
#                                            the runner user, delete its ~/.ssh, deregister the runner
#                                            through the GitHub API, delete the runner tree and remove
#                                            the unit
#   scripts/ci-runner/uninstall.sh --purge   also delete the user and its home and remove its SSH denial
# Overrides: RUNNER_REPO (default DungeonLeiz/local-assistant), RUNNER_NAME.
# CI falls back to GitHub-hosted runners once CI_RUNS_ON is deleted. If that deletion fails, the
# script stops before touching the runner. Nothing in the runner tree is ever executed here: job
# code can rewrite that tree, so it is deleted, not run.
set -euo pipefail

REPO="${RUNNER_REPO:-DungeonLeiz/local-assistant}"
RUNNER_NAME="${RUNNER_NAME:-aevra-home-1}"
# Fixed on purpose: install.sh creates exactly this account and home.
RUNNER_USER="gh-runner"
RUNNER_HOME="/var/lib/gh-runner"
SERVICE="aevra-gh-runner"
UNIT_PATH="/etc/systemd/system/${SERVICE}.service"
CGROUP_PROCS="/sys/fs/cgroup/system.slice/${SERVICE}.service/cgroup.procs"

die() { echo "error: $*" >&2; exit 1; }
step() { echo "==> $*"; }
user_procs() { pgrep -u "$RUNNER_USER" >/dev/null || pgrep -U "$RUNNER_USER" >/dev/null; }

# Print one jq expression evaluated on each entry with this name in the repository's runner list.
runner_field() {
  gh api "repos/${REPO}/actions/runners" --paginate \
    --jq ".runners[] | select(.name == \"${RUNNER_NAME}\") | $1"
}

purge=0
for arg in "$@"; do
  case "$arg" in
    --purge) purge=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done
[ "$(id -u)" -ne 0 ] || die "run as your own user; the script calls sudo for the system steps"
command -v gh >/dev/null || die "gh CLI is required"
gh auth status >/dev/null 2>&1 || die "gh is not authenticated (run: gh auth login); nothing was changed"
[[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || die "invalid RUNNER_REPO"
[[ "$RUNNER_NAME" =~ ^[A-Za-z0-9_.-]+$ ]] || die "invalid RUNNER_NAME"

# Sanity checks before anything changes: only the runner's own system account, its processes and
# its home are touched.
runner_uid=""
if getent passwd "$RUNNER_USER" >/dev/null; then
  runner_uid="$(id -u "$RUNNER_USER")"
  [ "$runner_uid" -gt 0 ] && [ "$runner_uid" -lt 1000 ] \
    || die "${RUNNER_USER} has uid ${runner_uid}; refusing; nothing was changed"
  [ "$(getent passwd "$RUNNER_USER" | cut -d: -f6)" = "$RUNNER_HOME" ] \
    || die "the home of ${RUNNER_USER} is not ${RUNNER_HOME}; refusing; nothing was changed"
  if sudo test -e "$RUNNER_HOME"; then
    [ "$(sudo stat -c %u -- "$RUNNER_HOME")" = "$runner_uid" ] \
      || die "${RUNNER_HOME} is not owned by ${RUNNER_USER}; refusing; nothing was changed"
  fi
elif sudo test -e "$RUNNER_HOME"; then
  # An earlier purge deleted the account but not the directory: delete it only if no account owns it.
  ! getent passwd "$(sudo stat -c %u -- "$RUNNER_HOME")" >/dev/null \
    || die "${RUNNER_HOME} belongs to an existing account; refusing; nothing was changed"
fi

step "Routing CI back to GitHub-hosted runners"
# Read the list first: inside an `if gh ... | grep` condition, a gh failure would skip the delete.
names="$(gh variable list --repo "$REPO" --json name --jq '.[].name')" \
  || die "cannot read the variables of ${REPO}; nothing was changed"
if grep -qx CI_RUNS_ON <<<"$names"; then
  gh variable delete CI_RUNS_ON --repo "$REPO" \
    || die "could not delete CI_RUNS_ON; the runner was left running"
fi

step "Stopping ${SERVICE} (sudo)"
if [ -f "$UNIT_PATH" ]; then
  sudo systemctl disable --now "$SERVICE"
fi
if [ -n "$(cat "$CGROUP_PROCS" 2>/dev/null)" ]; then
  # A unit from before KillMode=mixed, or a stop that timed out, can leave job processes behind.
  step "Killing processes left in the ${SERVICE} cgroup (sudo)"
  sudo systemctl kill --kill-whom=all --signal=SIGKILL "$SERVICE"
fi

if [ -n "$runner_uid" ]; then
  # Processes of the runner user may run outside the unit, for example an SSH session opened
  # before install.sh denied SSH logins as that user (ADR-194). None of them may outlive the
  # uninstall, with or without --purge.
  step "Removing lingering, the crontab and every process of ${RUNNER_USER} (sudo)"
  sudo loginctl disable-linger "$RUNNER_USER"
  if sudo crontab -l -u "$RUNNER_USER" >/dev/null 2>&1; then
    sudo crontab -r -u "$RUNNER_USER"
  fi
  if user_procs; then
    # pkill exits 1 when the processes are already gone; any other failure stops the script.
    sudo pkill -KILL -u "$RUNNER_USER" || [ "$?" -eq 1 ]
    sudo pkill -KILL -U "$RUNNER_USER" || [ "$?" -eq 1 ]
  fi
  for _ in $(seq 1 20); do user_procs || break; sleep 0.5; done
  ! user_procs || die "processes of ${RUNNER_USER} are still running; the runner tree and the account were kept"

  # sshd denies SSH logins as the runner user (install.sh, ADR-194), so a key that job code planted
  # in ~/.ssh gives no login. Delete it anyway as defense in depth, in case that denial is ever
  # lost, with or without --purge, now that no process of the user can write a new one. rm removes
  # a planted symlink itself and does not follow it.
  step "Deleting ${RUNNER_HOME}/.ssh (sudo)"
  sudo rm -rf --one-file-system -- "$RUNNER_HOME/.ssh"
fi

step "Deregistering ${RUNNER_NAME} from ${REPO} through the GitHub API"
# The runner id comes from GitHub, not from the job-writable runner/.runner file, and no removal
# token reaches the runner user. This needs the same admin access to the repository as install.sh.
ids="$(runner_field .id)" \
  || die "cannot read the runner list of ${REPO}; the service is stopped and the runner tree was kept, rerun to finish"
[ -n "$ids" ] || echo "note: no runner named ${RUNNER_NAME} is registered on ${REPO}"
for id in $ids; do
  [[ "$id" =~ ^[0-9]+$ ]] || die "unexpected runner id from the GitHub API"
  gh api -X DELETE "repos/${REPO}/actions/runners/${id}" >/dev/null \
    || die "could not deregister runner ${id}; the service is stopped and the runner tree was kept, rerun to finish"
done

step "Deleting the runner tree ${RUNNER_HOME}/runner (sudo)"
# Job code can rewrite this tree, credentials included. A later install.sh unpacks a fresh,
# checksum-verified copy and registers again.
sudo rm -rf --one-file-system -- "$RUNNER_HOME/runner"

step "Removing the unit file (sudo)"
sudo rm -f "$UNIT_PATH"
sudo systemctl daemon-reload

SSHD_DROPIN="/etc/ssh/sshd_config.d/90-aevra-gh-runner.conf"
if [ "$purge" = 1 ] && sudo test -f "$SSHD_DROPIN"; then
  # Without --purge the account stays, so its SSH denial stays too.
  step "Removing the SSH denial for ${RUNNER_USER} (sudo)"
  sudo rm -f "$SSHD_DROPIN"
  if systemctl is-active --quiet ssh.service; then sudo systemctl reload ssh.service; fi
fi

if [ "$purge" = 1 ]; then
  if [ -n "$runner_uid" ]; then
    step "Deleting the user ${RUNNER_USER} (sudo)"
    sudo userdel "$RUNNER_USER"
    # install.sh masked the user manager of this uid; the uid is free now.
    if [ -L "/etc/systemd/system/user@${runner_uid}.service" ]; then
      sudo systemctl unmask "user@${runner_uid}.service"
    fi
  fi
  step "Deleting ${RUNNER_HOME} (sudo)"
  sudo rm -rf --one-file-system -- "$RUNNER_HOME"
fi
# Without --purge the account, the rest of its home (for example ~/.gitconfig and caches written
# by CI jobs), the mask on its user manager and its SSH denial stay; ~/.ssh was deleted above.
echo "Done."
