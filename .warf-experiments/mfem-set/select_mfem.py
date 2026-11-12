"""Freeze the MFEM set (README.md) from the judged candidates and the clean pool, before any Jev call.

  defective  candidates both judges say introduced the defect its later fix repairs (judgements/*.jsonl,
             introduced == "yes" from judge A and judge B), the first TARGET of them in candidate-list
             order; right answer REJECT
  clean      one control per defective item from clean_pool.jsonl, matched greedily by commit date and
             then by input size, each control used once (as ../confirm-set/select_confirm.py); APPROVE

    python .warf-experiments/mfem-set/select_mfem.py     # writes items.jsonl, disagreements.tsv, select.log"""
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
TARGET = 150
verdict = {}
for v in (json.loads(l) for f in sorted((HERE / "judgements").glob("*.jsonl")) for l in f.open(encoding="utf-8") if l.strip()):
    if (v["judge"], v["base"]) in verdict:
        raise SystemExit(f"two verdicts from judge {v['judge']} for {v['base']}")
    verdict[(v["judge"], v["base"])] = v

defective, disagree, rejected = [], [], 0
unjudged = beyond = 0
for c in cands:
    if ("A", c["base"]) not in verdict:
        unjudged += 1
        continue
    a = verdict[("A", c["base"])]
    b = verdict.get(("B", c["base"]), {"introduced": "not asked", "reason": "A did not say yes", "visible": ""})
    if a["introduced"] == "yes" and ("B", c["base"]) not in verdict:
        raise SystemExit(f"{c['base']}: A said yes but B has not judged it")
    if a["introduced"] == b["introduced"] == "yes" and len(defective) >= TARGET:
        beyond += 1
    elif a["introduced"] == b["introduced"] == "yes":
        defective.append((c, a, b))
    elif "yes" in (a["introduced"], b["introduced"]):
        disagree.append((c, a, b))
    else:
        rejected += 1
say(f"{len(cands)} candidates ({unjudged} never judged): kept {len(defective)} confirmed by both judges "
    f"({beyond} more confirmed beyond the target of {TARGET}), disagree on {len(disagree)}, rejected {rejected}")


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
