"""Mine DuckDB's defect candidates (README.md), with git only and no model calls.

../rdb-set/build_rdb.py's defects() with its helpers, pointed at DuckDB, with three changes fixed in the
README before mining: the cutoff 2025-11-14 (one year before the clone), up to 1,100 candidates, and no file
under third_party/ (vendored code is fixed upstream). The same fix rule, blame, 180-day window, one file per
commit, input limit and seeded order (the seed is RocksDB's).

    python build_ddb.py      # writes candidates.jsonl, build.log"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "rdb-set"))
import build_rdb as B  # noqa: E402

B.REPO = Path(r"C:\workdir\warf\repos\duckdb")
B.GD = str(B.REPO / ".git")
B.BASE = {"git_dir": B.GD, "worktree": str(B.REPO)}
B.CUTOFF, B.N_DEFECT = "2025-11-14", 1100
VENDORED = "third_party/"


def defects(sink=None):
    """The candidates in mining order; each is also written to `sink` (a text file) as soon as it is found."""
    git, GD, REF = B.git, B.GD, B.REF
    fixes = [r.split("\t", 2) for r in git(GD, "log", REF, "--no-merges", "--format=%H%x09%ad%x09%s",
                                           "--date=short").splitlines()]
    fixes = [(h, d, s) for h, d, s in fixes if B.BUG.search(s) and not s.startswith("Revert")]
    reverted = set(B.re.findall(r"This reverts commit ([0-9a-f]{40})", git(GD, "log", REF, "--format=%B")))
    rng = random.Random(20261116)
    rng.shuffle(fixes)
    B.say(f"{len(fixes)} fix commits on {REF}")
    out, seen, visited = [], set(), 0
    for fix, fdate, fsubj in fixes:
        if len(out) >= B.N_DEFECT:
            break
        visited += 1
        files = git(GD, "show", "--format=", "--name-only", fix).split()
        if len(files) > 5 or fix in reverted:
            continue
        for path in [f for f in files if f.endswith(B.CPP) and not f.startswith(VENDORED)]:
            try:
                hits = B.blamed(fix, path)
            except RuntimeError:
                continue                              # added by the fix, or renamed
            for sha, lines in sorted(hits.items(), key=lambda kv: -len(kv[1])):
                if sha in seen or sha in reverted:
                    continue
                cdate, csubj = B.info(sha)
                days = B.day(fdate) - B.day(cdate)
                if (not 0 <= days <= 180 or cdate >= B.CUTOFF or csubj.startswith(("Revert", "Merge"))
                        or B.is_merge(sha)):
                    continue
                try:
                    code, domain, context, enrich_error = B.prepare({**B.BASE, "sha": sha}, path)
                except Exception:                     # noqa: BLE001  (the file is not in that commit's diff)
                    continue
                if len(code) > B.MAX_CHARS:
                    continue
                seen.add(sha)
                out.append({"base": f"{sha[:7]}:{Path(path).name}", "commit": sha, "date": cdate, "subject": csubj,
                            "file": path, "domain": domain, "context": context, "enrich_error": enrich_error,
                            "blamed_lines": lines, "fix": fix, "fix_days": days, "fix_subject": fsubj,
                            "fix_diff": git(GD, "show", "-U5", "--format=%H%n%ad%n%s%n%n%b", "--date=short",
                                            fix, "--", path),
                            "code": code})
                if sink is not None:
                    sink.write(json.dumps(out[-1], ensure_ascii=False) + "\n"); sink.flush()
                if len(out) % 50 == 0:
                    B.say(f"  {len(out)} candidates after {visited} fixes")
                break                                 # one candidate per fix file is enough
    B.say(f"defective candidates {len(out)} from {visited} fixes visited")
    return out, {h for h, _, _ in fixes}


def main():
    # Amendment 2026-11-14 (README): up to 1,600 candidates, each written to candidates_stream.jsonl when found.
    if len(sys.argv) > 1:
        B.N_DEFECT = int(sys.argv[1])
    with (HERE / "candidates_stream.jsonl").open("w", encoding="utf-8") as sink:
        d, fix_shas = defects(sink)
    with (HERE / "candidates.jsonl").open("w", encoding="utf-8") as f:
        for r in d:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (HERE / "fix_commits.txt").write_text("\n".join(sorted(fix_shas)) + "\n", encoding="utf-8")
    (HERE / "build.log").write_text("\n".join(B.log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
