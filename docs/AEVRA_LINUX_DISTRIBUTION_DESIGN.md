# Aevra Linux distribution design (HAR-016-B, proposed)

Abbreviations: D90 = `docs/progress/D90_RELEASE_DECISION_DOSSIER.md`; D88R/D88S = `docs/progress/D88_CLEAN_INSTALL_REHEARSAL.md` / `D88_MODEL_PROVENANCE_SCORECARD.md`; BL = `docs/progress/HARNESS_PRODUCT_BACKLOG.md`; RB = `docs/HARNESS_CLI_DESKTOP_RUNBOOK.md`; ADR-188 = `docs/ADR/188-aevra-brand-and-native-webkit-desktop.md`; UNVERIFIED = "UNVERIFIED — needs review". **[A]** = third-party behavior that qualification must verify.

## 1. Purpose and status

**PROPOSED design only.** Nothing has been packaged, written, released, tagged or distributed. HAR-016-B is P2 PENDING (BL:72). D90 is NOT APPROVED / NOT TAGGED / NOT DEPLOYED (D90:36-37,138). GitHub Actions has not run since PR #52 because of a billing block, and PRs #53–#56 were merged on local evidence (D90:37). Qualification does not authorize a tag, Release, deployment or distribution (decision 1).

## 2. Current state

- **Distribution.** `aevra` 0.1.0. The wheel holds only `apps`/`src` (`pyproject.toml:2-4,22-32`). Only an editable install exists (RB:13; `uv.lock:11-13`).
- **Checkout-relative anchors** (`grep -rnE 'parents\[[0-9]\]' apps src` finds 15 anchors in 15 files):
  - Release-immutable: `apps/harness/assets.py:14`; `apps/desktop/launcher.py:18`, `runtime.py:16`, `main.py:9`; `apps/cli/main.py:236`; `src/infrastructure/coding_sandbox.py:18`; `apps/api/core/model_config.py:6` (parents[3], resolves to `configs/models.yaml`, on the harness path through `apps/harness/inference.py:9,54` and `browser.py:24`).
  - Not yet classified (targets not inspected): `src/infrastructure/qwen_embedding.py:18`, `qwen_query.py:15`, `qwen_token_preflight.py:17`, `browser_runtime.py:18`, `file_verifier.py:43`, `voice/manifest.py:32` (parents[3]); `apps/api/storage/ingestion.py:17` (parents[3]).
  - **User state:** `apps/api/storage/files.py:33` (parents[3]) defaults `ASSISTANT_FILES_ROOT` to `<ROOT>/data/files`.
  - **The app works only from a full source tree.** With per-release directories, anything under `<ROOT>/data/` becomes per-release.
- **Desktop.** Linux-only (`launcher.py:25`). The argv (`launcher.py:28-35`) is `[uv, "run", "--offline", "--no-project", "--python", "/usr/bin/python3", "python", "<ROOT>/apps/desktop/main.py"]`. If no backend is running, the launcher starts one on 127.0.0.1 (`launcher.py:76-139`). Any backend that reports `product == "Aevra"` is reused, with no version check (`launcher.py:78-87`). Output from owned processes goes to DEVNULL (`launcher.py:119-120,163`). There is no browser fallback (ADR-188:16).
- **Launchers.** `--write-launcher` accepts any path (`apps/cli/main.py:172,337-339`) and refuses one that already exists (`:227-228,261-262`). It writes Exec `"<absolute uv>" run --project <checkout> …` with no token (`:229-236`), plus an icon named by hash (`apps/branding/identity.py:41-45`). This host has two launchers, `~/.local/share/applications/io.aevra.Aevra.desktop` and `~/Desktop/Aevra.desktop`. Both use `~/.local/bin/uv` and the checkout path.
- **UI assets.** `aevra ui prepare` checks the tracked `configs/llama-cpp-commit.txt` (`assets.py:80-81`). It then downloads the pinned llama-ui `b11557`, enforcing SHA-256 and size limits, with no `latest` fallback (`assets.py:15-19,78-147`). A rerun checks `source_pin` and re-hashes only the files listed in the receipt (`assets.py:86-93`). It does not check `version`, `archive_sha256` or extra files. It copies `runtimes/llama.cpp/LICENSE` outside the receipt (`assets.py:133-140`). The browser route serves only files listed in the receipt (`apps/harness/browser.py:455,460-463`).
- **Tarball blocker.** `runtimes/llama.cpp/` is gitignored (`.gitignore:8`; `git ls-files runtimes` returns 0), and CI builds the tarball with `git archive … HEAD` (`.github/workflows/ci.yml:197`). **Every install from a `git archive` tarball therefore fails `ui prepare` at `assets.py:133` until R1 is done.** This is inferred from the code and untested.
- **State.**
  - Credentials live in `~/.local/state/local-assistant/{token,principals.json}` (`apps/cli/client.py:16-17`). `initialize_auth` refuses if either file exists (`client.py:23-28`), and an owned backend needs a matching principal (`launcher.py:90-96`).
  - The WebKit profile is `~/.local/state/aevra/desktop/<hash>/`, mode 0700 (`runtime.py:63-106`).
  - Harness history stays in memory unless `--state-dir` is set (`apps/cli/main.py:86,307-308`; `apps/harness/main.py:124`; RB:7).
  - File blobs default to `<ROOT>/data/files`, and startup refuses an incompatible Alembic revision (`apps/api/storage/files.py:24-35`).
- **Services.** CORE is a separate llama.cpp container (`docker-compose.yaml:22-46`). Shared services live in `../infras` (`README.md:40`). Weights are gitignored (`.gitignore:2-5`). The desktop loads no model (`docs/AEVRA_DESKTOP.md:26`).

## 3. Target

- One user on one Ubuntu x86_64 desktop, using the OS's GTK3 and WebKitGTK 4.1, with the backend on 127.0.0.1.
- **OS:** Ubuntu 24.04, the CI baseline (`README.md:42`; `ci.yml:30`). Ubuntu 26.04, the Home Server OS (`README.md:42`), is **blocked on decision 4**:
  - On this 26.04.1 host, `apt-cache policy python3.12` shows 3.12.3-1ubuntu0.17 only from `/var/lib/dpkg/status`. It is a 24.04 build left over from the upgrade, and no configured repository provides or updates it.
  - A fresh 26.04 install probably has no `/usr/bin/python3.12` [A].
  - README:43 requires a system interpreter, and `coding_sandbox.py:23-27` refuses any interpreter outside `/usr/bin`.
- **Python:** CPython 3.12 only. Two 3.11.14 attempts failed (D88R:9-10). 3.12 installed 44 packages both online and offline (D88R:11-12).
- **Out of scope:** Windows and macOS (`launcher.py:25`; BL:137), auto-update (BL:137), multi-user installs, and bundling models or llama.cpp.

## 4. Options compared

| Concern | A. uv venv + desktop entry | B. zipapp/pex | C. Debian package | D. AppImage/Flatpak |
|---|---|---|---|---|
| GTK/WebKit, bubblewrap | OS apt. The `bwrap-userns-restrict` profile belongs to `apparmor` (`dpkg -S`), not to `bubblewrap` as README:49 says | OS; `main.py` must stay a file (`launcher.py:35`) | `Depends` [A] | AppImage bundles WebKit; nested userns breaks the sandbox [A] |
| Update/rollback | Release dirs side by side | Swap the file | apt; needs the old .deb [A] | Swap the file or roll back the commit [A] |
| Code fit | Works from a tree after R1 and R6 | Breaks all 15 anchors, including `model_config.py` on the harness path. Needs a resources/XDG refactor of 15 files plus tests (not estimated) | Same refactor; `/opt` is read-only; needs root and signing | Same refactor. Outside the scope ADR-188:20 describes, so it needs a new ADR |
| Ships third-party binaries? | Yes, unless an export allowlist is set (§5) | Yes | Yes | Yes |

No option ships llama.cpp or weights.

## 5. Recommended path

**Option A**, qualified from a tarball of a named commit built locally:

1. **It fits the current code, with blockers.** `ui prepare` fails on every tarball until R1. `data/files` lands inside the release directory unless R6 is done.
2. **The tarball can be built locally.** CI defines a `git archive` + `SHA256SUMS` job (`ci.yml:181-205`) and a `v*` Release job (`ci.yml:223-239`). But Actions is not running (D90:37), and non-tag artifacts expire after 30 days (`ci.yml:205`). Reusing CI waits until Actions is restored.
   - Qualification source: `git archive --format=tar.gz --prefix=local-assistant-<ref>-<sha7>/ <commit>` plus `sha256sum`.
   - Record the commit, tree and sha256. The name matches `ci.yml:195`.
3. **It is not source-only.** There is no `.gitattributes`, so the tarball holds every tracked file, including 3,189,520 bytes of media (`du -cb` over `git ls-files`). That includes whisper's `jfk.flac` (`tests/fixtures/audio/README.md:5`), MP4/MKV/DOCX/PDF/PNG fixtures, `aevra-logo-assets/*` and two `.bak` files. Decision 3 picks one of two paths:
   - export-ignore `tests/fixtures`, `benchmarks`, `docs/evidence` and `*.bak`, then redo the inventory; or
   - require the D1 SBOM/notice (`docs/ADR/174-proposed-opt-in-authenticated-voice-integration.md:62`; D90:88,136) for any audience beyond the owner's machines.
4. **Integrity.** Existing checks: `uv sync --locked`, the UI receipt, the icon manifest (`runtime.py:109-121`) and the model hashes.
   - `SHA256SUMS` is unsigned and ships next to the tarball (`ci.yml:198,239`). It catches corruption, not substitution.
   - Pin the tarball sha256 out of band in the owner-approved release record, or verify a signature [A].
5. **Rollback is cheap only for harness, desktop and credential state.** File blobs live inside the release by default (`files.py:30-35`), and the schema is not rolled back (`files.py:24-29`).

**Required before qualification (not done):**

- **R1 (hard blocker).** Vendor the pinned MIT text instead of reading `runtimes/llama.cpp/LICENSE`. Decide whether the UI shows it. If not, keep it out of the receipt's `files` (the list the browser serves) and hash it separately.
  - *Status 2026-11-11: implemented.* The upstream file at pin `5c8854fd` is vendored as `apps/harness/third_party/LLAMA_CPP_LICENSE` (SHA-256 `94f29bbe…`, pinned by `tests/test_product_assets.py`). It is still copied outside the receipt and is not served. Whether the UI shows it remains open.
- **R2.** An atomic launcher-replace mode for receipt-recorded paths. O_EXCL stays the default.
- **R3.** An installer/preflight script that never runs apt or sudo.
- **R4.** Set `requires-python` to 3.12. It is now `>=3.11` (`pyproject.toml:5`, `uv.lock:3`), and numpy forks between 2.4.6 and 2.5.4. The change rewrites `uv.lock`, which is inside the D87 freeze scope (D90:135), so a new D87 run is required.
- **R5.** `hatchling>=1.26,<2` (`pyproject.toml:27-29`) has no entry in `uv.lock` (grep count 0), so every install fetches a build backend that is neither pinned nor hashed.
  - Pin it with hashed build constraints [A], or use `--no-install-project` with an entry point that needs no project wheel (this changes `apps/cli/main.py:229-236`). A non-editable wheel breaks the anchors.
  - Specify where uv comes from, which version (this host has 0.9.13) and how it is verified. The preflight refuses other versions.
- **R6.** Set `ASSISTANT_FILES_ROOT` and any other state roots outside the release directory, or refuse to install when those features are enabled.
- **R7.** Add a release id and the UI pin to `/api/v1/harness/status`. The launcher refuses a mismatched backend with `aevra_backend_restart_required` (`launcher.py:84-85`).
- **R8.** A diagnostics mode that writes owned-process logs to a 0600 file under the state directory, with no prompts or tokens (AGENTS.md).

C may be revisited later. B and D are rejected for v1.

## 6. Install / update / rollback / uninstall

**Layout:** each release goes in `~/.local/share/aevra/releases/local-assistant-<ref>-<sha7>/` with its own `.venv` and `data/ui`. The state directories and R6 roots are never touched. Each release gets a receipt with no secrets, recording:
- commit and tree;
- tarball, uv.lock and UI-archive sha256;
- uv version and Alembic revision;
- every launcher and icon path written.

**Preflight (read-only):**
- Ubuntu version, plus `/usr/bin/python3.12` and its dpkg origin.
- `gi`, the uv version, and `dpkg-query` for the packages in `README.md:49-50`.
- `/etc/apparmor.d/bwrap-userns-restrict` exists and is loaded [A]; `kernel.apparmor_restrict_unprivileged_userns` (1 on this host); a bwrap probe.
- Credentials are both present or both absent. If only one exists, refuse with guidance and never regenerate.
- No other release is listening on 127.0.0.1:7090 (`apps/cli/main.py:84`).
- Enough free disk.

**Install:**

1. Run the preflight.
2. Compare the tarball sha256 with the out-of-band pin.
3. Extract into `.<name>.partial`. Refuse if the final directory exists.
4. Run `UV_PYTHON_PREFERENCE=only-system uv sync --locked --no-dev --python /usr/bin/python3.12`, with R5.
5. Run `aevra ui prepare`.
6. Run `aevra init` only if both credential files are absent.
7. Run `aevra doctor` and `--check`.
8. Rename atomically, then write the launchers and the receipt.

On failure, quarantine `.partial` with the reason. Retries use a fresh staging directory.

**Update:**

1. Close the desktop. Confirm that no backend from any release, including a manual `aevra serve`, is on port 7090.
2. Run install steps 1–5, 7 and 8.
3. Copy `data/ui` only if `version`, `source_pin` and `archive_sha256` match and no unlisted files exist.
4. Replace every recorded launcher (R2) and keep the previous release.

Releases with Alembic migrations stay blocked until backup and downgrade are documented (`docs/ADR/123-isolated-local-release-restore-drill.md`).

**Rollback:** allowed only if the live Alembic revision equals the one in the target receipt. Otherwise refuse with a clear message, because the old release would fail at `files.py:24-29`. The same port check as update applies. Whether IndexedDB stays compatible across UI pins is UNVERIFIED (C10).

**Uninstall:**
- Refuses while a recorded release is running.
- Removes all recorded launchers (both host paths), the hashed icons of every release (`identity.py:41-45`), the release directories and the receipts.
- Reports `~/.cache/uv` and any `data/files`/`data/backups` inside release trees, without deleting them.
- History is kept (`docs/AEVRA_DESKTOP.md:62-67`). Deleting state or credentials is a separate owner action.

## 7. Dependency and license inventory

| Component | Pin | Source | License (repo evidence) | Bundled? |
|---|---|---|---|---|
| Aevra `apps/`, `src/` | 0.1.0 | this repo | MIT (`LICENSE:1-3`) | Yes |
| Tracked media/fixtures | 3,189,520 B | e.g. openai/whisper | `tests/fixtures/audio/README.md:5`; the rest UNVERIFIED | Yes, unless export-ignored |
| Branding: 5 hashed assets + `manifest.json` (+2 `source_files`) | `manifest.json` | owner-supplied dragon (ADR-188:9) | UNVERIFIED | Yes |
| llama-ui | `b11557`, `840a7017…` | ggml-org | MIT text copied (`assets.py:133`); JS dependencies UNVERIFIED | Downloaded |
| llama.cpp | `5c8854fd88319125125dc4b836c98b1b215b0f23` | ggml-org | MIT, from a local untracked checkout at the pin, not in Git (`runtimes/llama.cpp/LICENSE:1-3`; `git -C runtimes/llama.cpp rev-parse HEAD`); `licenses/LICENSE-jsonhpp` UNVERIFIED | No |
| CUDA image | `nvidia/cuda:12.4.1-devel-ubuntu22.04`, `LLAMA_COMMIT` (`docker/llama.Dockerfile:2,16`) | Docker Hub | UNVERIFIED | No |
| CORE GGUF | Q6_K, `073a9275…bfef` (`configs/models.yaml:9`) | bartowski @ `182be2fd` | Apache-2.0 as declared on the quantizer card (`docs/progress/D74_VOICE_RIGHTS_REVIEW.md:11`); not legal clearance (D88S:22) | No |
| CORE mmproj | `models.yaml:8` | same | same | No; **unhashed** |
| UNRESTRICTED GGUF | `c0ba7beb…4986` (testing) | HauhauCS | UNVERIFIED — needs review (no repo record; D90:63,136) | No |
| Optional: embedding/reranker (D88S:11-13; rights unreviewed, D90:136), ASR/TTS (`configs/*-evaluation-candidates.json`), browsertrix (`browser_runtime.py:19`), sandbox image (`configs/python-sandbox-image-digest.json`), Docker socket | configs | HF / Docker Hub | UNVERIFIED | No; needed only if the feature is enabled |
| PyPI runtime | 13 direct; lock `cca077ac…` resolves 44 third-party + `aevra` (CPython 3.12, linux/x86_64) | pypi.org | UNVERIFIED | No |
| Build backend | `hatchling>=1.26,<2`, unpinned | pypi.org | UNVERIFIED | No |
| CPython 3.12; uv | 24.04: apt. 26.04: none (this host's copy is a 24.04 leftover). uv 0.9.13, origin unrecorded | decision 4 | UNVERIFIED | No |
| PyGObject/GTK3/WebKitGTK 4.1, bubblewrap, apparmor, ffmpeg, tesseract, poppler, LibreOffice, git | this host: 3.56.2-1 / 3.24.52-0ubuntu1 / 2.52.6-0ubuntu0.26.04.1; the rest via `dpkg-query` | Ubuntu apt | UNVERIFIED | No |
| PostgreSQL, Vault, Qdrant, SearXNG, Docker | `../infras` (not read) | upstream | UNVERIFIED | No |

**Invariant (checked by C16):** install, update and rollback never call `huggingface-hub` (`pyproject.toml:11`) or `docker pull`.

## 8. Clean-machine qualification plan

- **Q1/Q2:** fresh Ubuntu 24.04 x86_64, on GNOME Wayland (primary) and on X11.
- **Q3:** Ubuntu 26.04, only after decision 4 names a Python source. As designed, it fails the preflight.
- **Q4:** this host, only with an owner authorization that names what will change: launchers, the running backend, credentials and WebKit history. AGENTS.md forbids restarting shared services without authorization.
  - First, back up both launchers, the icons, and the metadata of `~/.local/state/{local-assistant,aevra}` (paths, modes and hashes; contents not printed).
  - Undo: restore the launchers and icons, remove the new release, and leave state untouched.
- **Q5 (negative):** an OS without Python 3.12 or WebKitGTK 4.1, for example 22.04 [A]. The preflight must refuse.

The VMs have no GPU, so they use the native synthetic stream with 0 model calls (BL:23,167). CORE is checked only on an authorized GPU host, without restarting shared services.

**Checks:**

- **C1.** The preflight names every missing prerequisite, including the python3.12 origin, AppArmor and half-present credentials.
- **C2.** A tampered tarball is refused. **C2b.** If the tarball and `SHA256SUMS` are both replaced, the install is refused.
- **C3.** A sync from a clean cache installs 44 third-party packages plus `aevra`. Record the lock SHA (D88R records none; the current one is `cca077ac…`) and whether uv counts the project. An offline reinstall works, including the build backend.
- **C4.** The receipt lists 70 files and 10,074,640 bytes (RB:35). The directory holds 72 files, adding `LLAMA_CPP_LICENSE` and `receipt.json`. A tampered file raises `ui_asset_changed`, a rerun downloads nothing, and unlisted files in a copied `data/ui` are refused.
- **C5.** `--check` reports `webkitgtk-4.1` and `external_browser: false`.
- **C6.** The launchers hold no token, and the icon and `StartupWMClass` are correct.
- **C7.** `window_opened` and `window_closed` both occur, the owned backend stops, and no orphan processes remain.
- **C8.** Permissions are 0700/0600, and a symlinked profile is refused.
- **C9.** The bwrap smoke test passes with the AppArmor restriction on.
- **C10.** An update, rollback, update cycle keeps history and credentials. **C10b.** A backend from another release on port 7090 is refused. **C10c.** A rollback after a schema change is refused.
- **C11.** Uninstall keeps state, removes all recorded launchers and icons, and refuses while a release is running.
- **C12.** The R8 logs contain no credentials or prompts.
- **C13.** Accessibility smoke test: keyboard, Orca and 2x scaling.
- **C14.** Record RSS and per-release disk use.
- **C15.** A network loss during sync or `ui prepare`, and a full disk, each leave a quarantined `.partial` and allow a retry.
- **C16.** No `huggingface-hub` or `docker pull` calls are made.

**Evidence** goes in `docs/progress/HAR016B_QUALIFICATION_<date>.md`:
- ISO SHA-256, `dpkg-query` and uv versions, and the commit, tree and tarball sha256.
- Exact commands, exit codes, counts, skips, screenshots and receipts.
- Software tests are kept separate from model quality, and a skip is never a PASS (AGENTS.md).

## 9. Owner decisions required

1. Confirm that qualification authorizes no tag, Release, deployment or third-party distribution. Those stay gated by D87, D88, D89 and D90. The D89 boxes are unticked (`docs/progress/D89_MANUAL_ACCEPTANCE_CHECKLIST.md:43-44`; D90:137). Reconcile the scope with HAR-015 (P1, PARTIAL: BL:23,70).
2. Approve Option A, and the rejection of B and D.
3. Choose the audience, and choose between an export allowlist and shipping the tracked binaries under D1.
4. Choose the matrix:
   - 24.04 only; or
   - 26.04 with Python 3.14 qualified on new evidence; or
   - 26.04 with a named non-apt 3.12 source that gets security updates (README:43 advises against a uv-managed Python).
5. **This gate comes first:** no tag is created during HAR-016-B. Any `v*` tag publishes a Release automatically (`ci.yml:223-239`), and branch protection is unavailable (D90:38,156). Tag only after the owner signs D90 section 5 (D90:161) and D87 passes on the tag commit (D90:119). Then choose the commit to qualify.
6. Approve R1–R8. R4 means a new D87 run.
7. Decide whether UNRESTRICTED is in desktop scope (D90 Scope A).
8. Confirm the icon's license or ownership.
9. Decide the install root, the migration of this host's editable install and both launchers, and whether Exec uses an absolute uv path or a stable shim.
10. Authorize VM resources, a GPU host and the Q4 change list.
11. Confirm that Windows and macOS stay out of scope until hardware and a separate assessment exist.
