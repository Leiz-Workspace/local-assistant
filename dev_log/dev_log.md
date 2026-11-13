

## 2026-11-13 — Forgejo release workflow (parallel to GitHub)

- **What.** `.forgejo/workflows/forgejo-release.yml` runs only on the Home Server's self-hosted Forgejo (`self-software-distribution-platform`), never on GitHub, which ignores `.forgejo/`. When a `v*` tag reaches the Forgejo pull mirror, it builds the same source bundle as the GitHub `package` job (`git archive` + SHA256SUMS), uploads it to Forgejo's generic package registry and creates a Forgejo Release. `workflow_dispatch` can build, and optionally upload, a dev bundle.
- **Not changed.** GitHub stays the source of truth: `ci.yml`, the GitHub Release and Actions artifacts are untouched. The Forgejo runner has only the `docker` label, so the GitHub workflows, which target `ubuntu-24.04`, never run there.
- **Validation.** A Forgejo sandbox copy of `develop` with this workflow and tag `v0.0.0-sandbox.1` produced the bundle, the generic package and the Release with both assets. The sandbox and its package were deleted afterwards.
