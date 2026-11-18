"""How many fresh RocksDB defect candidates exist after the first set's cutoff (git only, read-only, no model
calls): the rules of ../rdb-set/build_rdb.py, except that the introducing commit must be made on or after
2025-11-12 (the first set took only commits before it). Counts only; the WaRF input is not built here.

    python count_fresh.py      # prints the counts"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rdb-set"))
import build_rdb as B  # noqa: E402

fixes = [r.split("\t", 2) for r in B.git(B.GD, "log", B.REF, "--no-merges", "--since=2025-11-12",
                                          "--format=%H%x09%ad%x09%s", "--date=short").splitlines()]
all_after = len(fixes)
fixes = [(h, d, s) for h, d, s in fixes if B.BUG.search(s) and not s.startswith("Revert")]
last = B.git(B.GD, "log", "-1", "--format=%ad", "--date=short", B.REF).strip()
print(f"commits on {B.REF} since 2025-11-12: {all_after} (last {last}); fix commits among them: {len(fixes)}")
seen, n = set(), 0
for fix, fdate, fsubj in fixes:
    files = B.git(B.GD, "show", "--format=", "--name-only", fix).split()
    if len(files) > 5:
        continue
    for path in [f for f in files if f.endswith(B.CPP)]:
        try:
            hits = B.blamed(fix, path)
        except RuntimeError:
            continue
        for sha in sorted(hits, key=lambda s: -len(hits[s])):
            if sha in seen:
                continue
            cdate, csubj = B.info(sha)
            days = B.day(fdate) - B.day(cdate)
            if not 0 <= days <= 180 or cdate < B.CUTOFF or csubj.startswith(("Revert", "Merge")) or B.is_merge(sha):
                continue
            seen.add(sha); n += 1
            break
print(f"fresh defect candidates (before the input-size limit): {n}")
