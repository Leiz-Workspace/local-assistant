"""Pin the frozen HAR-006 v2 design tests to the commit that recorded the v2 evidence (ADR-195)."""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORDED_COMMIT = "6cd4da23fd1dd3bb1a8cbcfd2323bc74fae13436"
MODULE = "test_context_har006_v2.py"
MODULE_TESTS = 114
# sha256 of every file in v2's SOURCES at the recorded commit (Window 2 ran there).
RECORDED_SOURCES = {
    "benchmarks/context_har006_v2.py": "98f57b70b45c23808d2b2e953884549f996ef73e758607a006485dab22a2e991",
    "src/application/services/context_inspection.py": "c839113444fe9f15583ff57f7cebea548da705743cf144d676fca452bb8fd3da",
    "src/application/services/context_composer.py": "dd4f1987e05c971aca220fc42f9ec053affa73e0d650269ee2e2f41e794fc59b",
    "src/application/services/conversation_context.py": "856b3bb80635f1dec3f46666584b2d9806f0049192e069d858fad100d096cf5b",
    "src/application/services/context_reduction.py": "8800e17b56d68008f16bf6a63e7ea3ea021525fab16ace42eece8e6ac282f4ee",
    "apps/harness/inference.py": "11f7e9f94b5e5bde03ee1ff788f6278b050521942631f3d6660e7d23e8d60bb2",
    "apps/api/runtime/presets.py": "9c3e4836725c7f8d6b74b4d2e2b0da3ac1ed4f61fed9afacd09b3f66d87d8a69",
    "apps/api/services/llama_gateway.py": "c7d84baabdbd8baf688cace7a0fc8aec4f656f77b29b3e38e5282a488dbdadd3",
    "benchmarks/harness_stream_timing.py": "f8f3bed31dbf2c2b2328160ad2507b9b4bf7638cc25b7b83ce3e83ebf2ca64e7",
    "benchmarks/harness_resources.py": "3c22aa2c1c9e147c7caade6bdf288c6547ce40c58604a888ba5ba123844dfb49",
    "configs/models.yaml": "5a11768ab9bb30b2ebb3b4db32d23bfabdb1ee9d5d1cc490d2f604074755cde3",
}
# Every test that depends on chain() or the native_run fixture; their design check
# rebuilds the expected last message with v2's private block().
PINNED = (
    "test_6_calibration_and_design_check_under_proxy_counter",
    "test_6_derived_expectation_table_equals_the_matrix",
    "test_6_probes_and_sweep_behave_as_predicted",
    "test_6_flag_on_only_failure_is_flag_drift_not_a_crash[inference_failure]",
    "test_6_flag_on_only_failure_is_flag_drift_not_a_crash[value_error]",
    "test_9_window1_manifest_with_zero_generations",
    "test_9_window2_freezes_first_and_keeps_every_first_outcome",
    "test_9_receipts_are_exclusive_and_owner_only",
    "test_9_wall_cap_and_stream_failure_keep_first_outcomes",
    "test_9_sampler_failure_is_a_first_outcome_and_never_streams",
    "test_9_window1_stop_gates_halt_before_any_generation",
    "test_9_window2_stop_gates_halt_before_any_generation",
    "test_9_window2_refuses_a_missing_or_partial_software_record",
    "test_10_recheck_verifies_an_untouched_run",
    "test_10_recheck_detects_tampering[answer]",
    "test_10_recheck_detects_tampering[payload]",
    "test_10_recheck_detects_tampering[timings]",
    "test_10_recheck_detects_tampering[hash]",
    "test_10_recheck_detects_tampering[summary]",
    "test_10_recheck_detects_tampering[software]",
    "test_10_recheck_compares_the_software_record_and_never_substitutes_it",
)
# An async test that relied on a pinned sync test to fill v2's cached calibration().
WARM_CALIBRATION = ("test_6_conservation_detects_each_tampering",)
REASON = (
    f"HAR-006 v2 is frozen at its recorded commit {RECORDED_COMMIT[:7]} (ADR-195): "
    f"these {len(PINNED)} tests rebuild the last message with v2's private block(), "
    "which no longer matches the composer; run them from a worktree at that commit"
)


def changed_sources(root=ROOT):
    """Return the v2 SOURCES paths whose bytes differ from the recorded commit."""
    changed = []
    for name, expected in RECORDED_SOURCES.items():
        try:
            actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        except OSError:
            actual = None
        if actual != expected:
            changed.append(name)
    return changed
