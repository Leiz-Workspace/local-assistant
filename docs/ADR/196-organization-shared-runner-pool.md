# ADR-196: Organization-level shared runner pool and faster CI

**Purpose:** Run the CI of the owner's three private repositories on one pool of self-hosted runners on the Home Server. The repositories are `local-assistant`, `web-cloner-template` and `Mirrix`, all now in the `Leiz-Workspace` organization. The change also shortens `local-assistant`'s CI without dropping any test it ran. It extends [ADR-194](194-self-hosted-github-actions-runner.md), whose hardened runner unit it keeps.

**Date:** 2026-11-13. **Status:** ACCEPTED by the owner's request. The owner asked to remove the four old repositories of `Leiz-Workspace`, move the three current repositories into it, run a shared runner, and make CI faster but still effective. The scripts, units and workflow changes are implemented. The owner installed the pool on 2026-11-13, and the first concurrent run passed in local-assistant and web-cloner-template (see Validation).

## Context

- **The three repositories.** On 2026-11-13 `local-assistant`, `web-cloner-template` and `Mirrix` were transferred from the personal account `DungeonLeiz` into `Leiz-Workspace`, on the Free plan, with the owner as admin. All three are private.
  - GitHub redirects the old URLs.
  - The repository variables, the `staging` environment and the repository-level runner `aevra-home-1` moved with `local-assistant`.
  - The four old repositories of the organization (AI, Machine-Learning, Software-Fundamentals, Sony-PMCA-EcoSys) are to be deleted at the owner's request. That needs the `delete_repo` scope on the owner's `gh` login, which it did not have when this was written.
- **Runner scope.** A personal account can only register runners per repository. An organization can register them once for all its repositories, in runner groups. On the Free plan only the Default group exists, and by default it serves only private repositories.
- **The other two repositories.** GitHub-hosted jobs in `web-cloner-template` and `Mirrix` were blocked by the same billing state. Their workflows:
  - Node CI (lint, typecheck, test, build);
  - a token badge job in `web-cloner-template` that force-pushes a `badges` branch;
  - Mirrix's release workflow: Linux and Windows installers, and a release job with `contents: write`;
  - Mirrix also checks out `web-cloner-template` with the long-lived deploy key `TEMPLATE_DEPLOY_KEY`.
- **CI time, measured with the ADR-194 runner** (research of 2026-11-13; numbers from the job API and the JUnit files):
  - a run took about 11 minutes, almost all of it serial pytest: 526 s for 7,422 passed, 368 skipped and 30 deselected tests;
  - one runner executed the jobs one after another;
  - the quarantine job ran 0 tests in about 47 s, because its list is empty;
  - the `IPAddressDeny` probe took 16 s per Python job;
  - 6 of the 10 latest runs changed only documentation and still ran everything;
  - per-test speed equalled the earlier GitHub-hosted runs.

## Decision

1. **One pool of three organization-level runners** (owner's choice: 3 instances), installed by `github-runner/install.sh` in the `self-software-distribution-platform` repository (moved on 2026-11-13 from `ai/scripts/ci-runner/` to the `Server` repository's `infras/ci-runner/`, because the runners serve the whole server, and the same day to its current place next to the Forgejo runner):
   - **Registration.** `aevra-home-1`, `-2` and `-3` are registered in the Default runner group with the label `aevra-home`, so `CI_RUNS_ON=["self-hosted","aevra-home"]` reaches any idle instance.
   - **Units.** Each instance runs as the template unit `aevra-gh-runner@<n>.service` with every ADR-194 setting. Each has its own runner tree `runners/<n>`, its own `TMPDIR` (`tmp/<n>`) and its own private `/tmp` and `/dev/shm`.
   - **Shared limits.** All instances run in `system-ghrunners.slice`, a child of `system.slice` with `CPUWeight=20`, so under contention the pool yields to CORE and the data services: `CPUQuota=1200%`, `MemoryMax=20G`, `MemorySwapMax=4G`, `TasksMax=8192`. Each instance keeps `CPUQuota=800%` and `MemoryMax=16G`.
   - **Registration token.** It comes from the API when the `gh` login has `admin:org`. Otherwise the owner pastes it from the organization's "New runner" page; the input is hidden.
   - **Status check.** Without `admin:org`, runner status is read from the journal (`Listening for Jobs`).
   - **Busy check.** Whether an instance runs a job is read locally: a `Runner.Worker` process in its cgroup.
   - **Public guard.** The install refuses an organization that holds a non-private repository. With `admin:org` it also refuses a Default group that allows public repositories.
   - **Migration.** The ADR-194 v1 runner (`aevra-gh-runner.service`, repository-level `aevra-home-1`) is stopped, deleted and deregistered through the repository API. Until the pool's template unit exists, any `runners/` tree is deleted too, because v1 jobs could write there.
   - **Order of work.** The download and the registration token come before any system change, so a failure leaves v1 and CI as they were.
   - **No runner code outside the sandbox.** Before building any runner tree, every instance is stopped and every `gh-runner` process killed, because `config.sh` and the runner come from a tree that jobs could rewrite, and they run outside the units' sandbox.
   - **Routing.** `--use` sets `CI_RUNS_ON` in each of the three repositories; that needs only the `repo` scope.
2. **Jobs that hold write tokens run on the pool** (owner's choice, after the risk was explained). These are `local-assistant`'s release, `web-cloner-template`'s token badge, and Mirrix's release and its `TEMPLATE_DEPLOY_KEY` checkouts. GitHub-hosted runners are blocked, and the three repositories have one owner. The residual risk is listed under Consequences.
3. **Mirrix's packaging on the pool.** The runners use `UMask=0027`, so the Linux build normalizes file modes (`umask 0022`, `chmod go+rX,go-w`) and a gate fails any `.deb` entry that other users cannot read. Concurrent instances use separate X displays for the smoke test. The release job collects installers in `$RUNNER_TEMP`, so leftovers from an earlier release on a persistent runner cannot be published. The token badge job uses a per-job venv with pinned packages and a fresh badge repository.
4. **Mirrix's Windows installer** builds on GitHub-hosted `windows-latest`, and only in runs that publish: pushes to `staging` and `production` (owner's choice). Pull requests build and smoke-test Linux only, on the pool. Its `plan` job reads the version with `jq` instead of `node`, which the runners do not have before `setup-node`. Its Linux smoke test needs `xvfb-run` on the host; there is no sudo on the runners.
5. **Both other repositories** use `runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '"ubuntu-latest"') }}` and pin every remote action to a commit SHA: checkout v7.0.1, setup-node v7.1.0, setup-python v7.1.0, upload-artifact v7.0.2 and download-artifact v8.0.2, all `node24`. Their documentation and the deploy-key checkouts point to `Leiz-Workspace/...`.
6. **Faster CI in `local-assistant`, with the same test scope:**
   - **Parallel pytest.** pytest runs with `pytest-xdist` (new dev dependency, 3.8): `-n 6 --dist loadfile` on the pool and `-n 2` on GitHub-hosted runners. Whole files stay on one worker, so module fixtures are built once. A revision without `pytest-xdist` still runs serially.
   - **Fixed hash seed.** `PYTHONHASHSEED=0`, because some parametrized ids come from set iteration and every xdist worker must collect the same ids.
   - **Short temporary root.** `--basetemp="$TMPDIR/pt"` keeps AF_UNIX socket paths in `tmp_path` under 108 bytes; xdist adds a `popen-gw<n>` level.
   - **Exclusions plugin.** `.github/ci/hosted_exclusions.py` merges the workers' scope reports on the controller, so the "files ignored / excluded / outside quarantine" line stays exact.
   - **Leak check in `tests/test_check_runner.py`.** Its leak check counted every sandboxed pin process on the host, so another worker or a concurrent CI job made it fail. It now counts only processes that descend from the test process, or that became orphans during the test.
   - **Documentation-only pull requests.** A pull request skips the test jobs when every changed path is under `dev_log/`, or under `docs/` outside `docs/evidence/` and `docs/proposals/`, and no non-Markdown file of `tests`, `benchmarks`, `src`, `apps`, `scripts`, `configs` or `.github` names that path. Renames count as their old and new paths (`--no-renames`). Every push, promotion, tag and manual run runs everything, so a develop run after a cancelled one never passes without testing.
   - **Quarantine job.** It runs only while `.github/ci/hosted-runner-quarantine.txt` has an entry.
   - **Artifacts.** JUnit artifacts are uploaded only for a failed or cancelled run, and kept 7 days instead of 14. The source bundle is kept 14 days instead of 30.
   - **Address probe.** The `IPAddressDeny` probe connects to all addresses at once instead of one after another.

## Alternatives

- **One runner instance per repository, each with its own user** (recommended in the research when stronger separation matters). On the Free plan any repository can target any label of the Default group, so separate users would separate the files of different instances, not the repositories. It would also need per-instance sshd drop-ins and instance-aware scripts. Not chosen: the owner wanted one shared pool.
- **Ephemeral just-in-time runners.** These give a clean state per job but need a stored credential with administration rights and a launcher service. They remain the long-term option of ADR-194.
- **Fixing GitHub billing.** This is the owner's separate decision. It would also restore Mirrix's Windows builds on pull requests.
- **Sharding test-python across the runners** instead of xdist. Each shard pays its own setup, and the shards occupy all three runners, so other repositories' jobs would wait. xdist inside one job reached about 2.3 minutes locally.

## Consequences

- **Every job shares one user.** Jobs of all three repositories run as `gh-runner`, on persistent runners that can run at the same time. Job code of any repository can:
  - read the environment and files of the other jobs, including the write tokens and `TEMPLATE_DEPLOY_KEY`;
  - tamper with the runner trees.

  Accepted by the owner for three private, single-owner repositories. After a suspected compromise, run `uninstall.sh --purge` and rotate `TEMPLATE_DEPLOY_KEY` (README, Recovery).
- **Concurrent jobs see each other's processes** in `/proc` and their loopback listeners. Tests must not assume that they are alone on the host.
- **CI load.** Up to three jobs can load the host at once, within 12 CPUs and 20G. Before D87 or a native benchmark, stop all instances: `sudo systemctl stop 'aevra-gh-runner@*'`.
- **Faster runs, measured locally on 2026-11-13** (owner user, CI scope, project venv; see Validation):
  - serial pytest took 526 s on the runner;
  - with xdist and 4, 6 and 8 workers, pytest took 185 s, 136–144 s and 115 s.

  A documentation-only change finishes after `prepare`.
- **Unchanged:** the test scope is the same as before. D87 is still the full regression with live services.

## Rollback

- **Back to GitHub-hosted runners.** Delete `CI_RUNS_ON` in a repository: `gh variable delete CI_RUNS_ON --repo Leiz-Workspace/<repo>`.
- **Remove the pool.** Run `github-runner/uninstall.sh` in the `self-software-distribution-platform` repository (or `--purge`). It stops every instance, deregisters the runners (organization runners need `admin:org`; without it the script exits with status 3 and names the page where you remove them), and deletes the trees, the template unit and the slice.
- **Revert the CI speed changes.** Revert the `ci.yml` and plugin commits; serial pytest still works, because the `-n` flag is only added when xdist is importable.

## Validation

- **Done, without sudo (2026-11-13):**
  - `bash -n` on both scripts.
  - `systemd-analyze verify` on the rendered slice and template unit (instance 1).
  - YAML parse of every changed workflow.
  - The `prepare` step was simulated on real commits:
    - three documentation-only changes skip the tests: the ADR plus roadmap plus dev log, the ADR-194 note plus dev log, and a documentation-only pull request;
    - a `docs/evidence` receipt, a script plus workflow change, a code merge, and a documentation-only push to `staging` all run them.
  - The parallel address probe still reports every reachable address outside the unit, in about 0.1 s.
  - The changed test file passes serially (22 passed) and together with two other sandbox files under `-n 6` (86 passed).
  - The full CI scope under `-n 6 --dist loadfile`, run twice on the owner's account with the project venv: 7,422 passed, 368 skipped, 0 failed, in 141.46 s and 141.05 s. The plugin line read `19 files ignored, 30 excluded`, as in the serial run.
  - An adversarial review (three reviewers, one verifier each) confirmed 17 findings, all fixed:
    - two blocking: Mirrix `.deb` modes under `UMask=0027`, and the missing `xvfb-run` check before `--use`;
    - the documentation-only rule (renames, cancelled develop runs);
    - the install order and the stop-everything step before building runner trees;
    - the journal check on reruns, and the slice placement;
    - stale runner workspaces in the release and badge jobs;
    - documentation fixes.
- **The first xdist measurement failed for a reason in the measurement itself.** It used `uv run --with pytest-xdist`, whose interpreter lives in uv's cache. The project sandboxes do not bind that directory, so 132 sandbox tests failed. The same 10 tests fail with that interpreter and no xdist, and pass with the project venv.
- **With xdist in the project venv,** two causes remained: the AF_UNIX path length, and the leak check counting other workers' sandboxes. Both are fixed above.
- **Installed and run on 2026-11-13.**
  - **Install.** The owner installed `xvfb`, then ran `sudo -v && scripts/ci-runner/install.sh --use` with a pasted registration token (no `admin:org` scope). The script reported `aevra-home-1`, `-2` and `-3` online and set `CI_RUNS_ON` in all three repositories.
  - **Checked afterwards, without sudo:**
    - the v1 unit file is gone and `Leiz-Workspace/local-assistant` has 0 repository-level runners;
    - the three instances run in `/system.slice/system-ghrunners.slice` (`CPUWeight` 20, `CPUQuota` 1200%, `MemoryMax` 20G);
    - each instance has `NoNewPrivs: 1`, the three mount masks and its own `TMPDIR` (`/var/lib/gh-runner/tmp/<n>`).
  - **First concurrent run.** All three repositories started CI at the same time (07:08 UTC):
    - **local-assistant** (`workflow_dispatch` on `develop`, run 43383562394) passed in about 4.5 minutes, with its jobs spread over all three runners: test-python on `aevra-home-2` (7,422 passed, 368 skipped, 0 failed, pytest 194.72 s while the other repositories' jobs ran), test-js on `aevra-home-1`, lint on `aevra-home-3`. The preflight blocked the 8 host addresses.
    - **web-cloner-template** PR #19 passed on `aevra-home-3` in 58 s, and was merged.
    - **Mirrix** PR #3: Plan version passed on `aevra-home-2`. Lint/typecheck/test/build and Package (linux), both on `aevra-home-1`, stopped at "Checkout website template" ("Could not read from remote repository"), because the organization has deploy keys disabled (`deploy_keys_enabled_for_repositories=false`). `TEMPLATE_DEPLOY_KEY` stopped working when the repositories moved into the organization.
  - **Found on the way.** Before `CI_RUNS_ON` was set in the two other repositories, their pull requests ran on GitHub-hosted runners and were not blocked. The billing block applied to the personal account; repositories in `Leiz-Workspace` use the organization's own Free allowance.
- **Completed on 2026-11-13 (14:20 +07).** The owner enabled deploy keys for the organization (`deploy_keys_enabled_for_repositories=true`; the `mirrix CI` read-only key shows `enabled=true`). The owner also deleted the four old repositories; the organization now holds only `local-assistant`, `web-cloner-template` and `Mirrix`.
  - **Mirrix PR #3, re-run on the pool.** Lint/typecheck/test/build passed on `aevra-home-2`. Plan version passed on `aevra-home-1`. Package (linux) passed on `aevra-home-1` in about 2 minutes:
    - it built the AppImage and the .deb;
    - the .deb mode gate passed;
    - the Electron smoke test passed under `xvfb-run` with the instance's own display.

    No Windows job ran on the pull request, as designed. PR #3 was merged.
  - **Develop push runs after the merges** passed on the pool: web-cloner-template on `aevra-home-2`, Mirrix on `aevra-home-3`.
  - **Submodule bump.** web-cloner-template PR #20 bumps its `desktop` submodule to Mirrix develop; it passed on `aevra-home-3` and was merged.
  - **Status.** All three repositories now run CI on the shared pool and are green. Mirrix's Windows installer for releases still builds on GitHub-hosted `windows-latest`, within the organization's own allowance.
