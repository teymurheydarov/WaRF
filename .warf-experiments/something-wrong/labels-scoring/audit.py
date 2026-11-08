"""Audit of labels and scoring for the 100 gismo6 commits (laya-five selection).
Read-only on every existing file; writes only audit.log next to this script.
Pure Python (numpy crashes in gs\\cf\\python.exe)."""
import json
import math
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
GIT_DIR = r"C:\Users\Teymur Heydarov\source\repos\gismo6\.git"
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


def boot_auc(score, pos, n=2000, seed=1):
    P = [i for i, t in enumerate(pos) if t]
    N = [i for i, t in enumerate(pos) if not t]
    rng = random.Random(seed)
    v = []
    for _ in range(n):
        idx = [rng.choice(P) for _ in P] + [rng.choice(N) for _ in N]
        v.append(auc([score[i] for i in idx], [pos[i] for i in idx]))
    v.sort()
    return v[int(0.025 * n)], v[int(0.975 * n) - 1]


sel = jl(EXP / "laya-five" / "selection.jsonl")
ids = [s["id"] for s in sel]
y = [s["label"] == "REJECT" for s in sel]
say(f"selection: {len(sel)} rows, {sum(y)} REJECT, distinct commits {len({s['commit'] for s in sel})}, distinct ids {len(set(ids))}")
say(f"pair order REJECT,APPROVE at rows 2k,2k+1: {all(y[2*k] and not y[2*k+1] for k in range(50))}")

# ---------- labels: re-derive from labels.jsonl -------------------------------------------
want = {(s["commit"], s["file"]) for s in sel}
lab = {}
for line in (EXP / "laya-sweep" / "labels.jsonl").open(encoding="utf-8"):
    e = json.loads(line)
    if (e["commit"], e["file"]) in want and "gismo6" in e["repo"]:
        lab[(e["commit"], e["file"])] = e
mism = [s["id"] for s in sel if (s["commit"], s["file"]) not in lab or lab[(s["commit"], s["file"])]["label"] != s["label"]]
say(f"labels.jsonl agrees with selection label for {100 - len(mism)}/100; mismatches {mism}")

feat = {r["id"]: r for r in jl(EXP / "jev-five" / "verify" / "refute" / "features.jsonl")}
F = [feat[i] for i in ids]

# ---------- scores --------------------------------------------------------------------------
one = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_one.jsonl")}
five = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_five.jsonl")}
std = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_standard.jsonl")}
lfive = {r["five"]["id"]: r for r in jl(EXP / "laya-five" / "sessions.jsonl")}
key = {k["id"]: k for k in json.loads((EXP / "laya-near-chance" / "claude-review" / "key.json").read_text(encoding="utf-8"))}
cres = json.loads((EXP / "laya-near-chance" / "laya-probe" / "claude_review_result.json").read_text(encoding="utf-8"))
claude_raw = {it["id"]: it for b in cres["reviews"] for it in b["items"]}

# label leak check in the stored sessions: are the labels in the jev blocks the selection labels?
leak = sum(one[i]["jev"]["label"] != s["label"] for i, s in zip(ids, sel))
say(f"sessions_one jev.label disagrees with selection: {leak}; key.json label disagrees: "
    f"{sum(key[i]['label'] != s['label'] for i, s in zip(ids, sel))}; key p_laya == p_single_laya: "
    f"{sum(abs(key[i]['p_laya'] - s['p_single_laya']) < 1e-12 for i, s in zip(ids, sel))}/100; "
    f"claude p == p_claude: {sum(abs(claude_raw[i]['p_defect'] - s['p_claude']) < 1e-12 for i, s in zip(ids, sel))}/100")


def final(block, a):
    b = block["round2"].get(a) or block["round1"][a]
    return b["p_reject"]


S = {
    "Jev one question": [one[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids],
    "Jev five mean p R1": [sum(five[i]["jev"]["round1"][a]["p_reject"] for a in AGENTS) / 5 for i in ids],
    "Jev five mean p final": [sum(final(five[i]["jev"], a) for a in AGENTS) / 5 for i in ids],
    "Jev standard mean p": [sum(v["p_reject"] for v in std[i]["jev"]["round1"].values()) / len(std[i]["jev"]["round1"]) for i in ids],
    "Laya one (sweep)": [s["p_single_laya"] for s in sel],
    "Laya five mean p R1": [sum(lfive[i]["five"]["round1"][a]["p_reject"] for a in AGENTS) / 5 for i in ids],
    "Claude blinded": [s["p_claude"] for s in sel],
    "added lines": [f["added"] for f in F],
    "removed lines": [f["removed"] for f in F],
    "patch chars": [s["patch_chars"] for s in sel],
    "state tokens": [s["state_tokens"] for s in sel],
}
ref = {"Jev one question": 0.641, "Jev five mean p R1": 0.628, "Jev five mean p final": 0.633, "Jev standard mean p": 0.624,
       "Laya one (sweep)": 0.586, "Laya five mean p R1": 0.557, "Claude blinded": 0.745, "added lines": 0.716, "patch chars": 0.502}
say("\n== headline AUCs recomputed (later fixed = positive, ties half), 95% bootstrap within label")
for n, s in S.items():
    a = auc(s, y)
    lo, hi = boot_auc(s, y)
    say(f"  {n:<24} AUC {a:.3f} [{lo:.3f}, {hi:.3f}]  RESULTS.md {ref.get(n, '-')}  distinct values {len(set(s))}")

# ---------- artefacts -----------------------------------------------------------------------
say("\n== label-determining artefacts")
added = [f["added"] for f in F]
code_added = []      # added lines that are not blank and not comments: what B-SZZ can blame
for f, s in zip(F, sel):
    pass
trivial = [f["comment_only"] or f["added"] == 0 for f in F]
say(f"  added == 0: R {sum(a == 0 and t for a, t in zip(added, y))}  A {sum(a == 0 and not t for a, t in zip(added, y))}")
say(f"  comment-only: R {sum(f['comment_only'] and t for f, t in zip(F, y))}  A {sum(f['comment_only'] and not t for f, t in zip(F, y))}")
say(f"  trivial (no added line or comment-only): R {sum(t and yy for t, yy in zip(trivial, y))}  A {sum(t and not yy for t, yy in zip(trivial, y))}")
say(f"  new file: R {sum(f['status']=='new' and t for f, t in zip(F, y))}  A {sum(f['status']=='new' and not t for f, t in zip(F, y))}")
say(f"  blamed_lines of REJECTs: {sorted(lab[(s['commit'], s['file'])]['blamed_lines'] for s in sel if s['label']=='REJECT')}")
say(f"  REJECTs with blamed lines >= added lines: {sum(lab[(s['commit'], s['file'])]['blamed_lines'] >= f['added'] for s, f in zip(sel, F) if s['label']=='REJECT')}/50")

# Decompose each reviewer's AUC: comparisons against trivial APPROVEs vs non-trivial ones
nt = [not t for t in trivial]
say("\n  reviewer AUC: all 100 | R vs the trivial A only | without trivial items (n R/A) | within pairs both non-trivial")
pairs_nt = [k for k in range(50) if nt[2 * k] and nt[2 * k + 1]]
for n in ("Jev one question", "Jev five mean p R1", "Claude blinded", "Laya one (sweep)", "added lines", "patch chars"):
    s = S[n]
    P = [s[i] for i in range(100) if y[i]]
    T = [s[i] for i in range(100) if trivial[i] and not y[i]]
    vs_triv = sum((p > q) + 0.5 * (p == q) for p in P for q in T) / (len(P) * len(T))
    s2 = [s[i] for i in range(100) if nt[i]]
    y2 = [y[i] for i in range(100) if nt[i]]
    pw = sum((s[2 * k] > s[2 * k + 1]) + 0.5 * (s[2 * k] == s[2 * k + 1]) for k in pairs_nt)
    lo, hi = boot_auc(s2, y2)
    say(f"  {n:<24} {auc(s, y):.3f} | {vs_triv:.3f} | {auc(s2, y2):.3f} [{lo:.3f},{hi:.3f}] ({sum(y2)}/{len(y2)-sum(y2)}) | "
        f"pairs won {pw}/{len(pairs_nt)}")

# AUC within strata of added lines (exact match stratification) for added-line-free signal
say("\n  added lines among non-trivial items: AUC " + f"{auc([added[i] for i in range(100) if nt[i]], [y[i] for i in range(100) if nt[i]]):.3f}")

# Partial: residual of each reviewer after added-lines rank (Spearman with label within strata)
def ranks(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = math.sqrt(sum((x - ma) ** 2 for x in a)); sb = math.sqrt(sum((x - mb) ** 2 for x in b))
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / (sa * sb)


say("\n  Spearman with log added lines (all 100): " + ", ".join(
    f"{n} {corr(ranks(S[n]), ranks(added)):+.2f}" for n in ("Jev one question", "Jev five mean p R1", "Claude blinded", "Laya one (sweep)")))

# Mean score on trivial items vs others, per reviewer
say("\n  mean score on the 15 trivial APPROVEs vs non-trivial APPROVEs vs REJECTs:")
for n in ("Jev one question", "Jev five mean p R1", "Claude blinded", "Laya one (sweep)"):
    s = S[n]
    ta = [s[i] for i in range(100) if trivial[i] and not y[i]]
    na = [s[i] for i in range(100) if nt[i] and not y[i]]
    r = [s[i] for i in range(100) if y[i]]
    say(f"  {n:<24} trivial A {sum(ta)/len(ta):.3f}  other A {sum(na)/len(na):.3f}  R {sum(r)/len(r):.3f}")

# Combine added lines with each reviewer by rank average: does each one add beyond added lines?
say("\n  rank-average of added lines and reviewer (AUC), and best by within-added-bin ordering:")
for n in ("Jev one question", "Jev five mean p R1", "Claude blinded", "Laya one (sweep)"):
    ra, rb = ranks(added), ranks(S[n])
    say(f"  added + {n:<20} rank mean AUC {auc([a + b for a, b in zip(ra, rb)], y):.3f}; "
        f"lexicographic (added, then reviewer) AUC {auc([a + 0.001 * b / 100 for a, b in zip(added, rb)], y):.3f}")
say(f"  added lines alone {auc(added, y):.3f}; trivial flag alone {auc([0 if t else 1 for t in trivial], y):.3f}")

# ---------- fixes behind the REJECT labels ------------------------------------------------------
say("\n== the fixes behind the 50 REJECT labels")
szz = {}
for line in (EXP / "laya-sweep" / "szz.jsonl").open(encoding="utf-8"):
    r = json.loads(line)
    if "gismo6" in r.get("repo", ""):
        szz[r["fix"]] = r


def git(*a):
    r = subprocess.run(["git", f"--git-dir={GIT_DIR}", *a], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip()


rows = []
for s, f in zip(sel, F):
    if s["label"] != "REJECT":
        continue
    L = lab[(s["commit"], s["file"])]
    fx = L["fixes"][0]
    sub = szz.get(fx["fix"], {}).get("subject", "?")
    a_commit = git("log", "-1", "--format=%ae", s["commit"])
    a_fix = git("log", "-1", "--format=%ae", fx["fix"])
    rows.append((fx["days"], fx["kind"], a_commit == a_fix, L["blamed_lines"], f["added"], s["id"], sub[:70], len(L["fixes"])))
rows.sort()
for r in rows:
    say(f"  {r[0]:>7.1f} d  {r[1]:<7} same-author {str(r[2]):<5} blamed {r[3]:>3} added {r[4]:>3} fixes {r[7]}  {r[5]}  {r[6]}")
days = [r[0] for r in rows]
say(f"  first fix within 1 day: {sum(d <= 1 for d in days)}/50, within 7 days {sum(d <= 7 for d in days)}, within 30 {sum(d <= 30 for d in days)}, >180 {sum(d > 180 for d in days)}")
say(f"  same author as the fix: {sum(r[2] for r in rows)}/50; kinds: " +
    ", ".join(f"{k} {sum(r[1] == k for r in rows)}" for k in sorted({r[1] for r in rows})))
apl = [lab[(s["commit"], s["file"])]["later_days"] for s in sel if s["label"] == "APPROVE"]
rel = [lab[(s["commit"], s["file"])]["later_days"] for s in sel if s["label"] == "REJECT"]
say(f"  later history (days): APPROVE min {min(apl)} median {sorted(apl)[25]}; REJECT min {min(rel)} median {sorted(rel)[25]}; "
    f"REJECTs with < 180 days later history: {sum(d < 180 for d in rel)}")

# by fix speed: how each reviewer ranks fast-fixed vs slow-fixed REJECTs against all APPROVEs
fast = {r[5] for r in rows if r[0] <= 7}
say("\n  AUC against all 50 APPROVEs, REJECTs split by first-fix delay (<=7 d: %d, >7 d: %d):" % (len(fast), 50 - len(fast)))
for n in ("Jev one question", "Jev five mean p R1", "Claude blinded", "Laya one (sweep)", "added lines"):
    s = S[n]
    for name, keep in (("<=7d", lambda i: ids[i] in fast), (">7d", lambda i: ids[i] not in fast)):
        idx = [i for i in range(100) if not y[i] or keep(i)]
        out_auc = auc([s[i] for i in idx], [y[i] for i in idx])
        say(f"    {n:<24} {name:<5} {out_auc:.3f}")

# ---------- label-noise ceiling ---------------------------------------------------------------
say("\n== label-noise ceiling: AUC of a perfect detector of true defects, given label noise")
say("   q = share of REJECT labels that are not real defects, r = share of APPROVE labels that hide one")
for q in (0.2, 0.34, 0.45, 0.6):
    cells = []
    for r in (0.0, 0.1, 0.2, 0.3):
        a = (1 - q) * (1 - r) + 0.5 * ((1 - q) * r + q * (1 - r))
        cells.append(f"r {r:.1f}: {a:.3f}")
    say(f"   q {q:.2f}: " + "  ".join(cells))

# ---------- replay rounding / ties ----------------------------------------------------------------
say("\n== replay.py clamp(round(p, 2)) effect on single-seat AUCs (no calibration)")
clamp = lambda p: min(0.99, max(0.01, round(p, 2)))
for n in ("Jev one question", "Laya one (sweep)", "Claude blinded"):
    s = S[n]
    c = [clamp(v) for v in s]
    say(f"  {n:<24} raw {auc(s, y):.3f} ({len(set(s))} values)  rounded {auc(c, y):.3f} ({len(set(c))} values)")
(HERE / "audit.log").write_text("\n".join(out) + "\n", encoding="utf-8")
