"""Write the history (the first 40 confirmed defects in candidate-list order) before judging ends, so that the
profile and checks agents can work while the rest is judged. Allowed only when every candidate up to the
40th confirmed one has judge A's verdict and, where A said yes, judge B's: then no later verdict can change
which 40 they are. select_defects.py must later write the same history_defects.md (it is compared).

    python write_history.py      # writes history_defects.md"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
HISTORY = 40

cands = [json.loads(l) for l in (HERE / "candidates.jsonl").open(encoding="utf-8")]
verdict = {}
for v in (json.loads(l) for f in sorted((HERE / "judgements").glob("*.jsonl")) for l in f.open(encoding="utf-8")
          if l.strip()):
    verdict[(v["judge"], v["base"])] = v
history = []
for k, c in enumerate(cands):
    a = verdict.get(("A", c["base"]))
    if a is None:
        raise SystemExit(f"candidate {k} ({c['base']}) has no verdict from A yet: the history is not fixed")
    if a["introduced"] != "yes":
        continue
    b = verdict.get(("B", c["base"]))
    if b is None:
        raise SystemExit(f"candidate {k} ({c['base']}): A said yes, B has not judged it: the history is not fixed")
    if b["introduced"] == "yes":
        history.append((c, a, b))
        if len(history) == HISTORY:
            print(f"history fixed: the first {HISTORY} confirmed defects lie within the first {k + 1} candidates")
            break
lines = [f"# Confirmed DuckDB defects outside the test set (both judges yes; the first {HISTORY} in candidate order)", ""]
lines += [f"- {c['file']} ({c['date']}): {a['defect']} | {b['defect']}" for c, a, b in history]
(HERE / "history_defects.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
