
from pathlib import Path
import numpy as np
from gguf import GGUFReader

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "core": ROOT / "models/core/qwen3.5-9b/mmproj-Qwen_Qwen3.5-9B-bf16.gguf",
    "unrestricted": ROOT / "models/unrestricted/qwen3.5-9b/mmproj-Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-BF16.gguf",
}

readers = {
    name: GGUFReader(str(path), "r")
    for name, path in FILES.items()
}

tensors = {
    name: {tensor.name: tensor for tensor in reader.tensors}
    for name, reader in readers.items()
}

core = tensors["core"]
unrestricted = tensors["unrestricted"]

print("CORE tensors:", len(core))
print("UNRESTRICTED tensors:", len(unrestricted))

core_only = sorted(set(core) - set(unrestricted))
unrestricted_only = sorted(set(unrestricted) - set(core))

print("CORE-only tensor names:", len(core_only))
print("UNRESTRICTED-only tensor names:", len(unrestricted_only))
print("CORE-only examples:", core_only[:10])
print("UNRESTRICTED-only examples:", unrestricted_only[:10])

shape_mismatch = []
type_mismatch = []
value_mismatch = []
identical = 0

for name in sorted(set(core) & set(unrestricted)):
    a = core[name]
    b = unrestricted[name]

    if tuple(a.shape) != tuple(b.shape):
        shape_mismatch.append(name)
        continue

    if a.tensor_type != b.tensor_type:
        type_mismatch.append(name)
        continue

    # Compare raw stored tensor bytes/values without converting
    # BF16 to float, to avoid precision conversion artifacts.
    if np.array_equal(a.data, b.data):
        identical += 1
    else:
        value_mismatch.append(name)

print("\n=== RESULTS ===")
print("Identical tensors:", identical)
print("Shape mismatches:", len(shape_mismatch))
print("Type mismatches:", len(type_mismatch))
print("Value mismatches:", len(value_mismatch))
print("Value mismatch examples:", value_mismatch[:20])

if (
    not core_only
    and not unrestricted_only
    and not shape_mismatch
    and not type_mismatch
    and not value_mismatch
):
    print("\nPASS: All stored tensors are identical.")
else:
    print("\nDIFFERENCES FOUND: Review details above.")
