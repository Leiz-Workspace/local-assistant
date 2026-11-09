# ADR 179 — Retire the sandbox PID namespace before control returns

**Purpose:** Make the document and media sandbox callers regain control only after every process in the sandbox PID namespace has exited, on a timeout, on an interruption and on a normal exit.

**Status:** ACCEPTED, 2026-11-09. After PR #46 the assistant asked "Sửa code production để chờ sandbox dọn xong khi timeout?" and the owner answered "Làm luôn". Model, default, activation and release state are out of scope.

## Context

- The following workers run under bubblewrap through `src/infrastructure/file_verifier.py::sandbox_command` (`--unshare-all --die-with-parent --new-session`, payload copied from stdin with `--ro-bind-data 0 /payload`):
  - file verification;
  - native PDF extraction;
  - page OCR and rendering, also used by the native image normalizer;
  - DOCX and XLSX;
  - audio and video;
  - report export.
- The process tree has four levels:
  1. the outer `bwrap` launcher, which is the caller's child;
  2. the `bwrap` init, which is PID 1 of a new PID namespace and runs in its own session;
  3. the worker;
  4. possible descendants.
- Measured on the Home Server:
  - The init holds dups of stdout and stderr, which are the caller's output file.
  - The worker holds the `/payload` copy of the source, plus stdout and stderr.
  - Until its bootstrap replaces fd 0, the sandboxed child holds the borrowed source descriptor itself.
- Seven callers used `subprocess.run(..., timeout=...)`. `report_export.supervise` used `Popen` with `killpg` and `wait`. Both returned once the launcher was reaped, and on two paths that happens before namespace teardown:
  - **Timeout.** Only the launcher was SIGKILLed; the init died later and asynchronously through `--die-with-parent`.
    - With an 800 MiB worker and an 800 MiB nested child, the call returned after 0.2 ms in 3/3 trials while the namespace processes still existed.
    - The worker was still in state `S` with 3 open descriptors.
  - **Normal exit.** bwrap's launcher exits as soon as the sandboxed command exits (the init reports it on an event fd). It does not wait for the init.
    - In 10/10 runs the init was still alive when the launcher returned.
    - Leftover descendants could therefore still write to the caller's output file after the call returned.
- PR #46 had relaxed two timeout tests to a 5 s window because of this race on a hosted runner. Several docstrings (for example `extract_reader`, `NativeImageNormalizer.normalize` and `prepare_page`) promised the stronger property.
- Two independent reviews shaped the final design:
  - **First version, replaced.** It froze the launcher with SIGSTOP and read `/proc/<pid>/task/<pid>/children`. It counted an already exited launcher as proof of teardown, which is false given the exit order above. Its tests also passed against the old behaviour.
  - **Second review (four lenses plus adversarial verification).** It found the defects fixed in the final design:
    - a `select()` call that fails at descriptor numbers of 1024 and above;
    - a report window that the pending retirement path could miss;
    - a report-less end of file treated too loosely;
    - report export ignoring an unconfirmed teardown;
    - two gaps in the tests.

## Decision

1. **New module and launch report.** The new module is `src/infrastructure/sandbox_process.py`, and its class is `Sandbox`.
   - `Sandbox` starts the launcher with `bwrap --info-fd`, passing only the write end of a close-on-exec pipe.
   - About 1.6 ms after launch, bwrap writes `{"child-pid": <init>, ..., "pid-namespace": <inode>}`. This also happens when stdin is an unwritten pipe.
   - The constructor reads that report, bounded at 5 s. It waits with `poll`, never `select`, so descriptor numbers have no limit.
   - It then opens a pidfd for the init, and keeps it only if `/proc/<pid>/ns/pid` matches the reported namespace.
   - **No namespace.** An end of file with an empty report means no namespace was created, but only if the launcher then exited by itself with a status of 0 or more, as bwrap does when it fails before cloning.
   - **Init already gone.** If the PID is missing, or now belongs to another namespace, the init has already exited and been reaped.
   - **Unknown state.** Every other outcome leaves the state `unknown` and is never treated as success. That covers a launcher killed by a signal, a partial or malformed report, and errors such as `EMFILE` from `pidfd_open`.
2. `Sandbox.retire(reason)`:
   1. If the report is still pending (an interruption inside the constructor), it first reads the report from the live launcher, for up to 0.5 s. A child that is cloned but not yet reported would otherwise be left behind with no name.
   2. It sends SIGKILL to the init through the pidfd.
   3. It kills and reaps the launcher, then reads any report that arrives late.
   4. It polls the init pidfd, bounded by `TEARDOWN_SECONDS = 5.0`.

   The kernel completes a namespace init's exit only after `zap_pid_ns_processes` has killed and reaped every other process in the namespace. A readable init pidfd therefore means that no sandboxed process holds the payload copy, the source descriptor or the caller's streams.

   `retire` returns whether teardown was confirmed. It does not raise for operating-system errors, and it is idempotent. It logs:
   - `sandbox_namespace_retirement_unconfirmed reason=… state=… signalled=… elapsed_ms=…` as a warning when teardown is not confirmed;
   - `sandbox_namespace_retired reason=… state=… elapsed_ms=…` for a confirmed timeout, interruption or abort;
   - nothing for a confirmed normal exit.

   No log contains paths, commands, PIDs, markers or content.
3. **`run_sandbox(args, *, timeout, **popen_options)`** behaves like `subprocess.run` for callers that use file or `DEVNULL` streams.
   - It refuses `PIPE`, because waiting without draining could deadlock, and it refuses a launcher that is not `bwrap`.
   - It waits for the launcher on a pidfd instead of `Popen.wait(timeout)`, which sleep-polls with up to 50 ms of delay. If the pidfd cannot be opened, it falls back to `Popen.wait`.
   - `TimeoutExpired` carries the caller's command and timeout.
   - It calls `retire` on every path: normal exit (`exit`), `TimeoutExpired` (`timeout`) and any other exception (`interrupted`). It then returns, or re-raises the original exception.
4. **Callers.**
   - The seven `subprocess.run` callers switch to `run_sandbox` with the same arguments, minus `check=False`, which `Popen` does not accept. Their error codes, statuses and normal-path results are unchanged. If teardown cannot be confirmed, they log the warning and return or raise as before.
   - `report_export.supervise` starts its launcher through `Sandbox` and calls `retire("exit" | "abort")` in its `finally` block, before closing its pipes.
   - If teardown is not confirmed, report export now fails closed: it logs `status=export_cleanup_uncertain` and raises `ReportExportError("export_cleanup_uncertain")`. `NativeReportExporter.render` and the application service already map that code to `closing=True`, so no further export is admitted.
5. **Tests.**
   - **Watching teardown.** `tests/process_probe.py::watch_teardown` runs the call in a thread and holds pidfds on the marked processes inside the sandbox once they are up. When the call returns or raises, it records whether all of them have exited at that moment. Zombies count as exited, so an exited process cannot be missed.
   - **Normal and timeout paths** (`tests/test_sandbox_process.py`):
     - normal exit and output;
     - a leftover descendant on normal exit;
     - timeout with a 256 MiB worker and a 256 MiB nested child, 3 runs;
     - descriptor numbers above 1100.
   - **Interruption paths:**
     - an interruption delivered only after the tree is up, and only while the call is still running;
     - an interruption inside the constructor before the report is read (the pending path).
   - **Launcher and report handling:**
     - a bwrap failure before cloning;
     - stand-in launchers that exit 1, kill themselves, or write a partial report;
     - malformed, recycled and reaped reports.
   - **Unconfirmed and refused cases:**
     - the bounded unconfirmed path, with the init kept alive by removing `--die-with-parent` and disabling the kill;
     - a `pidfd_open` failure;
     - idempotent retirement;
     - refusal of pipes and of launchers that are not bwrap.
   - **Processor and report export tests.**
     - The eight processor timeout tests use `watch_teardown` with a 2.5 s wall timeout, so the tree is seen alive before the timeout fires.
     - A report export test checks that an unconfirmed teardown closes admission.
     - Mocks of `subprocess.run` in the processor tests now patch `run_sandbox`.
   - **Regression check.** All 14 strict tests fail against each of two emulated regressions:
     - the old kill-the-launcher-only behaviour;
     - killing the init without waiting for it.

## Consequences

- **Timing.**
  - A timeout returns after teardown: about 1 ms for small workers, and 50–58 ms for an 800 MiB pair.
  - A normal exit waits for the init, typically well under a millisecond after the launcher. Waking on the launcher pidfd also removes up to 50 ms of polling delay from each call.
  - The wait is bounded at 5 s in pathological cases. After that, the warning is logged and the result or the timeout error is returned as before. Report export is the exception: it fails closed.
- After retirement the init can remain a zombie, with no descriptors and no memory, until its new parent reaps it.
- **Requirements.** The design needs Linux pidfds (`pidfd_open` and `pidfd_send_signal`, Linux 5.3 or later), bwrap `--info-fd`, and a readable `/proc/<pid>/ns/pid`. Without them, teardown is reported as unconfirmed rather than assumed.
- **Not covered.**
  - Sandboxes that do not use `file_verifier.sandbox_command` are unchanged: the coding sandbox, the check runner, checkpoint git, MCP stdio and the voice sandbox.
  - A signal that lands inside `Popen()` itself was already uncovered with `subprocess.run`.
  - An outside SIGKILL of the launcher in the microseconds between clone and report leaves an unnamed child. It is reported as unconfirmed, not as success.
- **D87 and voice evidence.**
  - The change touches `src/` and `tests/`, both in the D87 source-freeze scope. The 2026-11-09 D87 PASS therefore applies only to the `production` `0b67d95` tree. A tag needs D87 on the final tag tree, or the owner's named exception in the D90 form.
  - `src/**/*.py` is also in the B3/B4 voice source snapshot. As with D81, that evidence stays bound to its recorded snapshot, and a future `/voice` session recomputes the manifest.
- **Rollback.** Revert the change. Callers go back to `subprocess.run`, and the timeout tests then need the 5 s window from PR #46 again.
