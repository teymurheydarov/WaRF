"""Split DuckDB's confirmed defects into history and test (README.md), from the judgements only; no Jev call.

A candidate is a defect when judge A and judge B both say "introduced: yes". In candidate-list order, the first
HISTORY of them are the project's history (history.jsonl, and history_defects.md for the profile agent: file,
date and the two judges' descriptions, the shape of ../pooled-dev/history/history_defects.md); the next TEST are
the test defects (defects.jsonl, items in ../rdb-set/select_rdb.py's shape).

    python select_defects.py      # writes history.jsonl, history_defects.md, defects.jsonl, select_defects.log"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
HISTORY, TEST = 40, 400
out = []


def say(s=""):
    out.append(s); print(s)


cands = [json.loads(l) for l in (HERE / "candidates.jsonl").open(encoding="utf-8")]
verdict = {}
for v in (json.loads(l) for f in sorted((HERE / "judgements").glob("*.jsonl")) for l in f.open(encoding="utf-8")
          if l.strip()):
    if (v["judge"], v["base"]) in verdict:
        raise SystemExit(f"two verdicts from judge {v['judge']} for {v['base']}")
    verdict[(v["judge"], v["base"])] = v
confirmed, unjudged = [], 0
for c in cands:
    a = verdict.get(("A", c["base"]))
    if a is None:
        unjudged += 1
        continue
    if a["introduced"] == "yes" and ("B", c["base"]) not in verdict:
        raise SystemExit(f"{c['base']}: A said yes but B has not judged it")
    b = verdict.get(("B", c["base"]), {})
    if a["introduced"] == "yes" and b.get("introduced") == "yes":
        confirmed.append((c, a, b))
history, test = confirmed[:HISTORY], confirmed[HISTORY:HISTORY + TEST]
say(f"{len(cands)} candidates ({unjudged} not judged): {len(confirmed)} confirmed by both judges; "
    f"history {len(history)}, test {len(test)}, beyond {max(0, len(confirmed) - HISTORY - TEST)}")
if len(test) < TEST:
    say(f"  only {len(test)} test defects: the target of {TEST} is not reached")


def item(c, a, b):
    return {"id": c["base"] + ":defective", "base": c["base"], "kind": "defective", "answer": "REJECT",
            "commit": c["commit"], "date": c["date"], "file": c["file"], "domain": c["domain"], "context": c["context"],
            "fix": c["fix"], "fix_subject": c["fix_subject"],
            "visible": a["visible"] if a["visible"] == b["visible"] else "split",
            "defect": [a["defect"], b["defect"]], "code": c["code"]}


for name, rows in (("history.jsonl", history), ("defects.jsonl", test)):
    with (HERE / name).open("w", encoding="utf-8") as f:
        for t in rows:
            f.write(json.dumps(item(*t), ensure_ascii=False) + "\n")
lines = [f"# Confirmed DuckDB defects outside the test set (both judges yes; the first {HISTORY} in candidate order)", ""]
lines += [f"- {c['file']} ({c['date']}): {a['defect']} | {b['defect']}" for c, a, b in history]
(HERE / "history_defects.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
vis = {}
for _, a, b in test:
    k = a["visible"] if a["visible"] == b["visible"] else "split"
    vis[k] = vis.get(k, 0) + 1
say("test defects' visibility (both judges): " + ", ".join(f"{k} {v}" for k, v in sorted(vis.items())))
(HERE / "select_defects.log").write_text("\n".join(out) + "\n", encoding="utf-8")
