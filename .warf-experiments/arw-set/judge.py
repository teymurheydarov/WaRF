"""Judge batches for the Arrow set (README.md, judge_prompt.md): ../rdb-set/judge.py with TARGET 440. No model calls.

    python judge.py next A 400      # write judge A's next 400 unjudged candidates (in list order) as batches
    python judge.py next B          # write every candidate A called "yes" that B has not judged yet
    python judge.py status          # counts; judging stops once 440 are confirmed (40 history + 400 test)

Batches go to judge_inputs/<judge>_<k>.md (40 candidates each); a judge agent answers a batch into
judgements/<judge>_<k>.jsonl. B never sees A's verdict: its batches hold the same fields as A's."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BATCH, TARGET, FIX_CAP = 40, 440, 8000
INP, OUT = HERE / "judge_inputs", HERE / "judgements"


def cands():
    """
    The candidate list. While build_arw.py still mines it: the longer of candidates_stream.jsonl (build_arw.py,
    written as found) and candidates_prefix.jsonl (build_prefix.py), after checking that the shorter one is the
    start of the longer one (both come from the same rules and seeded order).
    """
    if (HERE / "candidates.jsonl").exists():
        return [json.loads(l) for l in (HERE / "candidates.jsonl").open(encoding="utf-8")]
    lists = [[json.loads(l) for l in (HERE / name).open(encoding="utf-8")]
             for name in ("candidates_stream.jsonl", "candidates_prefix.jsonl") if (HERE / name).exists()]
    lists.sort(key=len)
    if len(lists) == 2 and lists[1][:len(lists[0])] != lists[0]:
        raise SystemExit("candidates_stream.jsonl and candidates_prefix.jsonl disagree: mining is not deterministic")
    return lists[-1]


def verdicts():
    """All verdicts so far. A line that is not valid JSON (a judge still writing its file) is skipped with a
    warning here; select_defects.py, which freezes the set, refuses it."""
    v = {}
    for f in sorted(OUT.glob("*.jsonl")) if OUT.exists() else []:
        for k, l in enumerate(f.open(encoding="utf-8")):
            if l.strip():
                try:
                    r = json.loads(l)
                except json.JSONDecodeError:
                    print(f"  warning: {f.name} line {k + 1} is not valid JSON yet; skipped", file=sys.stderr)
                    continue
                if (r["judge"], r["base"]) in v:
                    raise SystemExit(f"two verdicts from {r['judge']} for {r['base']}")
                v[(r["judge"], r["base"])] = r
    return v


def queued(judge):
    q = set()
    for f in INP.glob(f"{judge}_*.md") if INP.exists() else []:
        q |= {l[len("## base: "):].strip() for l in f.open(encoding="utf-8") if l.startswith("## base: ")}
    return q


def block(c):
    fix = c["fix_diff"] if len(c["fix_diff"]) <= FIX_CAP else c["fix_diff"][:FIX_CAP] + "\n[... fix diff cut ...]"
    return (f"## base: {c['base']}\n\ncommit {c['commit']} ({c['date']}): {c['subject']}\nfile: {c['file']}\n\n"
            f"### The change\n```\n{c['code']}\n```\n\n### The later fix ({c['fix']}, {c['fix_days']} days later): "
            f"{c['fix_subject']}\n```\n{fix}\n```\n")


def write(judge, todo):
    INP.mkdir(exist_ok=True)
    k0 = len(list(INP.glob(f"{judge}_*.md")))
    names = []
    for j in range(0, len(todo), BATCH):
        name = f"{judge}_{k0 + j // BATCH:02d}"
        part = todo[j:j + BATCH]
        (INP / f"{name}.md").write_text(f"# Judge {judge}, batch {name}: {len(part)} candidates\n\n"
                                        + "\n\n".join(block(c) for c in part), encoding="utf-8")
        names.append(f"{name} ({len(part)})")
    print(f"judge {judge}: {len(todo)} candidates in batches " + ", ".join(names))


def main():
    cmd = sys.argv[1]
    cs, v = cands(), verdicts()
    if cmd == "next":
        judge = sys.argv[2]
        q = queued(judge)
        if judge == "A":
            todo = [c for c in cs if c["base"] not in q][:int(sys.argv[3])]
        else:
            todo = [c for c in cs if v.get(("A", c["base"]), {}).get("introduced") == "yes" and c["base"] not in q]
            if len(sys.argv) > 3:                     # at most this many, in list order
                todo = todo[:int(sys.argv[3])]
        write(judge, todo)
    elif cmd == "status":
        a = sum(("A", c["base"]) in v for c in cs)
        ay = [c for c in cs if v.get(("A", c["base"]), {}).get("introduced") == "yes"]
        b = sum(("B", c["base"]) in v for c in ay)
        both = [c for c in ay if v.get(("B", c["base"]), {}).get("introduced") == "yes"]
        missing = {j: len(queued(j)) - sum(1 for (jj, _) in v if jj == j) for j in "AB"}
        print(f"{len(cs)} candidates; A judged {a}, yes {len(ay)}; B judged {b} of those, both yes {len(both)} "
              f"(target {TARGET}); queued but unanswered A {missing['A']}, B {missing['B']}")


if __name__ == "__main__":
    main()
