"""Score the alternative Jev inputs (answers_commit.jsonl, answers_changed.jsonl) against the 30-line diff
(answers.jsonl, whole state), same three measures as score_narrow.py. Writes score_inputs.log."""
import contextlib, io, json, math
from pathlib import Path
HERE = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    import score_narrow as s
CH = s.CH; out = []
def load(fn):
    w = {}
    for l in (HERE / fn).open(encoding="utf-8"):
        r = json.loads(l)
        if r["state"] == "whole":
            w[r["id"]] = {q: (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0) for q, v in r["answers"].items()}
    assert set(w) == set(s.ids), fn
    return w
size = lambda i: math.log(s.A[i] + 1)
print(f"{'input / score':<34} {'AUC':>6} {'within':>7} {'LOO size+score':>15}"); out.append("")
for name, fn in (("30-line diff", "answers.jsonl"), ("whole commit + message", "answers_commit.jsonl"), ("changed lines only", "answers_changed.jsonl")):
    w = load(fn)
    for sname, sc in (("verdict", {i: s.lg(w[i]["verdict"]) for i in s.ids}),
                      ("narrow mean logit", {i: sum(s.lg(w[i][q]) for q in CH) / len(CH) for i in s.ids})):
        line = f"{name + ', ' + sname:<34} {s.auc(sc)[0]:6.3f} {s.within(sc):7.3f} {s.loo([size, (lambda sc: lambda i: sc[i])(sc)]):15.3f}"
        print(line); out.append(line)
(HERE / "score_inputs.log").write_text("\n".join(out) + "\n", encoding="utf-8")
