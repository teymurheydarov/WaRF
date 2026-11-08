"""Build a set of REAL G+Smo defects with their fixes, the plan's set R (docs/spec/evidence-seats-test-plan.md):
the test where a lenient reviewer can lose recall, which planted defects could not provide (../hard-set/).

Defective candidates come from the Laya sweep's git-history mining (../laya-sweep/labels.jsonl, szz.jsonl):
  * a change to a C++ file under src/ in the gismo6 clone, blamed (B-SZZ) by a later fix commit;
  * that fix is of kind "defect", comes within 60 days, touches at most 3 files, and its subject names
    a bug (label_laya_sweep.py's BUG_WORDS, or starts with "fix");
  * one file per inducing commit; commits already reviewed in ../laya-five (= ../four-arms),
    ../evidence-set and ../hard-set are excluded; the reviewer's input is at most MAX_CHARS.
The reviewer's input is built exactly as WaRF's review path builds it (../laya-five/run_five.py prepare,
at the inducing commit). The fix's diff of that file is stored for the judges only; no reviewer sees it.
Whether the fix really repairs a defect this change introduced is decided by two judges (check_real.js
workflow) before any reviewer runs.

    python .warf-experiments/real-set/build_real.py     # writes candidates.jsonl and build.log"""
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "evidence-set"))
from build_set import GISMO, git, prepare  # noqa: E402

MAX_CHARS = 20000
N_CANDIDATES = 150
BUG = re.compile(r"\b(bugs?|bugfix(es)?|crash(es|ed|ing)?|segfaults?|leaks?|wrong|regressions?|defects?|"
                 r"faults?|faulty|incorrect(ly)?)\b|^fix", re.I)
out_log = []


def say(s=""):
    out_log.append(s)
    print(s)


def main() -> None:
    szz = {json.loads(line)["fix"]: json.loads(line) for line in (EXP / "laya-sweep" / "szz.jsonl").open(encoding="utf-8")}
    used = set()
    for path, key in ((EXP / "laya-five" / "selection.jsonl", "commit"), (EXP / "evidence-set" / "candidates.jsonl", "commit"),
                      (EXP / "hard-set" / "candidates.jsonl", "commit")):
        used |= {json.loads(line)[key] for line in path.open(encoding="utf-8")}
    rows = []
    for r in map(json.loads, (EXP / "laya-sweep" / "labels.jsonl").open(encoding="utf-8")):
        if not (r["label"] == "REJECT" and "gismo6" in r["repo"] and r["file"].startswith("src/")
                and r["file"].endswith((".h", ".hpp", ".cpp")) and r["commit"] not in used):
            continue
        fixes = [f for f in r["fixes"] if f["kind"] == "defect" and f["days"] <= 60 and f["fix"] in szz
                 and BUG.search(szz[f["fix"]]["subject"]) and szz[f["fix"]]["files"] <= 3]
        if fixes:
            rows.append((r, min(fixes, key=lambda f: f["days"])))
    say(f"{len(rows)} commit-files qualify, {len({r['commit'] for r, _ in rows})} distinct commits")
    rng = random.Random(20261105)
    rng.shuffle(rows)
    base = {"git_dir": str(GISMO / ".git"), "worktree": str(GISMO)}
    picked, seen, skipped = [], set(), {"same commit": 0, "too long": 0, "error": 0}
    for r, fix in rows:
        if len(picked) == N_CANDIDATES:
            break
        if r["commit"] in seen:
            skipped["same commit"] += 1
            continue
        try:
            code, domain, context, enrich_error = prepare({**base, "sha": r["commit"]}, r["file"])
            fix_diff = git(str(GISMO / ".git"), "show", "-U5", "--format=%H%n%ad%n%s%n%n%b", "--date=short",
                           fix["fix"], "--", r["file"])
        except Exception:
            skipped["error"] += 1
            continue
        if len(code) > MAX_CHARS:
            skipped["too long"] += 1
            continue
        seen.add(r["commit"])
        date, subject = git(str(GISMO / ".git"), "show", "-s", "--format=%ad%x09%s", "--date=short", r["commit"]).strip().split("\t", 1)
        picked.append({"base": f"{r['commit'][:7]}:{Path(r['file']).name}", "commit": r["commit"], "date": date,
                       "subject": subject, "file": r["file"], "domain": domain, "context": context,
                       "enrich_error": enrich_error, "blamed_lines": r["lines"], "fix": fix["fix"],
                       "fix_days": fix["days"], "fix_subject": szz[fix["fix"]]["subject"], "fix_diff": fix_diff,
                       "code": code})
    with (HERE / "candidates.jsonl").open("w", encoding="utf-8") as out:
        for p in picked:
            out.write(json.dumps(p, ensure_ascii=False) + "\n")
    years = {}
    for p in picked:
        years[p["date"][:4]] = years.get(p["date"][:4], 0) + 1
    say(f"candidates: {len(picked)}; skipped: " + ", ".join(f"{k} {v}" for k, v in skipped.items()))
    say("years: " + ", ".join(f"{y} {n}" for y, n in sorted(years.items())))
    (HERE / "build.log").write_text("\n".join(out_log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
