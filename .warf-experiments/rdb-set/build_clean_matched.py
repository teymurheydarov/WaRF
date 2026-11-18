"""Mine clean controls matched to the defects' added-line counts (README.md, Amendment 2026-11-13). Git only.

    python build_clean_matched.py      # writes clean_matched.jsonl, build_matched.log"""
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_rdb as B  # noqa: E402  (git, prepare, survives, BUG, CPP, CUTOFF, MAX_CHARS, GD, REF, BASE)
sys.path.insert(0, str(HERE.parent / "kpx-set"))
from freeze import added  # noqa: E402

EDGES = [1, 2, 3, 4, 6, 9, 13, 19, 28, 41, 61, 91, 136, 201]          # bin k holds edges[k] <= n < edges[k+1]
log = []


def say(s=""):
    log.append(s); print(s, flush=True)


def bin_of(n):
    return max(k for k, e in enumerate(EDGES) if n >= e) if n >= 1 else None


def added_lines(sha, path):
    diff = B.git(B.GD, "show", "--format=", "-U0", "--no-color", sha, "--", path)
    return [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip()]


def screen(pair):
    """The original survival screen, run cheaply first, then on WaRF's input as build_rdb did."""
    sha, date, subj, path = pair
    try:
        lines = added_lines(sha, path)
        if not lines:
            return None
        blame = B.git(B.GD, "blame", "-l", "-s", B.REF, "--", path)
        remaining = [row.split(") ", 1)[1] for row in blame.splitlines() if row.startswith(sha) and ") " in row]
        for ln in lines:
            if ln in remaining:
                remaining.remove(ln)
            else:
                return None
        code, domain, context, enrich_error = B.prepare({**B.BASE, "sha": sha}, path)
    except Exception:
        return None
    if len(code) > B.MAX_CHARS or not B.survives(sha, path, code):
        return None
    return {"base": f"{sha[:7]}:{Path(path).name}", "commit": sha, "date": date, "subject": subj, "file": path,
            "domain": domain, "context": context, "enrich_error": enrich_error, "code": code}


def main():
    defects = [json.loads(l) for l in (HERE / "items_unmatched.jsonl").open(encoding="utf-8")]
    defects = [d for d in defects if d["kind"] == "defective"]
    need = [0] * len(EDGES)
    for d in defects:
        need[bin_of(added(d["code"]))] += 1
    target = [2 * n for n in need]
    say("defects per added-line bin: " + ", ".join(f"{EDGES[k]}+:{need[k]}" for k in range(len(EDGES))))

    cands = {json.loads(l)["commit"] for l in (HERE / "candidates.jsonl").open(encoding="utf-8")}
    fixes = {h for h, s in (r.split("\t", 1) for r in B.git(B.GD, "log", B.REF, "--no-merges", "--format=%H%x09%s").splitlines())
             if B.BUG.search(s) and not s.startswith("Revert")}
    at_head = set(B.git(B.GD, "ls-tree", "-r", "--name-only", B.REF).splitlines())
    raw = B.git(B.GD, "log", B.REF, "--no-merges", f"--until={B.CUTOFF}", "--numstat", "--date=short",
                "--format=@%H%x09%ad%x09%s", "--", *[f"*{e}" for e in B.CPP])
    pairs, cur = [], None
    for ln in raw.splitlines():
        if ln.startswith("@"):
            sha, date, subj = ln[1:].split("\t", 2)
            cur = None if (sha in cands or sha in fixes or subj.startswith(("Revert", "Merge"))) else (sha, date, subj)
            continue
        m = re.match(r"(\d+)\t\d+\t(.+)$", ln)
        if cur and m and "=>" not in m.group(2) and m.group(2).endswith(B.CPP) and m.group(2) in at_head \
                and bin_of(int(m.group(1))) is not None:
            pairs.append((*cur, m.group(2), int(m.group(1))))
    random.Random(20261118).shuffle(pairs)
    say(f"{len(pairs)} (commit, C++ file) pairs to draw from (file still present at {B.REF})")

    pool, have, used, screened = [], [0] * len(EDGES), set(), 0
    with ThreadPoolExecutor(8) as ex:
        i = 0
        while i < len(pairs) and any(h < t for h, t in zip(have, target)):
            chunk = []
            while i < len(pairs) and len(chunk) < 64:
                sha, date, subj, path, n = pairs[i]; i += 1
                approx = bin_of(n)
                # numstat counts blank lines too: also try pairs one bin above a needed bin
                if sha in used or all(have[k] >= target[k] for k in (approx, max(0, approx - 1))):
                    continue
                chunk.append((sha, date, subj, path))
            for r in ex.map(screen, chunk):
                screened += 1
                if r is None or r["commit"] in used:
                    continue
                k = bin_of(added(r["code"]))
                if k is not None and have[k] < target[k]:
                    pool.append(r); have[k] += 1; used.add(r["commit"])
            if screened % 512 < 64:
                say(f"  screened {screened} of {i} drawn; bins " + " ".join(f"{h}/{t}" for h, t in zip(have, target)))
    say(f"done: screened {screened}, kept {len(pool)}; bins " + " ".join(f"{EDGES[k]}+:{have[k]}/{target[k]}" for k in range(len(EDGES))))
    with (HERE / "clean_matched.jsonl").open("w", encoding="utf-8") as f:
        for r in pool:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (HERE / "build_matched.log").write_text("\n".join(log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
