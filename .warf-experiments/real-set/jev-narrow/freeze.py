"""Thresholds frozen from the development set for the confirm-set Jev test: for each score, the cut
with the best in-sample balanced accuracy on the 132 dev items (ties: lowest cut)."""
import contextlib, io, json
from pathlib import Path
with contextlib.redirect_stdout(io.StringIO()):
    import score_narrow as s
out = {}
for key, name in (("verdict", "verdict, whole change (this run)"), ("narrow", "narrow checks, hunks, mean logit of hunk max")):
    sc = s.S[name]; ts = sorted(set(sc.values()))
    def ba(t):
        P = [i for i in s.ids if s.D[i]]; N = [i for i in s.ids if not s.D[i]]
        return (sum(sc[i] >= t for i in P) / len(P) + sum(sc[i] < t for i in N) / len(N)) / 2
    t = max(ts, key=lambda t: (ba(t), -t)); out[key] = {"threshold": t, "dev_ba": round(ba(t), 4)}
print(out)
(Path(__file__).parent / "frozen.json").write_text(json.dumps(out, indent=1))
