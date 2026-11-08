"""Freeze the hard set from build_hard.py's candidates and the two judges' verdicts (judgements.jsonl;
judge A and judge B are Claude agents that read the code at each commit with read-only git).

A plant is kept when both judges say it compiles and is a real defect. Kept candidates, in
build_hard.py's seeded order, are split before any reviewer sees them:

  pilot     the first N_PILOT kept bases: pilot/items.jsonl, used only to check that the plants are hard
            enough (README.md, stage gate)
  test      the next up to N_TEST kept bases: items.jsonl, reviewed once by the preregistered arms

Each base gives two items, clean (APPROVE) and planted (REJECT). Disagreements go to
disagreements.tsv for a person; agreed rejections are dropped.

    python .warf-experiments/hard-set/select_hard.py     # writes pilot/items.jsonl, items.jsonl, disagreements.tsv, select.log"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
N_PILOT, N_TEST = 20, 50
out_log = []


def say(s=""):
    out_log.append(s)
    print(s)


cands = [json.loads(line) for line in (HERE / "candidates.jsonl").open(encoding="utf-8")]
verdict = {}
for v in map(json.loads, (HERE / "judgements.jsonl").open(encoding="utf-8")):
    if (v["judge"], v["base"]) in verdict:
        raise SystemExit(f"two verdicts from judge {v['judge']} for {v['base']}")
    verdict[(v["judge"], v["base"])] = v


def good(v):
    return v["compiles"] == "yes" and v["defect"] == "real"


kept, disagree, rejected = [], [], 0
for c in cands:
    a, b = verdict[("A", c["base"])], verdict[("B", c["base"])]
    if good(a) and good(b):
        kept.append((c, a, b))
    elif good(a) or good(b):
        disagree.append((c, a, b))
    else:
        rejected += 1
pilot, test = kept[:N_PILOT], kept[N_PILOT:N_PILOT + N_TEST]
say(f"{len(cands)} candidates: both judges keep {len(kept)}, disagree on {len(disagree)}, both reject {rejected}")
for name, part in (("pilot", pilot), ("test", test)):
    ops = {}
    for c, _, _ in part:
        ops[c["operator"]] = ops.get(c["operator"], 0) + 1
    say(f"{name}: {len(part)} bases; " + ", ".join(f"{k} {v}" for k, v in sorted(ops.items()))
        + f"; visible from the diff (both judges): {sum(a['visible'] == b['visible'] == 'diff' for _, a, b in part)}")


def write(path, part):
    with path.open("w", encoding="utf-8") as out:
        for c, a, b in part:
            common = {k: c[k] for k in ("base", "commit", "date", "subject", "file", "domain", "context", "operator")}
            out.write(json.dumps({**common, "id": c["base"] + ":clean", "kind": "clean", "answer": "APPROVE",
                                  "code": c["code_clean"]}, ensure_ascii=False) + "\n")
            out.write(json.dumps({**common, "id": c["base"] + ":planted", "kind": "planted", "answer": "REJECT",
                                  "original": c["original"], "mutated": c["mutated"],
                                  "visible": a["visible"] if a["visible"] == b["visible"] else "unsure",
                                  "judge_reasons": [a["reason"], b["reason"]], "code": c["code_planted"]},
                                 ensure_ascii=False) + "\n")


(HERE / "pilot").mkdir(exist_ok=True)
write(HERE / "pilot" / "items.jsonl", pilot)
write(HERE / "items.jsonl", test)
with (HERE / "disagreements.tsv").open("w", encoding="utf-8") as out:
    out.write("base\toperator\toriginal\tmutated\tA compiles/defect\tB compiles/defect\tA reason\tB reason\n")
    for c, a, b in disagree:
        out.write("\t".join([c["base"], c["operator"], c["original"].strip(), (c["mutated"] or "").strip(),
                             f"{a['compiles']}/{a['defect']}", f"{b['compiles']}/{b['defect']}",
                             a["reason"].replace("\t", " "), b["reason"].replace("\t", " ")]) + "\n")
(HERE / "select.log").write_text("\n".join(out_log) + "\n", encoding="utf-8")
