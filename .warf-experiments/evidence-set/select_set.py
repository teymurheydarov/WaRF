"""Freeze the small evidence-seat answer key from build_set.py's candidates and the two independent
judges' verdicts in judgements.jsonl (judge A and judge B, Claude agents that read the code at each
commit with read-only git; they did not review the changes for any arm).

A plant is kept when both judges say it compiles and is a real defect. The first N_BASE kept
candidates, in build_set.py's seeded order, form the set, with dropped statements held to a third.
Every base gives two items, clean (right answer APPROVE) and planted (right answer REJECT).

Candidates the judges disagree on are listed in disagreements.tsv for a person to settle; an
agreed rejection (both say harmless, dead or not compiling) is dropped without review.

    python .warf-experiments/evidence-set/select_set.py    # writes items.jsonl, disagreements.tsv, select.log"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
N_BASE = 50
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


kept, disagree, rejected, ops = [], [], 0, {}
for c in cands:
    a, b = verdict[("A", c["base"])], verdict[("B", c["base"])]
    if good(a) and good(b):
        if len(kept) < N_BASE and (c["operator"] != "drop_stmt" or ops.get("drop_stmt", 0) < N_BASE // 3):
            kept.append((c, a, b))
            ops[c["operator"]] = ops.get(c["operator"], 0) + 1
    elif good(a) or good(b):
        disagree.append((c, a, b))
    else:
        rejected += 1
both_good = sum(good(verdict[("A", c["base"])]) and good(verdict[("B", c["base"])]) for c in cands)
say(f"{len(cands)} candidates: both judges keep {both_good}, they disagree on {len(disagree)}, both reject {rejected}")
say(f"set: {len(kept)} bases ({2 * len(kept)} items); operators: "
    + ", ".join(f"{k} {v}" for k, v in sorted(ops.items())))
say(f"visible from the diff, both judges: {sum(a['visible'] == b['visible'] == 'diff' for _, a, b in kept)}; "
    f"needs another file, either judge: {sum('needs_other_file' in (a['visible'], b['visible']) for _, a, b in kept)}")
say(f"commits after 2026-06-30 (after Claude Opus 5.5's training cutoff): {sum(c['date'] > '2026-06-30' for c, _, _ in kept)}")

with (HERE / "items.jsonl").open("w", encoding="utf-8") as out:
    for c, a, b in kept:
        common = {k: c[k] for k in ("base", "commit", "date", "subject", "file", "domain", "context", "operator")}
        visible = a["visible"] if a["visible"] == b["visible"] else "unsure"
        out.write(json.dumps({**common, "id": c["base"] + ":clean", "kind": "clean", "answer": "APPROVE",
                              "code": c["code_clean"]}, ensure_ascii=False) + "\n")
        out.write(json.dumps({**common, "id": c["base"] + ":planted", "kind": "planted", "answer": "REJECT",
                              "original": c["original"], "mutated": c["mutated"], "visible": visible,
                              "judge_reasons": [a["reason"], b["reason"]], "code": c["code_planted"]},
                             ensure_ascii=False) + "\n")
with (HERE / "disagreements.tsv").open("w", encoding="utf-8") as out:
    out.write("base\toperator\toriginal\tmutated\tA compiles/defect\tB compiles/defect\tA reason\tB reason\n")
    for c, a, b in disagree:
        out.write("\t".join([c["base"], c["operator"], c["original"].strip(), (c["mutated"] or "(line dropped)").strip(),
                             f"{a['compiles']}/{a['defect']}", f"{b['compiles']}/{b['defect']}",
                             a["reason"].replace("\t", " "), b["reason"].replace("\t", " ")]) + "\n")
(HERE / "select.log").write_text("\n".join(out_log) + "\n", encoding="utf-8")
