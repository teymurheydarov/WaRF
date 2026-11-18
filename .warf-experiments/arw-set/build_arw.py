"""Mine Arrow's defect candidates (README.md), with git only and no model calls.

../ddb-set/build_ddb.py pointed at Arrow: ../rdb-set/build_rdb.py's rules and helpers, cutoff 2025-11-16 (one year
before the clone), up to 1,600 candidates, each written to candidates_stream.jsonl as it is found, and no
vendored or generated code (cpp/thirdparty/, any path containing /vendored/ or /generated/). The same seed.
Amended 2026-11-16 before any judging (README.md "Amendment"): the subject rule is applied to the subject after
Arrow's issue key and component tags ("GH-123: [C++][Parquet] "), since its "^fix" alternative never matches
otherwise (552 fix commits with the prefix, 2,870 without).

    python build_arw.py      # writes candidates_stream.jsonl, then candidates.jsonl, fix_commits.txt, build.log"""
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "rdb-set"))
import build_rdb as B  # noqa: E402

B.REPO = Path(r"C:\workdir\warf\repos\arrow")
B.GD = str(B.REPO / ".git")
B.BASE = {"git_dir": B.GD, "worktree": str(B.REPO)}
B.CUTOFF, B.N_DEFECT = "2025-11-16", 1600


PREFIX = B.re.compile(r"^((GH|ARROW|PARQUET|MINOR)(-\d+)?\s*:\s*)?(\[[^\]]*\]\s*)*", B.re.I)


def subject(s):
    """The subject without Arrow's issue key and component tags."""
    return PREFIX.sub("", s, count=1)


def excluded(path):
    """Vendored or generated code: fixed upstream or by its generator, not by a change to it."""
    return path.startswith("cpp/thirdparty/") or "/vendored/" in path or "/generated/" in path


def defects(sink):
    git, GD, REF = B.git, B.GD, B.REF
    fixes = [r.split("\t", 2) for r in git(GD, "log", REF, "--no-merges", "--format=%H%x09%ad%x09%s",
                                           "--date=short").splitlines()]
    fixes = [(h, d, s) for h, d, s in fixes if B.BUG.search(subject(s)) and not s.startswith("Revert")]
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
        for path in [f for f in files if f.endswith(B.CPP) and not excluded(f)]:
            try:
                hits = B.blamed(fix, path)
            except RuntimeError:
                continue
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
                sink.write(json.dumps(out[-1], ensure_ascii=False) + "\n"); sink.flush()
                if len(out) % 50 == 0:
                    B.say(f"  {len(out)} candidates after {visited} fixes")
                break
    B.say(f"defective candidates {len(out)} from {visited} fixes visited")
    return out, {h for h, _, _ in fixes}


def main():
    with (HERE / "candidates_stream.jsonl").open("w", encoding="utf-8") as sink:
        d, fix_shas = defects(sink)
    with (HERE / "candidates.jsonl").open("w", encoding="utf-8") as f:
        for r in d:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (HERE / "fix_commits.txt").write_text("\n".join(sorted(fix_shas)) + "\n", encoding="utf-8")
    (HERE / "build.log").write_text("\n".join(B.log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
