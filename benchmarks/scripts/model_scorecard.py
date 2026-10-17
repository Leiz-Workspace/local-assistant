
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("benchmarks/results")
OUTPUT = ROOT / "scorecards"
OUTPUT.mkdir(parents=True, exist_ok=True)

WEIGHTS = {
    "reasoning": 20,
    "coding": 20,
    "agent": 20,
    "vietnamese": 10,
    "multimodal": 10,
    "performance": 10,
    "memory_context": 5,
    "provenance": 5,
}

PROFILES = ("core", "unrestricted")


def read_json(path):
    if not path.exists():
        print(f"WARNING: Missing {path}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(profile):
    quality = read_json(ROOT / "quality" / f"{profile}.json")
    coding = read_json(
        ROOT / "quality/day11" / f"{profile}-coding.json"
    )
    structured = read_json(
        ROOT / "quality/day11" / f"{profile}-structured.json"
    )
    agent = read_json(
        ROOT / "quality/day12" / f"{profile}-agent.json"
    )

    categories = {
        name: {"passed": 0, "total": 0}
        for name in ("reasoning", "coding", "agent", "vietnamese")
    }

    def add(category, passed):
        item = categories[category]
        item["total"] += 1
        item["passed"] += int(bool(passed))

    if quality:
        for test in quality.get("results", []):
            category = test.get("category")

            if category in ("reasoning", "mathematics"):
                add("reasoning", test.get("passed"))
            elif category == "coding":
                add("coding", test.get("passed"))
            elif category == "tool_calling":
                add("agent", test.get("passed"))
            elif category == "vietnamese":
                add("vietnamese", test.get("passed"))

    if coding:
        for test in coding.get("results", []):
            add("coding", test.get("passed"))

    if agent:
        for test in agent.get("results", []):
            add("agent", test.get("passed"))

    covered_weight = 0
    earned_weight = 0

    for name, item in categories.items():
        if item["total"] > 0:
            weight = WEIGHTS[name]
            rate = item["passed"] / item["total"]
            item["rate"] = rate
            item["weight"] = weight
            covered_weight += weight
            earned_weight += weight * rate
        else:
            item["rate"] = None
            item["weight"] = WEIGHTS[name]

    return {
        "profile": profile,
        "categories": categories,
        "structured_output": (
            structured.get("passed")
            if structured else None
        ),
        "covered_weight": covered_weight,
        "earned_weight": earned_weight,
        "provisional_rate": (
            earned_weight / covered_weight
            if covered_weight else None
        ),
        "unscored_categories": [
            name for name in WEIGHTS
            if name not in categories
        ],
    }


reports = {p: summarize(p) for p in PROFILES}

result = {
    "generated_at_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "benchmark_stage": "day13_provisional",
    "weights": WEIGHTS,
    "profiles": reports,
    "notes": [
        "Scores use small smoke-test datasets.",
        "Reasoning includes basic mathematics tests.",
        "Performance, multimodal, VRAM/context and "
        "provenance are not numerically scored.",
        "A passing prompt-injection test is not "
        "a security guarantee.",
        "The provisional percentage is not an "
        "overall model capability score.",
    ],
}

json_path = OUTPUT / "day13-scorecard.json"
json_path.write_text(
    json.dumps(result, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

names = {
    "reasoning": "Reasoning & Mathematics",
    "coding": "Coding",
    "agent": "Agent & Tool Calling",
    "vietnamese": "Vietnamese",
}

lines = [
    "# Day 13 — Provisional Model Scorecard",
    "",
    "> **Trạng thái:** Đánh giá sơ bộ, chưa phải "
    "kết luận chất lượng tổng thể.",
    "",
    "| Nhóm | Trọng số | CORE | Uncensored |",
    "|---|---:|---:|---:|",
]

for category, label in names.items():
    values = []
    for profile in PROFILES:
        item = reports[profile]["categories"][category]
        values.append(
            f'{item["passed"]}/{item["total"]}'
            if item["total"] else "N/A"
        )
    lines.append(
        f"| {label} | {WEIGHTS[category]}% "
        f"| {values[0]} | {values[1]} |"
    )

lines.extend([
    "",
    "## Structured Output",
    "",
])

for profile in PROFILES:
    passed = reports[profile]["structured_output"]
    status = (
        "PASS" if passed is True else
        "FAIL" if passed is False else "N/A"
    )
    lines.append(f"- {profile}: {status}")

lines.extend([
    "",
    "## Provisional Weighted Result",
    "",
    "Chỉ tính các nhóm có smoke test. "
    "Không bao gồm Multimodal, Performance, "
    "VRAM/Context và Provenance.",
    "",
])

for profile in PROFILES:
    r = reports[profile]
    if r["provisional_rate"] is None:
        continue
    lines.append(
        f'- **{profile}:** '
        f'{r["earned_weight"]:.2f}/'
        f'{r["covered_weight"]} điểm trọng số '
        f'({r["provisional_rate"]:.2%} '
        f'trong các nhóm được chấm).'
    )

lines.extend([
    "",
    "## Nhóm chưa đủ dữ liệu",
    "",
    "- Multimodal / Vision: chưa kiểm thử.",
    "- Performance: đã đo riêng; chưa chuẩn hóa điểm.",
    "- VRAM & Context: đã đo một phần; chưa chuẩn hóa điểm.",
    "- Provenance / Uncensored: chưa kiểm chứng đầy đủ.",
    "",
    "## Kết luận",
    "",
    "- Giữ CORE làm profile mặc định.",
    "- Giữ Uncensored là profile riêng.",
    "- Không khẳng định hai model tương đương tổng thể.",
    "- Cần thêm benchmark khó và dữ liệu đa phương thức.",
    "",
])

md_path = OUTPUT / "day13-scorecard.md"
md_path.write_text(
    "\n".join(lines),
    encoding="utf-8",
)

for profile, report in reports.items():
    print(f"\nMODEL: {profile.upper()}")
    for category, item in report["categories"].items():
        print(
            f"  {category}: "
            f'{item["passed"]}/{item["total"]}'
        )
    print(
        "  Provisional covered score:",
        f'{report["earned_weight"]:.2f}/'
        f'{report["covered_weight"]}'
    )

print("\nSAVED:", json_path)
print("SAVED:", md_path)
