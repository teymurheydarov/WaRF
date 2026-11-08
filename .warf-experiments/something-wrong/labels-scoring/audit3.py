"""Part 3: B-SZZ cosmetic filter vs block comments. For every REJECT of the 100 (and of the 352-item
Claude sample, gismo6 only), classify each blamed line at the blamed commit as inside a comment
(/* */ block or //), #include, other preprocessor, explicit template instantiation/extern, or code.
Then rescore the 100 without the REJECTs whose every blamed line sits in a comment.
Read-only; writes audit3.log here."""
import json
import random
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
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


def boot(score, pos, n=2000, seed=1):
    P = [i for i, t in enumerate(pos) if t]
    N = [i for i, t in enumerate(pos) if not t]
    rng = random.Random(seed)
    v = []
    for _ in range(n):
        idx = [rng.choice(P) for _ in P] + [rng.choice(N) for _ in N]
        v.append(auc([score[i] for i in idx], [pos[i] for i in idx]))
    v.sort()
    return v[int(0.025 * n)], v[int(0.975 * n) - 1]


def git(*a):
    r = subprocess.run(["git", f"--git-dir={GIT_DIR}", *a], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout


def comment_mask(text, py):
    """For each line: True if it has no code outside comments (C/C++ /* */ and //, Python #)."""
    lines = text.split("\n")
    mask = []
    in_block = False
    for ln in lines:
        code = []
        i = 0
        in_str = None
        while i < len(ln):
            c = ln[i]
            if py:
                if in_str:
                    if c == in_str:
                        in_str = None
                    code.append(c)
                elif c in "\"'":
                    in_str = c
                    code.append(c)
                elif c == "#":
                    break
                else:
                    code.append(c)
                i += 1
                continue
            if in_block:
                if ln.startswith("*/", i):
                    in_block = False
                    i += 2
                else:
                    i += 1
                continue
            if in_str:
                if c == "\\":
                    code.append(ln[i:i + 2]); i += 2; continue
                if c == in_str:
                    in_str = None
                code.append(c); i += 1; continue
            if c == '"':
                in_str = c; code.append(c); i += 1; continue
            if ln.startswith("/*", i):
                in_block = True; i += 2; continue
            if ln.startswith("//", i):
                break
            code.append(c); i += 1
        mask.append(not re.search(r"\w", "".join(code)))
    return lines, mask


def classify(commit, path, nums):
    text = git("show", f"{commit}:{path}")
    lines, mask = comment_mask(text, path.endswith(".py"))
    kinds = []
    for n in nums:
        if not (0 < n <= len(lines)):
            kinds.append("?"); continue
        s = lines[n - 1].strip()
        if mask[n - 1]:
            kinds.append("comment")
        elif s.startswith("#include") or s.startswith("# include"):
            kinds.append("include")
        elif s.startswith("#"):
            kinds.append("preproc")
        elif re.search(r"TEMPLATE_INST|TEMPLATE_EINST|^extern template|^template (class|struct)|EXTERN_", s):
            kinds.append("instantiation")
        else:
            kinds.append("code")
    return kinds


def summary(kinds):
    if all(k == "comment" for k in kinds):
        return "all comment"
    if all(k in ("comment", "include", "preproc", "instantiation") for k in kinds):
        return "include/preproc/inst"
    return "has code"


sel = jl(EXP / "laya-five" / "selection.jsonl")
ids = [s["id"] for s in sel]
y = [s["label"] == "REJECT" for s in sel]
want = None
lab = {}
for line in (EXP / "laya-sweep" / "labels.jsonl").open(encoding="utf-8"):
    e = json.loads(line)
    if "gismo6" in e["repo"] and e["label"] == "REJECT":
        lab[(e["commit"], e["file"])] = e

say("== the 50 REJECTs of the 100")
cls = {}
for s in sel:
    if s["label"] != "REJECT":
        continue
    L = lab[(s["commit"], s["file"])]
    k = classify(s["commit"], s["file"], L["lines"])
    cls[s["id"]] = summary(k)
    say(f"  {s['id']} {cls[s['id']]:<22} {k}")
from collections import Counter
say(f"  summary: {dict(Counter(cls.values()))}")

key = json.loads((EXP / "laya-near-chance" / "claude-review" / "key.json").read_text(encoding="utf-8"))
krej = [k for k in key if k["label"] == "REJECT" and "gismo6" in k["repo"]]
kc = Counter()
for k in krej:
    L = lab.get((k["commit"], k["file"]))
    if L is None:
        kc["no label row"] += 1; continue
    kc[summary(classify(k["commit"], k["file"], L["lines"]))] += 1
say(f"\n== the gismo6 REJECTs of the 352-item Claude sample ({len(krej)}): {dict(kc)}")

one = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_one.jsonl")}
five = {r["jev"]["id"]: r for r in jl(EXP / "jev-five" / "sessions_five.jsonl")}
feat = {r["id"]: r for r in jl(EXP / "jev-five" / "verify" / "refute" / "features.jsonl")}
S = {
    "Jev one": [one[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids],
    "Jev five mean R1": [sum(five[i]["jev"]["round1"][a]["p_reject"] for a in AGENTS) / 5 for i in ids],
    "Claude": [s["p_claude"] for s in sel],
    "Laya one": [s["p_single_laya"] for s in sel],
    "added lines": [feat[i]["added"] for i in ids],
}
trivial = [feat[i]["comment_only"] or feat[i]["added"] == 0 for i in ids]
say("\n== rescoring the 100 (AUC [95% bootstrap])")
subsets = {
    "all 100": [True] * 100,
    "drop REJECTs blamed only on comments": [not (y[i] and cls[ids[i]] == "all comment") for i in range(100)],
    "only REJECTs with a blamed code line (+all A)": [not y[i] or cls[ids[i]] == "has code" for i in range(100)],
    "... and without trivial A": [(not y[i] and not trivial[i]) or (y[i] and cls[ids[i]] == "has code") for i in range(100)],
}
for name, keep in subsets.items():
    idx = [i for i in range(100) if keep[i]]
    yy = [y[i] for i in idx]
    cells = []
    for n, s in S.items():
        ss = [s[i] for i in idx]
        lo, hi = boot(ss, yy)
        cells.append(f"{n} {auc(ss, yy):.3f} [{lo:.2f},{hi:.2f}]")
    say(f"  {name} (R {sum(yy)}, A {len(yy) - sum(yy)}): " + "; ".join(cells))
say("\n  mean score of REJECTs by class of blamed line:")
for c in ("all comment", "include/preproc/inst", "has code"):
    idx = [i for i in range(100) if y[i] and cls[ids[i]] == c]
    say(f"  {c:<22} n {len(idx):>2}: " + ", ".join(f"{n} {sum(S[n][i] for i in idx) / len(idx):.3f}" for n in S))
(HERE / "audit3.log").write_text("\n".join(out) + "\n", encoding="utf-8")
