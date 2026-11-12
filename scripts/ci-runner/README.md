# Self-hosted CI runner (Home Server)

This directory sets up a GitHub Actions self-hosted runner, so the repository's CI (`.github/workflows/ci.yml`) can run on the Home Server and still report as normal GitHub checks. The design is recorded in [ADR-194](../../docs/ADR/194-self-hosted-github-actions-runner.md).

Self-hosted runner minutes are not billed and do not draw from the plan's included compute. GitHub-hosted jobs in this private repository were blocked by the account's billing state, so CI could not run at all.

## How CI chooses a runner

Every job uses `runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '"ubuntu-24.04"') }}`.

| `CI_RUNS_ON` (repository variable) | Jobs run on |
|---|---|
| unset | GitHub-hosted `ubuntu-24.04` (the previous behaviour) |
| `["self-hosted","aevra-home"]` | this runner |

Switching needs no code change. Use the self-hosted runner:

```bash
gh variable set CI_RUNS_ON --repo DungeonLeiz/local-assistant --body '["self-hosted","aevra-home"]'
```

Go back to GitHub-hosted runners:

```bash
gh variable delete CI_RUNS_ON --repo DungeonLeiz/local-assistant
```

The composite action `.github/actions/hosted-python` handles both runner types:

- **GitHub-hosted:** it installs native tools and aligns the layout with `sudo`.
- **Self-hosted:** it only runs a preflight, without `sudo`. The host provides `bwrap` with unprivileged user namespaces, ffmpeg, tesseract, poppler, LibreOffice, and `/usr/bin/python3.12` without the `config-3.12` directory. The preflight also checks what the runner unit must allow and block:
  - the real project sandbox shape, `bwrap --unshare-all --die-with-parent --ro-bind / / --proc /proc --dev /dev --tmpfs /tmp true`, with bwrap's error in the log;
  - an `openat2()` call, which the workspace layer needs;
  - that the GPU device nodes are not accessible;
  - that tailscaled's LocalAPI socket `/run/tailscale/tailscaled.sock` cannot be connected to;
  - a multiprocessing lock, which needs a writable `/dev/shm`.

  The GPU and tailscaled checks only report a sandbox that lost its settings. They control nothing, because code on a branch can change the preflight.
- **Node.js** comes from `actions/setup-node` (`NODE_VERSION`) in the test jobs on both runner types, before the composite action. The runner user sees only `/usr/local/bin:/usr/bin:/bin` and no `/home`, so the owner's nvm node is out of reach and the host needs no system node. D87 runs as the owner with nvm on `PATH`, so it never showed this gap.

Every remote action in `ci.yml` and the composite action is pinned to a full commit SHA, with the version in a comment, because on this runner the action code runs on the Home Server.

## Install (once, as the owner)

Before `--use`, take secrets off host processes' command lines, because CI jobs can read every host process's command line (see Residual risks). The MongoDB healthcheck in `infras/mongo-server/mongo-compose.yaml` no longer has credentials (commit `71aa2c0` in the `Server` repository, applied on 2026-11-13). Keep it that way, and do not run a MongoDB rotation with `infras/scripts/manage_server_secrets.py` while the runner is installed. Also enable authorization on the host `mongod` on 127.0.0.1:27017 before `--use`, as you chose on 2026-11-13 (see Residual risks, Loopback services, for the steps). It is a host change outside this kit, which `install.sh` does not make. Deciding on SSH password logins (Residual risks, sshd) before `--use` is recommended too. The script denies SSH logins as `gh-runner` itself (step 6).

```bash
cd /home/korosaki-ryukai/Workspace/Server/ai
scripts/ci-runner/install.sh --use
```

The script:

1. Runs as your user, refuses to run as root, and asks for your sudo password only for the system steps.
2. Refuses a repository that is not private, before any system step. The repository is `RUNNER_REPO` (default `DungeonLeiz/local-assistant`). This check runs only at install time: the repository must stay private afterwards, and before making it public you must run `uninstall.sh`.
3. Checks the host tools with the runner's `PATH`, and that `tailscaled`, when installed, is running, so the unit can hide its socket (see Isolation).
4. Creates the system user `gh-runner` with home `/var/lib/gh-runner`, no login shell and no privileged group. If the user exists, it checks that it is that non-root system account and owns that home. The user name, home and label are fixed in the scripts.
5. Masks the user's systemd user manager (`user@<uid>.service`), disables lingering and removes any crontab, so job code cannot get a service manager outside the unit.
6. Denies SSH logins as `gh-runner`: it writes `/etc/ssh/sshd_config.d/90-aevra-gh-runner.conf` with `DenyUsers gh-runner` and checks it with `sshd -t`. It first runs `sshd -t` on the current configuration and, if that already fails, stops without touching the drop-in. A drop-in that already holds exactly that line is left as it is. If sshd rejects the new file, the script puts back what was there before and stops: a drop-in this run created is removed, and an earlier one is restored, so an existing denial is never dropped. It then checks with `sshd -T` that sshd reads the drop-in, and stops if it does not (no `Include` of `sshd_config.d`). It reloads `ssh.service` when it is active. The step runs on every run, and is skipped only when `sshd` is not installed or `/etc/ssh/sshd_config.d` does not exist. See Isolation, SSH.
7. On a first install, downloads the pinned runner (`RUNNER_VERSION`, default 2.338.2), verifies its SHA-256, unpacks it as `gh-runner` and registers it as `aevra-home-1` with the label `aevra-home`. Root creates only `/var/lib/gh-runner` itself. `runner/` and `tmp/` below it are created as `gh-runner`, so a symlink that job code plants there cannot redirect a root write. The short-lived registration token comes from your `gh` login and is passed through stdin, never printed. An existing registration is kept as it is (see Recovery).
8. Installs and starts the `aevra-gh-runner` systemd service. When the unit file changed, it restarts the service so the new settings apply, and refuses while the runner is running a job.
9. Waits until the runner is online and checks that it runs with `no_new_privs`.
10. With `--use`, checks that the registered runner has the labels `self-hosted` and `aevra-home`, then sets `CI_RUNS_ON` to `["self-hosted","aevra-home"]`.

Without `--use`, the runner is online but CI keeps targeting GitHub-hosted runners until you set the variable.

## Isolation

What `aevra-gh-runner.service` enforces, plus the sshd denial that `install.sh` adds on the host:

- **User.** The service runs as `gh-runner`, which has no sudo rights and is in no privileged group.
- **Files.** `ProtectHome=yes` hides `/home` entirely, including your files, the Vault bootstrap file, models, `.env` and `data/`. `ProtectSystem=strict` makes the file system read-only except `/var/lib/gh-runner` and the kernel API trees `/dev`, `/proc` and `/sys`. `PrivateTmp` gives the service its own `/tmp` and `/var/tmp`.
- **Shared memory and IPC.** The host's `/dev/shm` and `/dev/mqueue` are world-writable and stay writable under `ProtectSystem=strict`, so the unit replaces them. `TemporaryFileSystem=/dev/shm:mode=1777,nosuid,nodev,size=2G` gives the service its own size-capped `/dev/shm`, and `PrivateIPC=yes` its own SysV IPC namespace and `/dev/mqueue`. `RemoveIPC=yes` removes every SysV and POSIX IPC object that `gh-runner` still owns on the host when the service stops. None of these mounts anything under `/proc`. They are not yet validated on the installed unit; the preflight's `bwrap` and multiprocessing checks catch a breakage on the first run.
- **Privileges.** `NoNewPrivileges=yes`: setuid and setgid binaries (`crontab`, `su`, `pkexec`, `fusermount3`, `newuidmap`) and file capabilities cannot raise privileges for job code. `bwrap` still gets user namespaces, because AppArmor allows the exec from the unconfined runner into the `bwrap` profile under `no_new_privs`. systemd 259 does not imply `no_new_privs` for this unit, so the unit sets it explicitly. `ProtectKernelModules`, `ProtectControlGroups`, `ProtectClock`, `LockPersonality` and `UMask=0027` are also set.
- **System D-Bus.** `InaccessiblePaths=-/run/dbus/system_bus_socket` hides the system bus from processes inside the service, so job code there cannot ask logind to enable lingering or call other bus services directly. sshd denies SSH logins as `gh-runner` (see SSH below), so job code cannot reach the bus through an SSH session as `gh-runner` either (a password login as another account is a separate path; Residual risks, sshd). This is not a complete block: a restart of `dbus.socket` re-creates the socket file, which detaches the mask until the runner service restarts.
- **Tailscale LocalAPI.** `InaccessiblePaths=-/run/tailscale` hides tailscaled's LocalAPI socket (`/run/tailscale/tailscaled.sock`, mode 0666; `/var/run` is a symlink to `/run`). Through that socket, job code could make root `tailscaled`, which is outside the unit's `IPAddressDeny`, open connections to tailnet peers (`POST /localapi/v0/dial`, `tailscale nc`) and read the full peer list (`/localapi/v0/status`). `tailscaled.service` has `RuntimeDirectory=tailscale`, so every tailscaled restart deletes and re-creates `/run/tailscale`, and the kernel then drops the mask in the runner's namespace. The unit therefore has `After=tailscaled.service` and `PartOf=tailscaled.service`:
  - `systemctl restart tailscaled`, which package upgrades also use, restarts the runner too. The runner stops first and starts after tailscaled, so it never sees the new socket. A crash restart of tailscaled (`Restart=on-failure`, `RestartMode=normal` on this host) is expected to propagate the same way; this is not yet checked on the installed unit.
  - The tailscaled restart waits until the runner has stopped, up to `TimeoutStopSec=5min`, and the CI job in progress ends. After a tailscaled crash, the tailnet stays down for that time.
  - `systemctl stop tailscaled` stops the runner, and the runner stays stopped when tailscaled starts again. Start tailscaled first, then the runner. If the runner starts while `/run/tailscale` does not exist, the `-` prefix skips the mask without a message, and a later tailscaled start exposes the socket. `After=` keeps that order at boot, and `install.sh` refuses to run while an installed tailscaled is stopped.
  - None of this is validated on the installed unit yet. The preflight reports a reachable socket. An SSH session as `gh-runner` cannot forward to the socket, because sshd denies those logins (see SSH below).
- **Devices.** `DevicePolicy=closed` allows only the standard pseudo devices that `bwrap --dev` binds, plus read access to `/dev/rtc*` (`DeviceAllow=char-rtc r`, implied by `ProtectClock=yes`; the nodes are `root:clock` 0660 and `gh-runner` is not in `clock`, so it still cannot open them). The GPU nodes (`/dev/nvidia*`, mode 0666) and `/dev/kmsg` are refused.
- **Network.** `IPAddressDeny=` blocks `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10`, `169.254.0.0/16`, `224.0.0.0/4`, `fc00::/7`, `fe80::/10`, `ff00::/8` and `255.255.255.255/32`. Processes in the service cannot open direct connections to the LAN, Docker or k3s networks, tailnet addresses, or the host's own addresses on them. Limited broadcast is blocked too, so jobs cannot send broadcasts onto the LAN, Docker or k3s bridges. Public internet (GitHub, PyPI) and loopback stay allowed, for the DNS stub on 127.0.0.53 and the tests' 127.0.0.1 listeners. `IPAddressDeny=` filters only the service's own sockets. A host daemon that connects on a job's behalf is outside it: tailscaled (previous point) and sshd. Through tailscaled, jobs can still reach tailnet peers until the mask is validated. sshd forwards nothing for `gh-runner` logins, because it denies them (next point). A password login as another account through sshd on loopback is a separate path (Residual risks, sshd).
- **SSH.** Outside the unit, `install.sh` adds `/etc/ssh/sshd_config.d/90-aevra-gh-runner.conf` with `DenyUsers gh-runner` (Install, step 6), so sshd refuses every SSH login as `gh-runner` before any session or forwarding starts. It applies to port 22 (`ssh.socket` and `ssh.service`) and to `/run/ssh-unix-local/socket` (`sshd-unix-local.socket` from systemd-ssh-generator, mode 0666), which reads the same configuration. Job code can still write `/var/lib/gh-runner/.ssh/authorized_keys`, but a key planted there gives no login. Without the denial, such a key would be a standing login that works with no job running, survives a stop of the service, and makes sshd forward TCP and Unix sockets from outside `IPAddressDeny` and the mount sandbox: to loopback-only services, the LAN, the tailnet, the Docker and k3s networks, the system D-Bus and tailscaled's LocalAPI socket. The denial is host configuration, not part of the unit: it holds while the drop-in stays and sshd reads it, which `install.sh` checks with `sshd -T` on every run. `uninstall.sh` still deletes `~/.ssh` as defense in depth, and only `uninstall.sh --purge`, which also deletes the account, removes the drop-in. Check it with `sudo sshd -T -C user=gh-runner,host=localhost,addr=127.0.0.1 | grep -i denyusers`, which prints `denyusers gh-runner`. The denial covers only logins as `gh-runner`. The unit also hides `/run/ssh-unix-local` from processes inside it (`InaccessiblePaths=-/run/ssh-unix-local`), because each connection to that socket is a fresh `sshd -i` that sshd's `PerSourcePenalties` do not throttle, so job code could guess other accounts' passwords there. Like the D-Bus mask, it holds while the directory persists: re-creating `/run/ssh-unix-local` detaches it until the runner restarts. It is not yet validated on the installed unit. sshd on 127.0.0.1:22 stays reachable (Residual risks, sshd).
- **Processes.** `KillMode=mixed`: stopping the service, including the D87 pause, ends the runner gracefully and then kills every process left in its cgroup. `RemoveIPC=yes` also removes the user's IPC objects at that point.
- **Resources.** Limits leave headroom for CORE and the services:
  - `CPUQuota=800%`, about 8 of 16 cores;
  - `MemoryMax=16G` and `MemorySwapMax=2G`: a job past that is OOM-killed instead of using up the host's 8 GB swap;
  - `Nice=10`;
  - low I/O priority;
  - disk: not limited; see Residual risks.
- **Temporary files.** Pytest temporary trees go to `/var/lib/gh-runner/tmp` on disk, not the 16 GB `/tmp` tmpfs.

What the unit deliberately does not set, because each one breaks the project sandboxes:

- **Any directive that mounts over a path under `/proc`:** `ProtectKernelTunables`, `ProtectKernelLogs`, `ProtectHostname`, `ProtectProc`, `ProcSubset`, and `BindPaths`, `ReadOnlyPaths`, `InaccessiblePaths` or `TemporaryFileSystem` entries under `/proc`. `bwrap`'s user namespace locks such a mount, and the kernel then refuses the fresh `/proc` that every sandbox mounts with `--proc /proc`. The kernel log and sysctls stay closed to `gh-runner` anyway: `kernel.dmesg_restrict=1`, `/proc/kmsg` is mode 0400, and the user has no capabilities. Other processes' command lines do not stay closed; see Residual risks.
- **`RestrictSUIDSGID`:** its seccomp filter makes `openat2()` fail with `ENOSYS`, and the workspace layer requires `openat2`. `NoNewPrivileges` already stops privilege gain through setuid binaries.
- **`PrivateNetwork` or `IPAddressDeny=localhost`:** they break DNS through the 127.0.0.53 stub and the tests that use 127.0.0.1 listeners.

### Residual risks

These are accepted for a private, single-owner repository. Each one is the owner's decision to close.

- **Loopback services.** Jobs can connect to every service that listens on loopback or on all addresses: Vault (8200), Qdrant (6333/6334), PostgreSQL (5432/5433), Redis (6379), MongoDB (27017, the host `mongod`; 27018, Docker, `--auth`), sshd (22), k3s (6443) and the kubelet (10250), CORE (8080) when it runs, and the host's other listeners. Their protection rests on each service's own authentication. Jobs find no credentials for them in files, because `/home` is hidden, but they can read credentials that a process passes on its command line (Process list and command lines below). This kit adds no firewall or polkit rules. Two services have no authentication at all:
  - **Redis on 127.0.0.1:6379 accepts commands without authentication,** so a job can read and change its data.
  - **MongoDB on 127.0.0.1:27017 accepts every command without authentication.** This is the host `mongod` (`/etc/mongod.conf` has no `security.authorization`; the service is enabled at boot and holds application databases), not the Docker MongoDB on 27018, which runs with `--auth`. A job can read, change or drop its databases and run admin commands. You chose on 2026-11-13 to enable authorization; it is not done yet. Steps, before `install.sh --use`: as your own user, create an admin user while the server still accepts unauthenticated commands, typing the password at the prompt so that it never appears on a command line: `mongosh "mongodb://127.0.0.1:27017/admin?directConnection=true" --eval 'db.createUser({user: "admin", pwd: passwordPrompt(), roles: [{role: "root", db: "admin"}]})'`; then add `security:` with `authorization: enabled` to `/etc/mongod.conf` and run `sudo systemctl restart mongod`. Clients of `agent_angi_recipes`, `default_database`, `nutrition_ai` and `steam_db` then need their own users and credentials, passed in a file or the environment, not as arguments. Changing `/etc/mongod.conf` or restarting `mongod` is a host change that `install.sh` does not make.
- **sshd password logins as other accounts.** `NoNewPrivileges` blocks `su`, `sudo` and `pkexec` inside the unit, but job code can still reach sshd on 127.0.0.1:22 and [::1]:22 and guess the password of another account, including yours (you are in `sudo` and `docker`). `PasswordAuthentication` is on (the default; `KbdInteractiveAuthentication` is already `no`), and the host has no lockout: no fail2ban, sshguard or `pam_faillock`. Only sshd's `PerSourcePenalties`, pam_unix's failure delay of about 2 seconds and `MaxAuthTries 6` slow the guessing, and the penalties are keyed per source address, so a job can avoid them by binding other 127/8 addresses. A correct guess gives a session outside the unit's cgroup, `IPAddressDeny` and every mount mask. The local socket `/run/ssh-unix-local/socket` (mode 0666) would be weaker still, because each connection is a fresh `sshd -i` that the penalties do not cover, so the unit hides `/run/ssh-unix-local` (Isolation, SSH). Options, your decision, recommended before `--use`:
  - `PasswordAuthentication no` host-wide, which covers loopback TCP and the Unix socket, once key login works from every client you use;
  - if you keep password logins for remote clients, both of these together: a `Match Address 127.0.0.0/8,::1` block with `PasswordAuthentication no` for loopback TCP, and masking or disabling `sshd-unix-local.socket` (or booting with `systemd.ssh_auto=no`). The `Match` block alone does not cover the Unix socket, because sshd sees that peer as `UNKNOWN` and `Match Address` never matches it; until then the unit's mask is the only cover there.

  This kit does not change sshd beyond the `gh-runner` denial, or the socket units.
- **Disk.** No disk limit: `/var/lib/gh-runner` is on the root ext4 filesystem (`/dev/sda4`, mounted without quotas) together with Docker, k3s, PostgreSQL, MongoDB, Redis and Vault. A job, through a runaway test or a compromised dependency, or plain growth in `~/.cache/uv`, `runner/_work`, `runner/_diag` and `tmp/`, can fill it down to the 5% that ext4 keeps for root (about 46 GB here). The data services that do not run as root (PostgreSQL, MongoDB, Redis, Vault) then fail with `ENOSPC` at the same point as `gh-runner`; root daemons such as dockerd, containerd and k3s keep the reserve, and k3s's kubelet starts evicting pods earlier, once free space drops below its threshold. Files left under `/var/lib/gh-runner` stay after the job until someone removes them. Options, your decision:
  - a separate partition, or a preallocated, loop-mounted ext4 image of fixed size (for example 100G), mounted at `/var/lib/gh-runner`, with `RequiresMountsFor=/var/lib/gh-runner` added to the unit so the runner never starts on the root filesystem when the mount is missing;
  - `StateDirectory=gh-runner` with `StateDirectoryQuota=` (systemd 258 and later; this host has 259). It needs project quotas on the root ext4 (`tune2fs -O quota -Q prjquota`, which runs only with the filesystem unmounted), and it changes how `install.sh` handles directory ownership;
  - a free-space check in the self-hosted preflight, which only catches accidents, because job code can change the preflight;
  - periodic cleanup of `~/.cache/uv`, `runner/_work` and `tmp/`.
- **Process list and command lines.** `ProtectProc` and `ProcSubset` are unset (see above), so jobs see every host process and can read its full command line in `/proc/<pid>/cmdline`: your shells, Claude sessions, cron, services, and Docker/k3s containers with their healthchecks and `exec` commands. Any secret passed as a command-line argument is readable by CI jobs while it runs. Other users' `/proc/<pid>/environ` is mode 0400 and stays unreadable.
  - Instances: the MongoDB healthcheck in `infras/mongo-server/mongo-compose.yaml` ran `mongosh --password <root password>` every 10 seconds. It needs no credentials, because `db.adminCommand({ping: 1})` works without authentication, so it was fixed (commit `71aa2c0` in the `Server` repository) and applied on 2026-11-13. Still current: `infras/scripts/manage_server_secrets.py` passes the password as an argument during a MongoDB rotation, and the commands that `mongo-server/scripts/create-database-template.py` prints do too.
  - While the runner is installed, never pass a secret as an argument (for example `curl -H 'X-Vault-Token: ...'`, `redis-cli -a`, `docker exec -e K=V`, or a URI with a password). Use stdin, an environment variable or a file instead.
- **Tailnet through tailscaled.** Through tailscaled's LocalAPI socket, job code can make root `tailscaled` open connections to other tailnet peers, outside `IPAddressDeny`, and read the full peer list. The unit hides `/run/tailscale` and restarts with tailscaled (see Isolation), but that is not yet validated on the installed unit. Until it is, treat tailnet peers as reachable from CI jobs. An SSH session as `gh-runner` cannot forward to the socket, because sshd denies those logins (Isolation, SSH). Host-side options, your decision: a tailscaled drop-in with `RuntimeDirectoryPreserve=yes`, which keeps `/run/tailscale` across tailscaled restarts so the mask holds without restarting the runner, or restricting access to the LocalAPI socket on the host.
- **Abstract Unix sockets** are not covered by the mount sandbox.
- **Jobs are not isolated from each other.** The runner is persistent, and every job runs as the same user with a writable runner directory. Job code can:
  - leave modified files that affect later jobs: `runner/bin`, `.env`, `.path`, `~/.gitconfig`, `~/.cache/uv`;
  - read later steps' environment, including tokens such as the `contents: write` token of the tag-only `release` job;
  - read the runner credentials (`.credentials`, `.credentials_rsaparams`) and impersonate the runner.

  Processes that a job starts with an empty environment escape the runner's own cleanup between jobs. `KillMode=mixed` ends them only when the service stops.
- **Third-party action code** runs on the host. The remote actions are pinned to commit SHAs for that reason.

The repository is private, so only accounts with write access can trigger workflows. Do not attach this runner to a public repository: a fork pull request could then run arbitrary code on the Home Server. `install.sh` refuses a repository that is not private, but only at install time; run `uninstall.sh` before making the repository public.

## Native measurements and D87

The runner shares the host with CORE and the services, and CI jobs add CPU load. Before a native benchmark or D87, pause it and check that no job is running:

```bash
sudo systemctl stop aevra-gh-runner
sudo systemctl start aevra-gh-runner   # afterwards
```

Stopping the service also kills any process a job left behind in the service and removes the IPC objects it left (`RemoveIPC=yes`). An SSH key that a job planted gives no SSH session that could outlive the stop, because sshd denies logins as `gh-runner` (Isolation, SSH). A queued job waits on GitHub (up to 24 hours) while the runner is stopped. The idle-host check used before measurements also catches a running CI job through its CPU load.

## Operate

| Task | Command |
|---|---|
| Status and logs | `sudo systemctl status aevra-gh-runner`, `sudo journalctl -u aevra-gh-runner -n 100` |
| Runner list on GitHub | `gh api repos/DungeonLeiz/local-assistant/actions/runners --jq '.runners[] \| {name,status,busy,labels:[.labels[].name]}'` |
| Check the sandbox | `systemctl show -p NoNewPrivileges,ProtectSystem,ProtectHome,PrivateTmp,PrivateIPC,RemoveIPC,TemporaryFileSystem,InaccessiblePaths,DevicePolicy,DeviceAllow,IPAddressDeny,MemoryMax,MemorySwapMax,KillMode,PartOf aevra-gh-runner` (`DeviceAllow` prints `char-rtc r`, from `ProtectClock`); `grep NoNewPrivs /proc/$(systemctl show -p MainPID --value aevra-gh-runner)/status` prints 1; `sudo nsenter -t "$(systemctl show -p MainPID --value aevra-gh-runner)" -m ls -A /home /run/tailscale /run/ssh-unix-local` lists nothing in any of the three directories |
| Apply a changed unit | rerun `scripts/ci-runner/install.sh` while the runner is idle; it restarts the service only when the unit changed |
| Updates | the runner updates itself in `/var/lib/gh-runner/runner`, and the unit starts the current `bin/runsvc.sh`. Re-pinning `RUNNER_VERSION`/`RUNNER_SHA256` matters only for a fresh install. |
| Uninstall | `scripts/ci-runner/uninstall.sh` deletes `CI_RUNS_ON` first, so CI returns to GitHub-hosted runners. If it cannot delete the variable, it stops with an error and leaves the runner running. It then stops the service, kills every `gh-runner` process, removes lingering and any crontab, deletes `~gh-runner/.ssh` as defense in depth (sshd already denies logins as `gh-runner`), deregisters the runner through the GitHub API from your `gh` login, and deletes `/var/lib/gh-runner/runner`. It never executes anything from the runner tree, because job code can rewrite it. Without `--purge`, the account, the rest of its home and the sshd denial stay; add `--purge` to also delete the user and its home and remove the sshd drop-in (reloading `ssh.service` when it is active). |

## Recovery after a suspected compromise

A rerun of `install.sh` keeps an existing runner tree as it is, so it does not repair tampered files.

1. Run `scripts/ci-runner/uninstall.sh --purge`. It deletes `CI_RUNS_ON`, kills every `gh-runner` process, deregisters the runner through the GitHub API from your shell, and deletes the user and its home. No code from the possibly tampered runner tree runs outside the unit: the tree is deleted, never executed.
2. Check the runner list on GitHub and remove any runner you do not expect.
3. Run `scripts/ci-runner/install.sh --use`. It reinstalls from the pinned, checksum-verified tarball with a fresh registration.
