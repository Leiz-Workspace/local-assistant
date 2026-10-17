import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'benchmarks/scripts/context_32k_benchmark.py'
spec = importlib.util.spec_from_file_location('context32k', MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def test_filler_deterministic():
    assert mod.filler_lines(6) == mod.filler_lines(6)
    assert len(mod.filler_lines(6)) == 6

def test_canary_not_in_filler():
    assert mod.NEEDLE not in '\n'.join(mod.filler_lines(25))
