# ADR 176 — Bounded foreign GPU tolerance and B3 preflight

**Purpose:** Remove a host-specific blocker found in the single ADR174/175 B3 campaign without relaxing the measured voice resource caps, and allow exactly one replacement B3 panel.

**Status:** ACCEPTED, 2026-11-06. The owner chose "Cho phép app desktop nhỏ" for B3: tolerate foreign GPU compute processes up to 1 GiB total, keep free-VRAM and RAM caps, then run exactly one B3 panel. Product activation, model/default changes, downloads and D90 release remain excluded.

## Context

- The B3 campaign of 2026-11-05 (`data/backups/d74-main-integration-first/result.json`, private) ended `NOT_PASS` with `main_voice_prepare_fault`: 6/6 rows unattempted, 0 retries, owned CORE exited 0 and was reaped. The application audit shows the VAD worker load admitted at 21:17:18.384 and `dependency_failed` at 21:17:18.400, before any speech input; the exact guard that fired was not logged.
- ADR175 made `Monitor.require_owned_compute` reject any GPU compute process outside the owned voice workers and the borrowed CORE. The post-failure NVML record lists `gnome-remote-desktop` holding about 223 MiB. On 2026-11-06 NVML on the same desktop lists three foreign compute processes: `gnome-remote-desktop-daemon` (213 MiB), `nautilus` (46 MiB) and `rustdesk` (272 MiB). They are normal desktop contexts, so the ADR175 rule fails on this host before any speech is processed.
- The loopback trial (ADR173) and the resident CUDA runs (ADR170–172) used the same CORE launcher and the same 8 GiB worker+CORE RSS cap and passed; they had no foreign-process rule. The B3 CORE receipt shows a 7.71 GiB RSS peak sampled during model load, before llama.cpp releases the mappings of GPU-offloaded tensors. Whether steady-state RSS also constrains B3 is not proven, hence the preflight below.

## Decision

1. `src/infrastructure/voice/ipc.py`: foreign compute processes (not in the owned or borrowed-CORE process trees) are tolerated while their summed `usedGpuMemory` is at most `FOREIGN_VRAM_LIMIT = 1 GiB`. A row with an unknown, negative, non-integer or NVML not-available size counts as over the limit, preserving fail-closed behaviour. Foreign processes are never signalled. A finite `voice_foreign_gpu_tolerated processes=<n> mib=<m>` event is logged only when the count or size changes; no names, PIDs or content are logged.
2. Unchanged: owned ASR VRAM at most 4.5 GiB, free VRAM at least 1.25 GiB while running and 6 GiB before ASR load, 14 GiB MemAvailable before loads, worker+CORE RSS at most 8 GiB, TTS at most 2 GiB, main-process 1 GiB, RAM workspace budget, timeouts and call budgets.
3. `benchmarks/scripts/main_voice_integration.py`: after the owned CORE is ready and 5 seconds have passed, and before any voice model loads, `preflight` stops the run when CORE process-tree RSS is at least 6 GiB (`CORE_RSS_STOP`, leaving under 2 GiB for VAD/ASR/TTS inside the 8 GiB cap) or foreign GPU use exceeds the limit. The result is then `PREFLIGHT_STOPPED` with `panel_consumed: false`; the panel counts as spent only once `/ui/voice/prepare` is requested. A new `--root` option keeps each campaign in its own `data/backups` directory; the first campaign's evidence is not reused or overwritten.

## Replacement B3 scope

Exactly one panel in `data/backups/d74-main-integration-adr176`: the same retained four Vietnamese speech inputs and two no-speech negatives, maximum 6 VAD / 4 ASR / 4 CORE / 4 TTS calls plus one zero readiness, no retry, same models, voice, CORE command and acceptance rule (exact prior transcript/answer/audio and at most 4 s complete server response). A preflight stop is reported as such and is not a B3 result. A failed panel stays failed. Physical first-audible, room/short/quiet speech and product/default decisions remain B4/D74 gates.

## Validation, migration and rollback

Tests cover tolerated desktop totals including the exact limit, over-limit totals, unknown/invalid sizes, single change-logging, and preflight pass/stop cases. No data migration. Rollback restores the ADR175 rule by setting `FOREIGN_VRAM_LIMIT` to 0 or reverting this change; earlier evidence stays unchanged.
