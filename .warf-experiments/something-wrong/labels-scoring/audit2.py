"""Part 2: what the blamed lines are, a 'blameable added lines' artefact, paired differences on the
non-trivial subset, and a decomposition of replay.py's single-seat AUC drop.
Read-only on existing files; writes audit2.log and temporary session logs only under this folder."""
import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
ROOT = EXP.parent
sys.path.insert(0, str(ROOT))
from warf.calibration import Calibrator, fit_platt, approve_logodds  # noqa: E402
from warf.state import AgentProfile, persona_hash  # noqa: E402

GIT_DIR = r"C:\Users\Teymur Heydarov\source\repos\gismo6\.git"
AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
out = []


def say(s=""):
    out.append(str(s))
    print(s)


def jl(p):
    return [json.loads(x) for x in Path(p).open(encoding="utf-8")]


def auc(score, pos):
    P = [s for s, t in zip(score, pos) if t]
    N = [s for s, t in zip(score, pos) if not t]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))


def paired_diff(s1, s2, pos, n=2000, seed=5):
    P = [i for i, t in enumerate(pos) if t]
    N = [i for i, t in enumerate(pos) if not t]
    rng = random.Random(seed)
    d = []
    for _ in range(n):
        idx = [rng.choice(P) for _ in P] + [rng.choice(N) for _ in N]
        yy = [pos[i] for i in idx]
        d.append(auc([s1[i] for i in idx], yy) - auc([s2[i] for i in idx], yy))
    d.sort()
    return auc(s1, pos) - auc(s2, pos), d[int(0.025 * n)], d[int(0.975 * n) - 1]


def git(*a):
    r = subprocess.run(["git", f"--git-dir={GIT_DIR}", *a], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout


sel = jl(EXP / "laya-five" / "selection.jsonl")
ids = [s["id"] for s in sel]
y = [s["label"] == "REJECT" for s in sel]
feat = {r["id"]: r for r in jl(EXP / "jev-five" / "verify" / "refute" / "features.jsonl")}
F = [feat[i] for i in ids]
one = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_one.jsonl")}
five = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_five.jsonl")}
jev = [one[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids]
jev5 = [sum(five[i]["jev"]["round1"][a]["p_reject"] for a in AGENTS) / 5 for i in ids]
claude = [s["p_claude"] for s in sel]
laya = [s["p_single_laya"] for s in sel]
added = [f["added"] for f in F]
trivial = [f["comment_only"] or f["added"] == 0 for f in F]

want = {(s["commit"], s["file"]) for s in sel}
lab = {}
for line in (EXP / "laya-sweep" / "labels.jsonl").open(encoding="utf-8"):
    e = json.loads(line)
    if (e["commit"], e["file"]) in want and "gismo6" in e["repo"]:
        lab[(e["commit"], e["file"])] = e

# ---- 1. what the blamed lines are ------------------------------------------------------------
say("== blamed lines of the 50 REJECTs (content at the blamed commit)")
cat = {}
for s in sel:
    if s["label"] != "REJECT":
        continue
    L = lab[(s["commit"], s["file"])]
    text = git("show", f"{s['commit']}:{s['file']}").split("\n")
    got = [text[n - 1].strip() if 0 < n <= len(text) else "?" for n in L["lines"]]
    first = got[0]
    kind = ("#include" if all(g.startswith("#include") for g in got)
            else "preprocessor" if all(g.startswith("#") for g in got)
            else "other")
    cat[kind] = cat.get(kind, 0) + 1
    say(f"  {s['id']} {kind:<12} {' | '.join(g[:60] for g in got[:3])}")
say(f"  kinds of blamed lines: {cat}")

# ---- 2. blameable added lines: non-blank, non-comment added lines ------------------------------
states = {r["id"]: r for r in jl(EXP / "jev-five" / "verify" / "refute" / "states.jsonl")}
sys.path.insert(0, str(EXP / "laya-five"))
from run_five import PLAN, file_patch  # noqa: E402
plan = {}
for line in PLAN.open(encoding="utf-8"):
    e = json.loads(line)
    if e["sha"] in {s["commit"] for s in sel}:
        plan[e["sha"]] = e
code_added = []
for s, f in zip(sel, F):
    patch = file_patch(plan[s["commit"]], s["file"])
    body = patch.partition("\n@@")[2]
    adds = [l[1:].strip() for l in body.split("\n") if l.startswith("+") and not l.startswith("+++")]
    py = f["ext"] == ".py"
    n = 0
    for a in adds:
        if not re.search(r"\w", a):
            continue
        if py and a.startswith("#"):
            continue
        if not py and (a.startswith(("//", "/*", "*/")) or (a.startswith("*") and a[1:2] in ("", " ", "\t", "*"))):
            continue
        n += 1
    code_added.append(n)
say(f"\n  added lines AUC {auc(added, y):.3f}; non-blank non-comment added lines AUC {auc(code_added, y):.3f}; "
    f"'any code line added' AUC {auc([float(c > 0) for c in code_added], y):.3f}")
say(f"  items with no code line added: R {sum(c == 0 and t for c, t in zip(code_added, y))} A {sum(c == 0 and not t for c, t in zip(code_added, y))}")

# ---- 3. paired differences on all and on the non-trivial 85 -------------------------------------
say("\n== Claude minus Jev, all 100 and without the 15 trivial APPROVEs (resampling within label)")
nt = [i for i in range(100) if not trivial[i]]
for name, a_s, b_s in (("Claude - Jev one", claude, jev), ("Claude - Jev five R1", claude, jev5),
                       ("Claude - added lines", claude, added), ("Jev one - added lines", jev, added)):
    d, lo, hi = paired_diff(a_s, b_s, y)
    d2, lo2, hi2 = paired_diff([a_s[i] for i in nt], [b_s[i] for i in nt], [y[i] for i in nt])
    say(f"  {name:<22} all {d:+.3f} [{lo:+.3f}, {hi:+.3f}]   non-trivial {d2:+.3f} [{lo2:+.3f}, {hi2:+.3f}]")

# ---- 4. replay.py decomposition (Jev alone, Laya alone, Claude alone) --------------------------
say("\n== replay decomposition: raw AUC -> two-decimal clamp -> out-of-fold Platt evidence (replay's folds, seed 11)")
yy = {s["id"]: (-1 if s["label"] == "REJECT" else 1) for s in sel}
rng = random.Random(11)
folds = {}
for label in (1, -1):
    members = [i for i in ids if yy[i] == label]
    rng.shuffle(members)
    for k, i in enumerate(members):
        folds[i] = k % 5
clamp = lambda p: min(0.99, max(0.01, round(p, 2)))
seats = {"JEV": dict(zip(ids, jev)), "LAYA": dict(zip(ids, laya)), "CLAUDE": dict(zip(ids, claude))}
tmp = HERE / "tmp_log.jsonl"
for n, pm in seats.items():
    prof = AgentProfile(name=n, persona=f"seat {n}", persona_hash=persona_hash(f"seat {n}"))
    ev, fits, perfold = {}, [], []
    for k in range(5):
        with tmp.open("w", encoding="utf-8") as f:
            for i in ids:
                if folds[i] == k:
                    continue
                pr = clamp(pm[i])
                f.write(json.dumps({"session_id": i, "votes": [{"agent": n, "vote": -1 if pr > 0.5 else 1, "persona": prof.persona_hash,
                                    "provider": "x", "model": "y", "p_reject": pr}],
                                    "oracle": {"type": "DEVELOPER", "x_star": yy[i]}}) + "\n")
        cal = Calibrator(tmp)
        fit = cal._platt(prof, "x", "y")
        fits.append((round(fit.a, 3), round(fit.b, 3), round(fit.prior_logodds, 3)))
        test = [i for i in ids if folds[i] == k]
        for i in test:
            pr = clamp(pm[i])
            ev[i] = cal.evidence(prof, -1 if pr > 0.5 else 1, pr, 0.5, "x", "y")[0]
        perfold.append(auc([-ev[i] for i in test], [yy[i] == -1 for i in test]))
    raw = auc([pm[i] for i in ids], [yy[i] == -1 for i in ids])
    rd = auc([clamp(pm[i]) for i in ids], [yy[i] == -1 for i in ids])
    oof = auc([-ev[i] for i in ids], [yy[i] == -1 for i in ids])
    say(f"  {n:<7} raw {raw:.3f}  clamped {rd:.3f}  OOF Platt pooled {oof:.3f}  mean of per-fold AUCs {sum(perfold) / 5:.3f}")
    say(f"          fits (a, b, prior): {fits}")
tmp.unlink()

# sign check: higher p(REJECT) -> lower evidence (more REJECT) for every fold fit with b > 0
say("  (b > 0 in every fit means evidence falls as p(REJECT) rises: the sign convention is right)")
(HERE / "audit2.log").write_text("\n".join(out) + "\n", encoding="utf-8")
