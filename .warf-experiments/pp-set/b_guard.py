"""Before a B batch: are the first N unqueued A-yes verdicts all from finished A batches (first K files)?
    python b_guard.py K N"""
import sys
import judge
K, N = int(sys.argv[1]), int(sys.argv[2])
cs, v, qb = judge.cands(), judge.verdicts(), judge.queued("B")
done = set()
for k in range(K):
    done |= {l[9:].strip() for l in (judge.INP / f"A_{k:02d}.md").open(encoding="utf-8") if l.startswith("## base: ")}
todo = [c["base"] for c in cs if v.get(("A", c["base"]), {}).get("introduced") == "yes" and c["base"] not in qb]
print(len(todo), "unqueued A-yes; the first", N, "from finished batches:", all(b in done for b in todo[:N]))
