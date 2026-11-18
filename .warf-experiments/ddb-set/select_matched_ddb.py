"""Freeze the size-matched DuckDB set (README.md), before any Jev call: ../rdb-set/select_matched.py on DuckDB.

  defective  the 400 test defects of defects.jsonl (both judges said yes)
  clean      one control per defect from clean_matched.jsonl: defects in date order, each takes the free
             control in its own added-line bin with the nearest commit date (ties: nearest input size);
             if its bin is empty, the nearest non-empty bin

    python select_matched_ddb.py      # writes items.jsonl, select.log"""
import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "rdb-set"))
from build_clean_matched import EDGES, bin_of  # noqa: E402
sys.path.insert(0, str(HERE.parent / "kpx-set"))
from freeze import added  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s)


def day(s):
    return date.fromisoformat(s).toordinal()


rows = [json.loads(l) for l in (HERE / "defects.jsonl").open(encoding="utf-8")]
defects = sorted((r for r in rows if r["kind"] == "defective"), key=lambda r: r["date"])
free = [json.loads(l) for l in (HERE / "clean_matched.jsonl").open(encoding="utf-8")]
by_bin = {}
for c in free:
    by_bin.setdefault(bin_of(added(c["code"])), []).append(c)
pairs, moved = [], 0
for d in defects:
    k = bin_of(added(d["code"]))
    order = sorted((b for b in by_bin if by_bin[b]), key=lambda b: (abs(b - k), b))
    if not order:
        raise SystemExit("clean controls ran out")
    b = order[0]; moved += b != k
    best = min(by_bin[b], key=lambda c: (abs(day(c["date"]) - day(d["date"])),
                                         abs(math.log(len(c["code"])) - math.log(len(d["code"]))), c["base"]))
    by_bin[b].remove(best)
    pairs.append((d, best))

gap = sorted(abs(day(c["date"]) - day(d["date"])) for d, c in pairs)
say(f"{len(pairs)} defects matched; {moved} took a control from a neighbouring bin; date gap median {gap[len(gap) // 2]} days, max {gap[-1]}")
for k, xs in (("defective", [d for d, _ in pairs]), ("clean", [c for _, c in pairs])):
    say(f"  {k:<9} added lines median {statistics.median(added(x['code']) for x in xs):.0f}, "
        f"input chars median {statistics.median(len(x['code']) for x in xs):.0f}")
P = [added(d["code"]) for d, _ in pairs]; N = [added(c["code"]) for _, c in pairs]
say(f"  AUC of added lines (defective vs clean): {sum((a > b) + 0.5 * (a == b) for a in P for b in N) / (len(P) * len(N)):.3f}")
with (HERE / "items.jsonl").open("w", encoding="utf-8") as f:
    for d, c in pairs:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
        f.write(json.dumps({"id": c["base"] + ":clean", "base": c["base"], "kind": "clean", "answer": "APPROVE",
                            "commit": c["commit"], "date": c["date"], "file": c["file"], "domain": c["domain"],
                            "context": c["context"], "matched_to": d["base"], "code": c["code"]},
                           ensure_ascii=False) + "\n")
(HERE / "select.log").write_text("\n".join(out) + "\n", encoding="utf-8")
