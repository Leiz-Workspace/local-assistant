"""Run from project root: uv run python -m pytest tests/test_runtime_bench_advanced_v3.py -v"""
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "benchmarks" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import runtime_bench_advanced as benchmark


def test_integration_cases():
    cases = benchmark.cases_for({"integration"})
    assert {x["name"] for x in cases} == {"vision_mtp_off", "vision_mtp_on", "thinking_mtp_off", "thinking_mtp_on"}
    assert all("vision" in x for x in cases)


def test_cli_composition():
    cases = benchmark.cases_for({"integration"})
    original = ["--model", "/models/a.gguf", "--reasoning", "off", "--no-mmproj"]
    for case in cases:
        args = benchmark.command_for(original, case, "core")
        assert args.count("--reasoning") == 1
        assert ("--mmproj" in args) == case["vision"]
        assert ("--spec-type" in args) == case["mtp"]


def test_quality_checks():
    assert benchmark.score("vision", "Red, green, blue", "stop") == "PASS"
    assert benchmark.score("vision", "Green, red, blue", "stop") == "WRONG"
    assert benchmark.score("writing", "FastAPI llama.cpp Qdrant security errors FINAL: DONE", "stop") == "WRONG_OR_TOO_SHORT"
    assert benchmark.score("writing", "unfinished", "length") == "INCOMPLETE"
    answer = "FastAPI llama.cpp Qdrant security errors. " * 100 + " FINAL: DONE"
    assert benchmark.score("writing", answer, "stop") == "PASS_FORMAT_REVIEW_CONTENT"
