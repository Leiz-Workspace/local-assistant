#!/usr/bin/env bash
# Remove the Home Server's shared self-hosted GitHub Actions runners (ADR-194, ADR-196).
#
# Run as your own user (not root); sudo is used for the system steps.
#   scripts/ci-runner/uninstall.sh           delete CI_RUNS_ON in RUNNER_USE_REPOS, stop every runner
#                                            instance (and a v1 runner), kill every process of the
#                                            runner user, delete its ~/.ssh, deregister the runners
#                                            through the GitHub API, delete the runner trees and
#                                            remove the units and the slice
#   scripts/ci-runner/uninstall.sh --purge   also delete the user and its home and remove its SSH denial
# Overrides: RUNNER_ORG (default Leiz-Workspace), RUNNER_USE_REPOS, RUNNER_V1_REPO.
# CI falls back to GitHub-hosted runners once CI_RUNS_ON is deleted. If that deletion fails, the
# script stops before touching the runners. Nothing in a runner tree is ever executed here: job
# code can rewrite those trees, so they are deleted, not run. Deregistering organization runners
# needs the admin:org scope; without it the script does everything else, names the page where you
# remove them, and exits with status 3, because their stolen credentials stay valid until then.
set -euo pipefail

ORG="${RUNNER_ORG:-Leiz-Workspace}"
USE_REPOS="${RUNNER_USE_REPOS:-local-assistant web-cloner-template Mirrix}"
V1_REPO="${RUNNER_V1_REPO:-${ORG}/local-assistant}"
# Fixed on purpose: install.sh creates exactly this account, home and these units.
RUNNER_USER="gh-runner"
RUNNER_HOME="/var/lib/gh-runner"
NAME_PREFIX="aevra-home-"
TEMPLATE="aevra-gh-runner@"
SLICE="system-ghrunners.slice"
V1_SERVICE="aevra-gh-runner"

die() { echo "error: $*" >&2; exit 1; }
step() { echo "==> $*"; }
user_procs() { pgrep -u "$RUNNER_USER" >/dev/null || pgrep -U "$RUNNER_USER" >/dev/null; }

purge=0
for arg in "$@"; do
  case "$arg" in
    --purge) purge=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done
[ "$(id -u)" -ne 0 ] || die "run as your own user; the script calls sudo for the system steps"
command -v gh >/dev/null || die "gh CLI is required"
gh auth status >/dev/null 2>&1 || die "gh is not authenticated (run: gh auth login); nothing was changed"
[[ "$ORG" =~ ^[A-Za-z0-9_.-]+$ ]] || die "invalid RUNNER_ORG"
[[ "$V1_REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || die "invalid RUNNER_V1_REPO"
for repo in $USE_REPOS; do [[ "$repo" =~ ^[A-Za-z0-9_.-]+$ ]] || die "invalid name in RUNNER_USE_REPOS: $repo"; done

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

step "Routing CI of ${USE_REPOS} back to GitHub-hosted runners"
for repo in $USE_REPOS; do
  # Read the list first: inside an `if gh ... | grep` condition, a gh failure would skip the delete.
  names="$(gh variable list --repo "${ORG}/${repo}" --json name --jq '.[].name')" \
    || die "cannot read the variables of ${ORG}/${repo}; the runners were left running"
  if grep -qx CI_RUNS_ON <<<"$names"; then
    gh variable delete CI_RUNS_ON --repo "${ORG}/${repo}" \
      || die "could not delete CI_RUNS_ON in ${ORG}/${repo}; the runners were left running"
  fi
done

step "Stopping every runner instance (sudo)"
units="$(systemctl list-units --all --plain --no-legend "${TEMPLATE}*.service" | awk '{print $1}')"
for unit in $units; do
  sudo systemctl disable --now "$unit" || true
done
if [ -f "/etc/systemd/system/${V1_SERVICE}.service" ]; then
  sudo systemctl disable --now "$V1_SERVICE"
fi
# A stop that timed out can leave job processes behind in a unit's cgroup.
for unit in $units "${V1_SERVICE}.service"; do
  cg="$(systemctl show -p ControlGroup --value "$unit" 2>/dev/null || true)"
  if [ -n "$cg" ] && [ -n "$(cat "/sys/fs/cgroup${cg}/cgroup.procs" 2>/dev/null)" ]; then
    step "Killing processes left in ${unit} (sudo)"
    sudo systemctl kill --kill-whom=all --signal=SIGKILL "$unit"
  fi
done

if [ -n "$runner_uid" ]; then
  # Processes of the runner user may run outside the units, for example an SSH session opened
  # before install.sh denied SSH logins as that user. None of them may outlive the uninstall.
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
  ! user_procs || die "processes of ${RUNNER_USER} are still running; the runner trees and the account were kept"
  # A key that job code planted in ~/.ssh gives no login while sshd denies the user; delete it
  # anyway, now that no process of the user can write a new one. rm does not follow a planted link.
  step "Deleting ${RUNNER_HOME}/.ssh (sudo)"
  sudo rm -rf --one-file-system -- "$RUNNER_HOME/.ssh"
fi

org_left=0
step "Deregistering the runners from GitHub"
# Ids come from GitHub, not from the job-writable runner trees, and no removal token reaches the
# runner user. A v1 runner is registered on a repository; repository admin is enough for it.
v1_ids="$(gh api "repos/${V1_REPO}/actions/runners" --paginate --jq ".runners[] | select(.name | startswith(\"${NAME_PREFIX}\")) | .id" 2>/dev/null || true)"
for id in $v1_ids; do
  [[ "$id" =~ ^[0-9]+$ ]] || die "unexpected runner id from the GitHub API"
  gh api -X DELETE "repos/${V1_REPO}/actions/runners/${id}" >/dev/null \
    || die "could not deregister runner ${id} from ${V1_REPO}; the services are stopped and the trees were kept, rerun to finish"
done
if org_ids="$(gh api "orgs/${ORG}/actions/runners" --paginate --jq ".runners[] | select(.name | startswith(\"${NAME_PREFIX}\")) | .id" 2>/dev/null)"; then
  [ -n "$org_ids" ] || echo "note: no runner named ${NAME_PREFIX}* is registered in ${ORG}"
  for id in $org_ids; do
    [[ "$id" =~ ^[0-9]+$ ]] || die "unexpected runner id from the GitHub API"
    gh api -X DELETE "orgs/${ORG}/actions/runners/${id}" >/dev/null \
      || die "could not deregister runner ${id} from ${ORG}; the services are stopped and the trees were kept, rerun to finish"
  done
else
  org_left=1
  echo "warning: gh has no admin:org scope, so the organization runners stay registered (offline), and" \
    "credentials a job may have copied stay valid until they are removed." \
    "Remove the ${NAME_PREFIX}* runners at https://github.com/organizations/${ORG}/settings/actions/runners" \
    "or run: gh auth refresh -h github.com -s admin:org, then rerun this script." >&2
fi

step "Deleting the runner trees (sudo)"
# Job code can rewrite these trees, credentials included. A later install.sh unpacks fresh,
# checksum-verified copies and registers again.
sudo rm -rf --one-file-system -- "$RUNNER_HOME/runners" "$RUNNER_HOME/runner"

step "Removing the units and the slice (sudo)"
sudo rm -f "/etc/systemd/system/${TEMPLATE}.service" "/etc/systemd/system/${V1_SERVICE}.service" \
  "/etc/systemd/system/${SLICE}"
sudo rm -f /etc/systemd/system/multi-user.target.wants/${TEMPLATE}*.service
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
# Without --purge the account, the rest of its home (for example ~/.gitconfig, tmp/ and caches
# written by CI jobs), the mask on its user manager and its SSH denial stay; ~/.ssh was deleted above.
if [ "$org_left" = 1 ]; then
  echo "Done locally. Remove every ${NAME_PREFIX}* runner at https://github.com/organizations/${ORG}/settings/actions/runners" >&2
  exit 3
fi
echo "Done."
