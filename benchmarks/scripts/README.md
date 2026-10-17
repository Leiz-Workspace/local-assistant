# Local Assistant — Runtime Configuration Benchmark (CT07–CT09)

Tested target: llama.cpp build 11557; two Qwen3.5-9B Q6_K model services (`core`, `unrestricted`) in existing `docker-compose.yaml`.

## Install

Copy `runtime_bench.py` into project at `benchmarks/scripts/runtime_bench.py`.
Run from project root. Dependencies: `uv add --dev httpx pyyaml pillow` **only if missing** (these were already present in this project's prior environment).

```bash
cd ~/Workspace/Server/ai
uv run python benchmarks/scripts/runtime_bench.py --profile core --groups baseline,vision,reasoning
```

Above is **dry-run**. Actual test (WARNING: stops/recreates BOTH model services, and leaves them STOPPED):

```bash
uv run python benchmarks/scripts/runtime_bench.py \
  --profile core --groups baseline,vision,reasoning \
  --execute --confirm-restarts
```

Then:

```bash
uv run python benchmarks/scripts/runtime_bench.py \
  --profile unrestricted --groups baseline,vision,reasoning \
  --execute --confirm-restarts
```

Advanced opt-in experiments (run after initial tests):

```bash
uv run python benchmarks/scripts/runtime_bench.py \
  --profile core --groups kv,effort,budget \
  --execute --confirm-restarts

# MTP experimental: may fail, consume more VRAM, or show regressions.
uv run python benchmarks/scripts/runtime_bench.py \
  --profile core --groups mtp \
  --execute --confirm-restarts
```

Restart usual service after all tests:

```bash
docker compose -f docker-compose.yaml --profile core up -d --no-build core
```

## What it does

- Reads existing Compose configuration, including exact `--model`, `--alias`, network, mounts and CUDA image.
- Generates a temporary Compose override **without editing your `docker-compose.yaml`**.
- Stops `core` and `unrestricted` between configurations to avoid simultaneous GPU allocations.
- Recreates only the selected model service, polls `/health` and checks `/v1/models` ID.
- Sends a deterministic test request (`temperature=0`) and measures upstream `timings.predicted_per_second`, wall-clock duration and VRAM with `nvidia-smi`.
- Outputs results to `benchmarks/results/runtime-config/` in timestamped `.json` and `.csv` formats.
- Stops model services at completion or Ctrl+C. **It does not restore your original running service.** Other home-server services are not managed.

## Important limits

- This is a **screening benchmark**, not a full correctness suite. Text baseline only checks nonempty response; reasoning math test checks 28; Vision checks red/green/blue order on a generated picture. Manually inspect `answer` and `error` fields.
- Effort support in server help does not imply actual Qwen template obedience. Inspect thinking trace and repeat tests before conclusions.
- Each configuration starts a fresh container and warmup may affect timing. Run multiple repetitions for statistical comparisons. `predicted_per_second` is upstream timing, not full end-user throughput.
- MTP is experimental. Leave it disabled in normal Compose until measured stable.
- Vision uses the `mmproj` paths from your current project. Dynamic image resolution may change VRAM use significantly beyond this small test.
- GPU memory measurements include host desktop/other processes; `vram_loaded_mib - vram_before_mib` estimates incremental use.
- API is bound to host `127.0.0.1:8080`; do not expose to untrusted networks. No secrets are stored in these benchmark results, but generated replies may contain sensitive content with custom prompts.
- A failure of one case is recorded, and the script proceeds to the next case. If readiness/model identification fails, inspect log captured in JSON.
