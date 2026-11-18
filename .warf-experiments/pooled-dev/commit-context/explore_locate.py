"""EXPLORATORY, chosen after the primary result (README.md "Result"): commit context for the LOCATE seat only
(BOUNDARY and CHECKLIST without it), from the stored answers of both runs; no Jev call. A suggestion for a
fresh test, not a result.

    python explore_locate.py      # writes explore_locate.log"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score_cc as S  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


total = [0, 0]
for name, (short, set_dir) in S.SETS.items():
    items = {json.loads(l)["id"]: json.loads(l) for l in (set_dir / "items.jsonl").open(encoding="utf-8")}
    ids = list(items)
    Y = {i: (-1 if items[i]["kind"] == "defective" else 1) for i in ids}
    seats = S.load_panel(set_dir).panel3()
    names = {s.name for s in seats}
    stored = S.answers(set_dir / "sessions.jsonl", names)
    new = S.answers(HERE / f"sessions_cc_{short}.jsonl", names)
    hybrid = {**stored, **{k: v for k, v in new.items() if k[1] == "LOCATE"}}
    p_base = [S.predict(items, ids, Y, seats, stored, rep) for rep in range(5)]
    p_hyb = [S.predict(items, ids, Y, seats, hybrid, rep) for rep in range(5)]
    n10, n01 = S.mcnemar_counts(p_hyb[0], p_base[0], Y, ids)
    total[0] += n10; total[1] += n01
    say(f"{name}: PANEL3 {100 * S.ba(p_base[0], Y, ids):.1f}% (mean of 5 {100 * sum(S.ba(p, Y, ids) for p in p_base) / 5:.1f}%), "
        f"CC for LOCATE only {100 * S.ba(p_hyb[0], Y, ids):.1f}% (mean of 5 {100 * sum(S.ba(p, Y, ids) for p in p_hyb) / 5:.1f}%); "
        f"{n10} vs {n01}, p = {S.exact_p(n10, n01):.4f}")
say(f"both: {total[0]} vs {total[1]}, p = {S.exact_p(*total):.4f}  (exploratory)")
(HERE / "explore_locate.log").write_text("\n".join(out) + "\n", encoding="utf-8")
