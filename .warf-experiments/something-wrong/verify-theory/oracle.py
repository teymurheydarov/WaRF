"""Addendum: in-sample oracle d' = sqrt(d R^-1 d) for a few member sets (binormal, parametric d')."""
import math, runpy
from datetime import datetime
from pathlib import Path
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    g = runpy.run_path(str(Path(__file__).with_name("verify.py")))
Lg, ids, feat, dparam, wcorr, solve, N = g["Lg"], g["ids"], g["feat"], g["dparam"], g["wcorr"], g["solve"], g["N"]
F = [feat[i] for i in ids]
def yr(d):
    t = datetime.fromisoformat(d.replace("Z", "+00:00")); return t.year + (t.timetuple().tm_yday - 1) / 366
Lg["log_removed"] = [math.log1p(f["removed"]) for f in F]
Lg["log_chars"] = [math.log(f["patch_chars"]) for f in F]
for k, fn in (("new", lambda f: f["new_file"]), ("del", lambda f: f["deleted_file"] or f["deletion_only"]),
              ("comment", lambda f: f["comment_only"]), ("header", lambda f: f["header"]), ("test", lambda f: f["test_or_example"]),
              ("ext", lambda f: f["extensions_dir"]), ("enriched", lambda f: f["enriched"])):
    Lg[k] = [float(fn(f)) for f in F]
Lg["year"] = [yr(f["commit_date"]) for f in F]
F11 = ["new", "del", "comment", "header", "test", "log_added", "log_removed", "log_chars", "ext", "enriched", "year"]
seats = ["J_" + a for a in g["SEATS"]]
def orc(keys):
    d = [dparam(Lg[k]) for k in keys]
    R = [[1.0 if a == b else wcorr(Lg[a], Lg[b]) for b in keys] for a in keys]
    w = solve(R, d)
    dc = math.sqrt(sum(a * b for a, b in zip(d, w)))
    return dc, N.cdf(dc / math.sqrt(2))
for ks in (["claude"], ["claude", "jev"], ["claude", "laya"], seats, ["claude"] + seats, ["claude", "jev", "laya", "log_added"], ["claude"] + F11):
    dc, a = orc(ks)
    print(f"{'+'.join(ks) if len(ks) < 6 else ks[0] + ' + ' + str(len(ks) - 1) + ' more':45s} d {dc:.3f} AUC {a:.3f}")
