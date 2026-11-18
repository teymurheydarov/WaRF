"""Mine PPSSPP's clean controls matched to the test defects' added-line counts (README.md). Git only.

../ddb-set/build_clean_ddb.py pointed at PPSSPP (build_pp.py's settings), with the test defects of
defects.jsonl, and no vendored or generated file (build_pp.excluded); not the commit of any candidate and not a fix commit.

    python build_clean_pp.py      # writes clean_matched.jsonl, build_matched.log"""
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_pp  # noqa: E402,F401  (points build_rdb at PPSSPP)
from build_pp import B, excluded  # noqa: E402
sys.path.insert(0, str(HERE.parent / "rdb-set"))
import build_clean_matched as M  # noqa: E402  (EDGES, bin_of, screen)
sys.path.insert(0, str(HERE.parent / "kpx-set"))
from freeze import added  # noqa: E402

log = []


def say(s=""):
    log.append(s); print(s, flush=True)


def main():
    defects = [json.loads(l) for l in (HERE / "defects.jsonl").open(encoding="utf-8")]
    need = [0] * len(M.EDGES)
    for d in defects:
        need[M.bin_of(added(d["code"]))] += 1
    target = [2 * n for n in need]
    say("test defects per added-line bin: " + ", ".join(f"{M.EDGES[k]}+:{need[k]}" for k in range(len(M.EDGES))))
    cands = {json.loads(l)["commit"] for l in (HERE / "candidates.jsonl").open(encoding="utf-8")}
    fixes = {h for h, s in (r.split("\t", 1) for r in B.git(B.GD, "log", B.REF, "--no-merges",
                                                            "--format=%H%x09%s").splitlines())
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
                and not excluded(m.group(2)) and M.bin_of(int(m.group(1))) is not None:
            pairs.append((*cur, m.group(2), int(m.group(1))))
    random.Random(20261118).shuffle(pairs)
    say(f"{len(pairs)} (commit, C++ file) pairs to draw from (file still present at {B.REF})")
    pool, have, used, screened = [], [0] * len(M.EDGES), set(), 0
    with ThreadPoolExecutor(8) as ex:
        i = 0
        while i < len(pairs) and any(h < t for h, t in zip(have, target)):
            chunk = []
            while i < len(pairs) and len(chunk) < 64:
                sha, date, subj, path, n = pairs[i]; i += 1
                approx = M.bin_of(n)
                if sha in used or all(have[k] >= target[k] for k in (approx, max(0, approx - 1))):
                    continue
                chunk.append((sha, date, subj, path))
            for r in ex.map(M.screen, chunk):
                screened += 1
                if r is None or r["commit"] in used:
                    continue
                k = M.bin_of(added(r["code"]))
                if k is not None and have[k] < target[k]:
                    pool.append(r); have[k] += 1; used.add(r["commit"])
            if screened % 512 < 64:
                say(f"  screened {screened} of {i} drawn; bins " + " ".join(f"{h}/{t}" for h, t in zip(have, target)))
    say(f"done: screened {screened}, kept {len(pool)}; bins "
        + " ".join(f"{M.EDGES[k]}+:{have[k]}/{target[k]}" for k in range(len(M.EDGES))))
    with (HERE / "clean_matched.jsonl").open("w", encoding="utf-8") as f:
        for r in pool:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (HERE / "build_matched.log").write_text("\n".join(log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
