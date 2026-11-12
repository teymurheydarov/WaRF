"""Score run_variants.py's answers against the plain run (answers.jsonl, whole state) on the 128 dev items
that are not few-shot examples. Same measures as score_narrow.py. Writes score_variants.log."""
import contextlib, io, json, math
from pathlib import Path
HERE = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    import score_narrow as s
shot = {x["id"] for x in json.loads((HERE / "fewshot.json").read_text(encoding="utf-8"))}
ids = [i for i in s.ids if i not in shot]; D = s.D; lg = s.lg; CH = s.CH
def p(a):
    if a["type"] == "noul": return a["noul"]
    if a["type"] == "score": return a["score"]
    pr = a["probabilities"]; return pr.get("REJECT", pr.get("YES", 0.0))
def load(fn, whole_only=False):
    w = {}
    for l in (HERE / fn).open(encoding="utf-8"):
        r = json.loads(l)
        if whole_only and r.get("state") != "whole": continue
        ans = r["answers"]
        w[r["id"]] = {q: (p(v) if "type" in v else (v["p"] or {}).get("REJECT" if q == "verdict" else "YES", 0.0)) for q, v in ans.items()}
    return w
def auc(sc, smp):
    P = [sc[i] for i in smp if D[i]]; N = [sc[i] for i in smp if not D[i]]
    return sum((a > b) + 0.5 * (a == b) for a in P for b in N) / (len(P) * len(N)), len(P) * len(N)
def within(sc):
    num = den = 0
    for b in s.bins:
        b = [i for i in b if i in sc]
        if any(D[i] for i in b) and any(not D[i] for i in b):
            a, n = auc(sc, b); num += a * n; den += n
    return num / den
out = [f"{len(ids)} items (few-shot examples excluded)", f"{'variant / score':<36} {'AUC':>6} {'within':>7}"]
for name, fn, wo in (("plain", "answers.jsonl", True), ("noul", "answers_noul.jsonl", False), ("score", "answers_score.jsonl", False),
                     ("json", "answers_json.jsonl", False), ("fewshot", "answers_fewshot.jsonl", False)):
    w = load(fn, wo); assert all(i in w for i in ids), name
    rows = [("verdict", {i: w[i]["verdict"] for i in ids}), ("narrow mean logit", {i: sum(lg(w[i][q]) for q in CH) / 7 for i in ids})]
    if name == "score": rows.append(("severity (expected score)", {i: w[i]["severity"] for i in ids}))
    for sn, sc in rows:
        out.append(f"{name + ', ' + sn:<36} {auc(sc, ids)[0]:6.3f} {within(sc):7.3f}")
print("\n".join(out)); (HERE / "score_variants.log").write_text("\n".join(out) + "\n", encoding="utf-8")
