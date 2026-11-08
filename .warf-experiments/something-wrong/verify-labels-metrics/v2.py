"""Blamed-line classes of the REJECTs, fix timing/authors, subset AUCs, auditor's 15-item exclusion."""
import json, re, subprocess, sys, math, random
from pathlib import Path
HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(HERE))
OUT = open(HERE / "v2.log", "w", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.write(s + "\n"); OUT.flush()


D = json.load(open(HERE / "v1_data.json", encoding="utf-8"))
scores, F, y, ids, lab = D["scores"], D["F"], D["y"], D["ids"], D["lab"]
sel = [json.loads(l) for l in open(EXP / "laya-five/selection.jsonl", encoding="utf-8")]
GD = r"C:\Users\Teymur Heydarov\source\repos\gismo6\.git"


def git(*a):
    p = subprocess.run(["git", "--git-dir", GD, "-c", "core.quotePath=false", *a], capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:300])
    return p.stdout.decode("utf-8", "replace").replace("\r\n", "\n")


def auc(score, pos):
    P = [s for s, t in zip(score, pos) if t]; N = [s for s, t in zip(score, pos) if not t]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))


def comment_mask(text):
    out = []; inblock = False
    for ln in text.split("\n"):
        code = []; i = 0; instr = None
        while i < len(ln):
            c = ln[i]
            if inblock:
                if ln.startswith("*/", i): inblock = False; i += 2
                else: i += 1
                continue
            if instr:
                code.append(c)
                if c == "\\": i += 2; continue
                if c == instr: instr = None
                i += 1; continue
            if ln.startswith("//", i): break
            if ln.startswith("/*", i): inblock = True; i += 2; continue
            if c in "\"'": instr = c
            code.append(c); i += 1
        out.append(not re.search(r"\w", "".join(code)))
    return out


def classify_line(text, is_comment):
    s = text.strip()
    if is_comment: return "comment"
    if re.match(r"#\s*include", s): return "include"
    if s.startswith("#"): return "preproc"
    if re.search(r"TEMPLATE_INST|TEMPLATE_EINST|EXTERN_|^extern\s+template|^template\s+(class|struct)\b|^template\s+\w[\w:<>, ]*\s+\w+\s*\(", s):
        return "instantiation"
    return "code"


def blamed_classes(row, commit):
    # evidence in labels.jsonl: row["lines"] are line numbers of row's file at `commit`
    try:
        txt = git("show", f"{commit}:{row['file']}")
    except RuntimeError as ex:
        return None, str(ex)[:80]
    L = txt.split("\n"); m = comment_mask(txt)
    out = []
    for n in row["lines"]:
        if 1 <= n <= len(L):
            out.append((classify_line(L[n - 1], m[n - 1]), L[n - 1].strip()[:70]))
        else:
            out.append(("out-of-range", ""))
    return out, None


def summary(cls):
    k = {c for c, _ in cls}
    if k <= {"comment"}: return "comment-only"
    if k <= {"comment", "include", "preproc", "instantiation"}: return "plumbing"
    return "has-code"


say("== REJECTs of the 100: blamed line classes")
cnt = {}; R_cls = {}
for s in sel:
    if s["label"] != "REJECT": continue
    row = lab[s["id"]]
    cls, err = blamed_classes(row, s["commit"])
    if cls is None:
        say("  ", s["id"], "ERR", err); continue
    sm = summary(cls); R_cls[s["id"]] = sm; cnt[sm] = cnt.get(sm, 0) + 1
    if sm == "comment-only":
        say("  ", s["id"], sm, [t for _, t in cls][:3])
say("  summary", cnt, "lines field truncated?", sum(len(lab[i]["lines"]) != lab[i]["blamed_lines"] for i in R_cls))

# fixes: days, same author, kinds, subjects
say("\n== fixes behind the 50 REJECTs")
d1 = d7 = same = 0; kinds = {}
for s in sel:
    if s["label"] != "REJECT": continue
    fx = lab[s["id"]]["fixes"]
    f0 = fx[0]
    d1 += f0["days"] <= 1; d7 += f0["days"] <= 7
    a = git("log", "-1", "--format=%ae", s["commit"]).strip()
    b = git("log", "-1", "--format=%ae", f0["fix"]).strip()
    same += a == b
    kinds[f0["kind"]] = kinds.get(f0["kind"], 0) + 1
say(f"  first fix within 1 day {d1}, within 7 days {d7}; same author email {same}; first-fix kinds {kinds}")
lat = [lab[i]["later_days"] for i in ids]
say("  min later_days APPROVE", min(l for l, t in zip(lat, y) if not t), "REJECTs with later_days < 180:", sum(l < 180 for l, t in zip(lat, y) if t))

# subsets
say("\n== AUC on subsets")
names = ["Claude", "Jev one", "Jev five R1 mean", "Jev five final mean", "Laya one"]
allsc = dict(scores); allsc["added"] = F["added"]; allsc["added_noncosmetic"] = F["added_noncosmetic"]
names2 = names + ["added", "added_noncosmetic"]


def sub(keep, title):
    yk = [y[j] for j in keep]
    say(f"  {title}: n {len(keep)} R {sum(yk)} A {len(yk) - sum(yk)}")
    say("    " + "  ".join(f"{n} {auc([allsc[n][j] for j in keep], yk):.3f}" for n in names2))


sub([j for j in range(100) if not (y[j] and R_cls.get(ids[j]) == "comment-only")], "drop comment-only REJECTs")
sub([j for j in range(100) if not y[j] or R_cls.get(ids[j]) == "has-code"], "only has-code REJECTs vs all A")
# auditor's 15: features.jsonl comment_only or nothing added
FJ = {json.loads(l)["id"]: json.loads(l) for l in open(EXP / "jev-five/verify/refute/features.jsonl", encoding="utf-8")}
t15 = [j for j in range(100) if not y[j] and (FJ[ids[j]]["added"] == 0 or FJ[ids[j]]["comment_only"])]
say("  auditor-style trivial (nothing added or comment-only):", len(t15), "all APPROVE:", all(not y[j] for j in t15))
for n in names:
    say(f"    mean {n:<20} on those {sum(allsc[n][j] for j in t15)/len(t15):.3f}")
sub([j for j in range(100) if j not in t15], "drop the 15 auditor-trivial APPROVEs")
t18 = [j for j in range(100) if not y[j] and F["added_noncosmetic"][j] == 0]
say("  18 unblameable APPROVEs, extra 3 beyond the 15:", [(ids[j], FJ[ids[j]]["added"], FJ[ids[j]]["comment_only"]) for j in t18 if j not in t15])
sub([j for j in range(100) if j not in t18], "drop the 18 unblameable APPROVEs")
sub([j for j in range(100) if j not in t18 and not (y[j] and R_cls.get(ids[j]) == "comment-only")],
    "drop 18 unblameable A and comment-only R")
# matched-pair view: pairs where both members have >=1 noncosmetic added line
pk = [k for k in range(50) if F["added_noncosmetic"][2 * k] > 0 and F["added_noncosmetic"][2 * k + 1] > 0]
say(f"\n  pairs where both add a blameable line: {len(pk)}")
for n in names2:
    w = sum((allsc[n][2 * k] > allsc[n][2 * k + 1]) + 0.5 * (allsc[n][2 * k] == allsc[n][2 * k + 1]) for k in pk)
    say(f"    {n:<20} pairs won {w:.1f} of {len(pk)}")
json.dump({"R_cls": R_cls, "t18": [ids[j] for j in t18], "t15": [ids[j] for j in t15]}, open(HERE / "v2_data.json", "w"))
