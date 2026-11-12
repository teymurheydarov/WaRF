"""Mine the power-set candidates (README.md), with git only and no model calls.

  candidates.jsonl   defective candidates, as ../confirm-set/build_confirm.py, in two tiers: tier 1 the
                     confirm-set rules (fix within 180 days, at most 5 files, subject names a bug), tier 2
                     looser (365 days, at most 10 files, any subject). Each tier shuffled with a fixed seed,
                     tier 1 first. No commit of any earlier set, the confirm set's candidates and pool included.
  clean_pool.jsonl   clean controls, as build_confirm.py, excluding the same commits and every candidate.

    python .warf-experiments/power-set/build_power.py"""
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "evidence-set"))
sys.path.insert(0, str(EXP / "hard-set"))
from build_set import GISMO, git, prepare  # noqa: E402
from build_hard import survives  # noqa: E402

MAX_CHARS = 20000
N_DEFECT, N_CLEAN = 10 ** 6, 700
CPP = (".h", ".hpp", ".cpp", ".cc", ".cxx")
BUG = re.compile(r"\b(bugs?|bugfix(es)?|crash(es|ed|ing)?|segfaults?|leaks?|wrong|regressions?|defects?|"
                 r"faults?|faulty|incorrect(ly)?)\b|^fix", re.I)
GD = str(GISMO / ".git")
BASE = {"git_dir": GD, "worktree": str(GISMO)}


def used_commits() -> set:
    used = set()
    for path in [EXP / "laya-five" / "selection.jsonl", EXP / "evidence-set" / "candidates.jsonl",
                 EXP / "hard-set" / "candidates.jsonl", EXP / "real-set" / "candidates.jsonl",
                 EXP / "real-set" / "clean_pool.jsonl", EXP / "confirm-set" / "candidates.jsonl",
                 EXP / "confirm-set" / "clean_pool.jsonl"]:
        used |= {json.loads(line)["commit"] for line in path.open(encoding="utf-8")}
    return used


def defects(used: set) -> list:
    szz = {json.loads(line)["fix"]: json.loads(line) for line in (EXP / "laya-sweep" / "szz.jsonl").open(encoding="utf-8")}
    tiers = {1: [], 2: []}
    for r in map(json.loads, (EXP / "laya-sweep" / "labels.jsonl").open(encoding="utf-8")):
        if r["label"] != "REJECT" or "gismo6" not in r["repo"] or not r["file"].endswith(CPP) or r["commit"] in used:
            continue
        fx = [f for f in r["fixes"] if f["kind"] == "defect" and f["fix"] in szz]
        t1 = [f for f in fx if f["days"] <= 180 and BUG.search(szz[f["fix"]]["subject"]) and szz[f["fix"]]["files"] <= 5]
        t2 = [f for f in fx if f["days"] <= 365 and szz[f["fix"]]["files"] <= 10]
        if t1:
            tiers[1].append((r, min(t1, key=lambda f: f["days"])))
        elif t2:
            tiers[2].append((r, min(t2, key=lambda f: f["days"])))
    rng = random.Random(20261111)
    rng.shuffle(tiers[1]); rng.shuffle(tiers[2])
    rows = [(r, f, 1) for r, f in tiers[1]] + [(r, f, 2) for r, f in tiers[2]]
    out, seen = [], set()
    for r, fix, tier in rows:
        if len(out) == N_DEFECT:
            break
        if r["commit"] in seen:
            continue
        try:
            code, domain, context, enrich_error = prepare({**BASE, "sha": r["commit"]}, r["file"])
            fix_diff = git(GD, "show", "-U5", "--format=%H%n%ad%n%s%n%n%b", "--date=short", fix["fix"], "--", r["file"])
        except Exception:
            continue
        if len(code) > MAX_CHARS:
            continue
        seen.add(r["commit"])
        date, subject = git(GD, "show", "-s", "--format=%ad%x09%s", "--date=short", r["commit"]).strip().split("\t", 1)
        out.append({"base": f"{r['commit'][:7]}:{Path(r['file']).name}", "tier": tier, "commit": r["commit"], "date": date,
                    "subject": subject, "file": r["file"], "domain": domain, "context": context,
                    "enrich_error": enrich_error, "blamed_lines": r["lines"], "fix": fix["fix"], "fix_days": fix["days"],
                    "fix_subject": szz[fix["fix"]]["subject"], "fix_diff": fix_diff, "code": code})
    return out


def clean(used: set) -> list:
    commits = git(GD, "log", "origin/dev", "--no-merges", "--since=2014-01-01", "--until=2026-04-01",
                  "--format=%H%x09%ad%x09%s", "--date=short", "--", *[f"*{e}" for e in CPP]).splitlines()
    rng = random.Random(20261112)
    rng.shuffle(commits)
    out = []
    for row in commits:
        if len(out) == N_CLEAN:
            break
        sha, date, subject = row.split("\t", 2)
        if sha in used or subject.startswith(("Revert", "Merge")):
            continue
        files = [f for f in git(GD, "show", "--format=", "--name-only", "--diff-filter=AM", sha).split() if f.endswith(CPP)]
        rng.shuffle(files)
        for f in files:
            try:
                code, domain, context, enrich_error = prepare({**BASE, "sha": sha}, f)
            except Exception:
                continue
            if len(code) > MAX_CHARS or not any(ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip()
                                                for ln in code.splitlines()):
                continue
            if survives(sha, f, code):
                out.append({"base": f"{sha[:7]}:{Path(f).name}", "commit": sha, "date": date, "subject": subject,
                            "file": f, "domain": domain, "context": context, "enrich_error": enrich_error, "code": code})
                break
    return out


def main() -> None:
    used = used_commits()
    d = defects(used)
    c = clean(used | {x["commit"] for x in d})
    for name, rows in (("candidates.jsonl", d), ("clean_pool.jsonl", c)):
        with (HERE / name).open("w", encoding="utf-8") as out:
            for r in rows:
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"defective candidates {len(d)} (tier 1 {sum(x['tier'] == 1 for x in d)}, in src/ "
          f"{sum(x['file'].startswith('src/') for x in d)}), clean pool {len(c)}")


if __name__ == "__main__":
    main()
