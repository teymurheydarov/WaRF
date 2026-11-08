"""Independent re-check of the labels-metrics audit. Pure Python, stored data + local git only.
Writes nothing outside this folder (cache file feats.json here)."""
import json, math, random, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
OUT = open(HERE / "v1.log", "w", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s); OUT.write(s + "\n"); OUT.flush()


def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def auc_rank(score, pos):
    """Mann-Whitney via midranks (independent of the pairwise loop used by the scripts)."""
    idx = sorted(range(len(score)), key=lambda i: score[i])
    ranks = [0.0] * len(score)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and score[idx[j + 1]] == score[idx[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[idx[k]] = r
        i = j + 1
    n1 = sum(pos); n0 = len(pos) - n1
    R1 = sum(r for r, t in zip(ranks, pos) if t)
    return (R1 - n1 * (n1 + 1) / 2) / (n1 * n0)


def auc_pair(score, pos):
    P = [s for s, t in zip(score, pos) if t]; N = [s for s, t in zip(score, pos) if not t]
    return sum((p > q) + 0.5 * (p == q) for p in P for q in N) / (len(P) * len(N))


def boot_diff(s1, s2, pos, n=2000, seed=17):
    P = [i for i, t in enumerate(pos) if t]; N = [i for i, t in enumerate(pos) if not t]
    rng = random.Random(seed); d = []
    for _ in range(n):
        idx = [rng.choice(P) for _ in P] + [rng.choice(N) for _ in N]
        yy = [pos[i] for i in idx]
        d.append(auc_rank([s1[i] for i in idx], yy) - auc_rank([s2[i] for i in idx], yy))
    d.sort()
    return auc_rank(s1, pos) - auc_rank(s2, pos), d[int(0.025 * n)], d[int(0.975 * n)]


sel = jl(EXP / "laya-five/selection.jsonl")
ids = [s["id"] for s in sel]
y = [s["label"] == "REJECT" for s in sel]
say("== A. headline AUCs, recomputed with midranks")
say("n", len(sel), "REJECT", sum(y), "distinct ids", len(set(ids)), "distinct commits", len({s["commit"] for s in sel}))
say("pairs ordered REJECT,APPROVE:", all(sel[2 * k]["label"] == "REJECT" and sel[2 * k + 1]["label"] == "APPROVE" for k in range(50)))

one = {r["jev"]["id"]: r for r in jl(EXP / "jev-five/sessions_one.jsonl")}
five = {r["jev"]["id"]: r for r in jl(EXP / "jev-five/sessions_five.jsonl")}
std = {r["jev"]["id"]: r for r in jl(EXP / "jev-five/sessions_standard.jsonl")}
lf = {r["five"]["id"]: r for r in jl(EXP / "laya-five/sessions.jsonl")}
AG = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
key = json.load(open(EXP / "laya-near-chance/claude-review/key.json", encoding="utf-8"))
keyd = {k["id"]: k for k in key}
res = json.load(open(EXP / "laya-near-chance/laya-probe/claude_review_result.json", encoding="utf-8"))
cl = {}
for b in res["reviews"]:
    for it in b["items"]:
        if it["id"] in cl:
            say("DUPLICATE claude id", it["id"])
        cl[it["id"]] = it["p_defect"]
say("claude items", len(cl), "key items", len(key))

# label agreement across sources
bad = 0
for s in sel:
    i = s["id"]
    srcs = [one[i]["jev"]["label"], five[i]["jev"]["label"], std[i]["jev"]["label"], lf[i]["five"]["label"], keyd[i]["label"]]
    if any(x != s["label"] for x in srcs):
        bad += 1
    if (one[i]["jev"]["commit"], one[i]["jev"]["file"]) != (s["commit"], s["file"]) or (keyd[i]["commit"], keyd[i]["file"]) != (s["commit"], s["file"]):
        bad += 1
    if abs(cl[i] - s["p_claude"]) > 1e-12 or abs(keyd[i]["p_laya"] - s["p_single_laya"]) > 1e-12:
        bad += 1
say("label/commit/score mismatches across sessions_one/five/standard/laya-five/key/claude:", bad)

# labels.jsonl join (stream)
want = {(s["commit"], s["file"]): s for s in sel}
lab = {}
gis_rows = {}
for line in open(EXP / "laya-sweep/labels.jsonl", encoding="utf-8"):
    if "gismo6" not in line:
        continue
    r = json.loads(line)
    k = (r["commit"], r["file"])
    if k in want:
        if k in lab:
            say("duplicate labels row", k)
        lab[k] = r
    kd = {(kk["commit"], kk["file"]): kk for kk in key}
    break
kd = {(kk["commit"], kk["file"]): kk for kk in key}
for line in open(EXP / "laya-sweep/labels.jsonl", encoding="utf-8"):
    if "gismo6" not in line:
        continue
    r = json.loads(line)
    k = (r["commit"], r["file"])
    if k in want:
        lab[k] = r
    if k in kd:
        gis_rows[k] = r
say("labels.jsonl rows found for selection:", len(lab), "agree:", sum(lab[k]["label"] == want[k]["label"] for k in lab))
say("labels.jsonl rows found for key (gismo6):", len(gis_rows), "of", sum("gismo6" in k["repo"] for k in key),
    "agree:", sum(gis_rows[k]["label"] == kd[k]["label"] for k in gis_rows))

scores = {
    "Jev one": [one[i]["jev"]["round1"]["JEV"]["p_reject"] for i in ids],
    "Jev five R1 mean": [sum(five[i]["jev"]["round1"][a]["p_reject"] for a in AG) / 5 for i in ids],
    "Jev five final mean": [sum((five[i]["jev"]["round2"].get(a) or five[i]["jev"]["round1"][a])["p_reject"] for a in AG) / 5 for i in ids],
    "Jev standard mean": [sum(v["p_reject"] for v in std[i]["jev"]["round1"].values()) / len(std[i]["jev"]["round1"]) for i in ids],
    "Laya one": [s["p_single_laya"] for s in sel],
    "Laya five R1": [sum(lf[i]["five"]["round1"][a]["p_reject"] for a in AG) / 5 for i in ids],
    "Claude": [cl[i] for i in ids],
    "patch chars": [s["patch_chars"] for s in sel],
    "state tokens": [s["state_tokens"] for s in sel],
}
for n, sc in scores.items():
    a1, a2 = auc_rank(sc, y), auc_pair(sc, y)
    say(f"  {n:<22} {a1:.4f} (pairwise {a2:.4f}) distinct {len(set(sc))}")
# sign check: does the jev vote text agree with p_reject?
flip = sum((one[i]["jev"]["round1"]["JEV"]["choice"] == "REJECT") != (one[i]["jev"]["round1"]["JEV"]["p_reject"] > 0.5) for i in ids)
say("Jev one: choice inconsistent with p_reject>0.5:", flip)
# does reasoning text p(REJECT) agree with stored p_reject
mm = 0
for i in ids:
    t = one[i]["votes"][0]["reasoning"]
    m = re.search(r"p\(REJECT\)=([0-9.]+)", t)
    if not m or abs(float(m.group(1)) - one[i]["jev"]["round1"]["JEV"]["p_reject"]) > 0.006:
        mm += 1
say("Jev one: vote-text p(REJECT) differs from stored p_reject by >0.006:", mm)

# ------------------------------------------------------------------ B. diff features
plan = {}
for line in open(EXP / "laya-sweep/plan.jsonl", encoding="utf-8"):
    if "gismo6" in line:
        e = json.loads(line)
        plan[e["sha"]] = e


def git(gd, *a):
    p = subprocess.run(["git", "--git-dir", gd, "-c", "core.quotePath=false", *a], capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:300])
    return p.stdout.decode("utf-8", "replace").replace("\r\n", "\n")


def comment_mask(text):
    """For each line: True if the line has no non-whitespace character outside comments/blank-punct."""
    lines = text.split("\n"); out = []; inblock = False
    for ln in lines:
        code = []; i = 0; instr = None
        while i < len(ln):
            c = ln[i]
            if inblock:
                if ln.startswith("*/", i):
                    inblock = False; i += 2
                else:
                    i += 1
                continue
            if instr:
                code.append(c)
                if c == "\\":
                    if i + 1 < len(ln): code.append(ln[i + 1])
                    i += 2; continue
                if c == instr: instr = None
                i += 1; continue
            if ln.startswith("//", i):
                break
            if ln.startswith("/*", i):
                inblock = True; i += 2; continue
            if c in "\"'":
                instr = c
            code.append(c); i += 1
        out.append(not re.search(r"\w", "".join(code)))
    return out


def cosmetic(text):
    s = text.strip()
    if not re.search(r"\w", s): return True
    return s.startswith(("//", "/*", "*/")) or (s.startswith("*") and s[1:2] in ("", " ", "\t", "*"))


cache_p = HERE / "feats.json"
cache = {}
for s in sel:
    if s["id"] in cache:
        continue
    e = plan[s["commit"]]
    full = git(e["git_dir"], "show", "-M", "--no-color", "-U0", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/", "--format=", s["commit"])
    parts = re.split(r"(?m)^(?=diff --git )", full)
    hits = [p for p in parts if re.search(r"(?m)^\+\+\+ b/" + re.escape(s["file"]) + "$", p)
            or (p.startswith("diff --git ") and p.split(chr(10), 1)[0].endswith(" b/" + s["file"]))]
    assert len(hits) == 1, (s["id"], len(hits))
    d = hits[0]
    add = [l[1:] for l in d.split("\n") if l.startswith("+") and not l.startswith("+++")]
    rem = [l[1:] for l in d.split("\n") if l.startswith("-") and not l.startswith("---")]
    # comment-awareness on the post-image of the file
    try:
        post = git(e["git_dir"], "show", f"{s['commit']}:{s['file']}")
        mask = comment_mask(post)
        # map added lines -> new line numbers
        newnums = []
        for l in d.split("\n"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", l)
            if m:
                st = int(m.group(1)); cnt = int(m.group(2)) if m.group(2) is not None else 1
                newnums += list(range(st, st + cnt))
        add_code_true = sum(1 for n in newnums if 1 <= n <= len(mask) and not mask[n - 1])
    except RuntimeError as ex:
        say("  cannot show post-image", s["id"], str(ex)[:120]); add_code_true = -1
    cache[s["id"]] = {"added": len(add), "removed": len(rem),
                      "added_nonblank": sum(1 for l in add if l.strip()),
                      "added_noncosmetic": sum(1 for l in add if not cosmetic(l)),
                      "added_code_true": add_code_true}
json.dump(cache, open(cache_p, "w", encoding="utf-8"))
F = {k: [cache[i][k] for i in ids] for k in cache[ids[0]]}
say("\n== B. size features AUC (REJECT positive)")
for k, v in F.items():
    say(f"  {k:<18} {auc_rank(v, y):.4f}   median R {sorted(x for x, t in zip(v, y) if t)[25]}  median A {sorted(x for x, t in zip(v, y) if not t)[25]}")
say("  any noncosmetic added (binary)", round(auc_rank([float(x > 0) for x in F['added_noncosmetic']], y), 4))
triv = [F["added_noncosmetic"][j] == 0 for j in range(100)]
triv2 = [F["added_code_true"][j] == 0 for j in range(100)]
say("  items with 0 noncosmetic added lines: R", sum(t and yy for t, yy in zip(triv, y)), "A", sum(t and not yy for t, yy in zip(triv, y)))
say("  items with 0 true-code added lines (block-comment aware): R", sum(t and yy for t, yy in zip(triv2, y)), "A", sum(t and not yy for t, yy in zip(triv2, y)))
say("  items adding nothing:", sum(x == 0 for x in F["added"]), "labels", [sel[j]["label"] for j in range(100) if F["added"][j] == 0])

# REJECTs with 0 true-code added lines? B-SZZ blames non-cosmetic deleted lines, so a REJECT needs >=1 noncosmetic added line
say("  REJECTs with 0 noncosmetic added lines (should be 0 if blame is consistent):", sum(t and yy for t, yy in zip(triv, y)))

say("\n== C. Spearman with added lines")


def rank(v):
    idx = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and v[idx[j + 1]] == v[idx[i]]: j += 1
        for k in range(i, j + 1): r[idx[k]] = (i + j) / 2
        i = j + 1
    return r


def pear(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    return sum((x - ma) * (z - mb) for x, z in zip(a, b)) / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((z - mb) ** 2 for z in b))


for n in ("Claude", "Jev one", "Jev five R1 mean", "Laya one"):
    say(f"  {n:<18} rho(added) {pear(rank(scores[n]), rank(F['added'])):+.3f}  rho(noncosmetic) {pear(rank(scores[n]), rank(F['added_noncosmetic'])):+.3f}")

say("\n== D. trivial APPROVEs (0 noncosmetic added lines)")
for n in ("Claude", "Jev one", "Jev five R1 mean", "Laya one"):
    sc = scores[n]
    ta = [sc[j] for j in range(100) if triv[j] and not y[j]]
    oa = [sc[j] for j in range(100) if not triv[j] and not y[j]]
    rr = [sc[j] for j in range(100) if y[j]]
    say(f"  {n:<18} mean trivialA {sum(ta)/len(ta):.3f} (n {len(ta)}) otherA {sum(oa)/len(oa):.3f} (n {len(oa)}) R {sum(rr)/len(rr):.3f}")
keep = [j for j in range(100) if not (triv[j] and not y[j])]
yk = [y[j] for j in keep]
say("  without trivial APPROVEs: n", len(keep), "R", sum(yk))
allsc = dict(scores); allsc["added"] = F["added"]; allsc["added_noncosmetic"] = F["added_noncosmetic"]
for n in ("Claude", "Jev one", "Jev five R1 mean", "Jev five final mean", "Laya one", "added", "added_noncosmetic"):
    say(f"    {n:<20} {auc_rank([allsc[n][j] for j in keep], yk):.4f}")
for a, b in (("Claude", "Jev one"), ("Claude", "Jev five R1 mean")):
    d, lo, hi = boot_diff(allsc[a], allsc[b], y)
    d2, lo2, hi2 = boot_diff([allsc[a][j] for j in keep], [allsc[b][j] for j in keep], yk)
    say(f"  {a} - {b}: all {d:+.3f} [{lo:+.3f},{hi:+.3f}]  w/o trivial {d2:+.3f} [{lo2:+.3f},{hi2:+.3f}]")
# Also: within non-trivial items only, AUC of noncosmetic added lines vs Claude/Jev
# And partial: Claude vs Jev on items that both add code
json.dump({"scores": scores, "F": F, "y": y, "ids": ids,
           "lab": {s["id"]: lab[(s["commit"], s["file"])] for s in sel}}, open(HERE / "v1_data.json", "w", encoding="utf-8"))
say("done")
