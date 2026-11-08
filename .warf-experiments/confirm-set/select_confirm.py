"""Freeze the real-defect set from the judged candidates and the clean pool, before any reviewer runs.

  defective  candidates both judges say introduced the defect its later fix repairs (judgements.jsonl,
             introduced == "yes" from judge A and judge B); right answer REJECT
  clean      one control per defective item from clean_pool.jsonl (survival-screened), matched greedily
             by commit date and then by input size, each control used once; right answer APPROVE

    python .warf-experiments/real-set/select_real.py     # writes items.jsonl, disagreements.tsv, select.log"""
import json
import math
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
out_log = []


def say(s=""):
    out_log.append(s)
    print(s)


cands = [json.loads(line) for line in (HERE / "candidates.jsonl").open(encoding="utf-8")]
pool = [json.loads(line) for line in (HERE / "clean_pool.jsonl").open(encoding="utf-8")]
verdict = {}
for v in map(json.loads, (HERE / "judgements.jsonl").open(encoding="utf-8")):
    if (v["judge"], v["base"]) in verdict:
        raise SystemExit(f"two verdicts from judge {v['judge']} for {v['base']}")
    verdict[(v["judge"], v["base"])] = v

defective, disagree, rejected = [], [], 0
for c in cands:
    a, b = verdict[("A", c["base"])], verdict[("B", c["base"])]
    if a["introduced"] == b["introduced"] == "yes":
        defective.append((c, a, b))
    elif "yes" in (a["introduced"], b["introduced"]):
        disagree.append((c, a, b))
    else:
        rejected += 1
say(f"{len(cands)} candidates: both judges confirm {len(defective)}, disagree on {len(disagree)}, both reject {rejected}")


def day(s):
    return date.fromisoformat(s).toordinal()


free = list(pool)
pairs = []
for c, a, b in sorted(defective, key=lambda t: t[0]["date"]):
    best = min(free, key=lambda p: (abs(day(p["date"]) - day(c["date"])) // 180,
                                    abs(math.log(len(p["code"])) - math.log(len(c["code"]))), p["base"]))
    free.remove(best)
    pairs.append((c, a, b, best))
gap = sorted(abs(day(p["date"]) - day(c["date"])) for c, _, _, p in pairs)
say(f"clean controls: {len(pairs)}; date gap median {gap[len(gap) // 2]} days, max {gap[-1]}")
vis = {}
for _, a, b in defective:
    k = a["visible"] if a["visible"] == b["visible"] else "split"
    vis[k] = vis.get(k, 0) + 1
say("defect visibility (both judges): " + ", ".join(f"{k} {v}" for k, v in sorted(vis.items())))

with (HERE / "items.jsonl").open("w", encoding="utf-8") as out:
    for c, a, b, p in pairs:
        out.write(json.dumps({"id": c["base"] + ":defective", "base": c["base"], "kind": "defective", "answer": "REJECT",
                              "commit": c["commit"], "date": c["date"], "file": c["file"], "domain": c["domain"],
                              "context": c["context"], "fix": c["fix"], "fix_subject": c["fix_subject"],
                              "visible": a["visible"] if a["visible"] == b["visible"] else "split",
                              "defect": [a["defect"], b["defect"]], "code": c["code"]}, ensure_ascii=False) + "\n")
        out.write(json.dumps({"id": p["base"] + ":clean", "base": p["base"], "kind": "clean", "answer": "APPROVE",
                              "commit": p["commit"], "date": p["date"], "file": p["file"], "domain": p["domain"],
                              "context": p["context"], "matched_to": c["base"], "code": p["code"]},
                             ensure_ascii=False) + "\n")
with (HERE / "disagreements.tsv").open("w", encoding="utf-8") as out:
    out.write("base\tfix_subject\tA introduced\tB introduced\tA reason\tB reason\n")
    for c, a, b in disagree:
        out.write("\t".join([c["base"], c["fix_subject"], a["introduced"], b["introduced"],
                             a["reason"].replace("\t", " "), b["reason"].replace("\t", " ")]) + "\n")
(HERE / "select.log").write_text("\n".join(out_log) + "\n", encoding="utf-8")
