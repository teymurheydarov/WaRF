"""Token cost analysis across all logged WaRF sessions."""
import json
import sys
from pathlib import Path
from collections import defaultdict

# A dev tool, not part of the package: make the checkout importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from warf.paths import sessions_path as _resolve_sessions  # noqa: E402

sessions_path = _resolve_sessions()

sessions = []
with open(sessions_path, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            sessions.append(json.loads(line))

# Separate debate sessions (double-round) from single-round
debate_sessions = [s for s in sessions if s.get("debate")]
regular_sessions = [s for s in sessions if not s.get("debate")]

# For each regular session collect metrics
records = []
for s in regular_sessions:
    agents_queried = len(s["votes"])
    tokens = s["total_tokens_in"] + s["total_tokens_out"]
    five_agent = any(
        v["agent"] in ("TEST-FOCUSED", "BOUNDARY") for v in s["votes"]
    )
    records.append({
        "artifact": Path(s["artifact"]).name,
        "domain": s["domain"],
        "agents": agents_queried,
        "tokens": tokens,
        "sprt_fired": s.get("sprt_fired", False),
        "decision": s["decision"],
        "confidence": s["confidence"],
        "five_agent_pool": five_agent,
    })

print("=" * 60)
print("WaRF Token Cost Analysis")
print("=" * 60)

# ── Per-session table ────────────────────────────────────────
print(f"\n{'File':<30} {'Domain':<12} {'k':>2} {'Tokens':>7} {'SPRT':>5} {'Verdict'}")
print("-" * 70)
for r in records:
    sprt_mark = "YES" if r["sprt_fired"] else "-"
    pool_mark = "*" if r["five_agent_pool"] else " "
    print(
        f"{pool_mark}{r['artifact']:<29} {r['domain']:<12} {r['agents']:>2}"
        f" {r['tokens']:>7} {sprt_mark:>5}  {r['decision']} [{r['confidence']}]"
    )
print("* = 5-agent pool session")

# ── Group by pool size ───────────────────────────────────────
three_agent = [r for r in records if not r["five_agent_pool"]]
five_agent   = [r for r in records if r["five_agent_pool"]]
five_early   = [r for r in five_agent if r["sprt_fired"]]
five_full    = [r for r in five_agent if not r["sprt_fired"]]

def avg(lst):
    lst = list(lst)
    return sum(lst) / len(lst) if lst else 0

print(f"\n{'=' * 60}")
print("Summary by pool configuration")
print(f"{'=' * 60}")

print(f"\n3-agent pool ({len(three_agent)} sessions)")
if three_agent:
    print(f"  Avg tokens : {avg(r['tokens'] for r in three_agent):.0f}")
    print(f"  SPRT fired : never (boundary unreachable for REJECT at n=3)")

print(f"\n5-agent pool — pool exhausted ({len(five_full)} sessions)")
if five_full:
    print(f"  Avg tokens : {avg(r['tokens'] for r in five_full):.0f}")
    print(f"  Confidence : {', '.join(r['confidence'] for r in five_full)}")

print(f"\n5-agent pool — SPRT early stop ({len(five_early)} sessions)")
if five_early:
    avg_early = avg(r['tokens'] for r in five_early)
    print(f"  Avg tokens : {avg_early:.0f}")
    print(f"  Agents used: {', '.join(str(r['agents']) for r in five_early)} of 5")
    print(f"  Confidence : {', '.join(r['confidence'] for r in five_early)}")
    if five_full:
        avg_full = avg(r['tokens'] for r in five_full)
        saving = (avg_full - avg_early) / avg_full * 100
        print(f"  Token saving vs full pool: {saving:.0f}%")

if debate_sessions:
    print(f"\nDebate sessions ({len(debate_sessions)} — excluded from pool analysis)")
    for s in debate_sessions:
        r1 = s["total_tokens_in"] + s["total_tokens_out"]
        d  = s["debate"]
        r2 = sum(v["tokens_in"] + v["tokens_out"] for v in d["votes"])
        print(f"  {Path(s['artifact']).name:<28}  R1={r1} R2={r2} total={r1+r2}")
