"""Where does the planted line land, in C++ terms? For each of the 43 planted never-fixed changes:
read the whole new file at the commit (git show, read-only), find the first added line, and
classify the plant site: inside a comment, macro continuation, file/namespace scope, class scope,
function body, other language. Then join with Jev's and Laya's before/after p(REJECT)."""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

LAYA = Path(r"C:\workdir\warf\WaRF\.warf-experiments\laya-five")
JEV = LAYA.parent / "jev-five"
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(LAYA))
import run_five  # noqa: E402
from run_five import PLAN, prepare  # noqa: E402
from run_laya_sweep import git  # noqa: E402
from warf.context_extractor import extract_changed_lines  # noqa: E402

AG5 = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")


def load(p):
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]


def strip_cpp(text):
    """Replace comments and string/char literals by spaces (keeping newlines); return the
    stripped text and whether the text ends inside a block comment."""
    out, i, n = [], 0, len(text)
    in_block = False
    while i < n:
        c = text[i]
        if in_block:
            if text.startswith("*/", i):
                in_block = False
                out.append("  ")
                i += 2
            else:
                out.append("\n" if c == "\n" else " ")
                i += 1
        elif text.startswith("/*", i):
            in_block = True
            out.append("  ")
            i += 2
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append(" " * (min(j + 1, n) - i))
            i = min(j + 1, n)
        else:
            out.append(c)
            i += 1
    return "".join(out), in_block


def scope_at(stripped):
    """Innermost brace scope at the end of `stripped`: list of kinds, outermost first."""
    # drop preprocessor lines
    lines = [("" if l.lstrip().startswith("#") else l) for l in stripped.split("\n")]
    s = "\n".join(lines)
    stack, last = [], 0
    for m in re.finditer(r"[{}]", s):
        if m.group() == "{":
            head = s[max(0, m.start() - 300):m.start()]
            head = re.split(r"[;{}]", head)[-1]
            h = " ".join(head.split())
            if re.search(r"\bnamespace\b", h) or re.search(r'\bextern\s*$', h):
                kind = "namespace"
            elif re.search(r"\b(class|struct|union)\b", h) and not re.search(r"\)\s*(const)?\s*$", h):
                kind = "class"
            elif re.search(r"\benum\b", h):
                kind = "enum"
            elif re.search(r"\)\s*(const|override|final|noexcept|mutable|->\s*[\w:<>]+|\s)*$", h) or re.search(r"\b(else|do|try)\s*$", h) \
                    or re.search(r"\)\s*:\s*[\w:<>,\s()]*$", h):
                kind = "function"
            elif re.search(r"=\s*$", h) or re.search(r"[\w>]\s*$", h) and stack and stack[-1] in ("function", "init"):
                kind = "init"
            else:
                kind = "other"
            stack.append(kind)
        else:
            if stack:
                stack.pop()
    return stack


sel = load(LAYA / "selection.jsonl")
plan = {e["sha"]: e for e in map(json.loads, PLAN.open(encoding="utf-8"))}
J1 = {r["jev"]["id"]: r for r in load(JEV / "sessions_one.jsonl")}
J5 = {r["jev"]["id"]: r for r in load(JEV / "sessions_five.jsonl")}
L5 = {r["five"]["id"]: r for r in load(LAYA / "sessions.jsonl")}
C1 = {(r["jev"]["id"], r["jev"]["plant"]): r for r in load(JEV / "controls_one.jsonl")}
C5 = {(r["jev"]["id"], r["jev"]["plant"]): r for r in load(JEV / "controls_five.jsonl")}
LC = {(r["five"]["id"], r["five"]["plant"]): r for r in load(LAYA / "controls.jsonl")}

rows = []
for s in sel:
    if (s["id"], "null dereference") not in C1:
        continue
    e = plan[s["commit"]]
    code, domain, context, _ = prepare(e, s["file"])
    m = run_five.ADDED.search(code)
    first = m.group(1)
    newfile = git(e["git_dir"], "show", f"{s['commit']}:{s['file']}", cwd=e["worktree"])
    lines = newfile.split("\n")
    ln = extract_changed_lines(code.split("\n" + "\u2500" * 60)[0])[0]
    if lines[ln - 1] != first:
        cand = [k + 1 for k, l in enumerate(lines) if l == first]
        ln = cand[0] if cand else ln
    upto = "\n".join(lines[:ln])
    if s["file"].endswith(".py"):
        kind, stack, in_comment = "python file", [], False
    else:
        stripped, in_comment = strip_cpp(upto)
        stack = scope_at(stripped)
        if in_comment:
            kind = "inside /* */ comment"
        elif first.rstrip().endswith("\\"):
            kind = "macro continuation"
        elif "function" in stack:
            kind = "function body"
        elif stack and stack[-1] in ("class",):
            kind = "class scope"
        elif stack and stack[-1] in ("init", "other", "enum"):
            kind = f"{stack[-1]} braces"
        else:
            kind = "file/namespace scope"
    b1 = J1[s["id"]]["jev"]["round1"]["JEV"]["p_reject"]
    b5 = sum(J5[s["id"]]["jev"]["round1"][a]["p_reject"] for a in AG5) / 5
    bl = sum(L5[s["id"]]["five"]["round1"][a]["p_reject"] for a in AG5) / 5
    row = {"id": s["id"], "file": s["file"], "kind": kind, "stack": stack, "line": ln, "first": first.strip()[:60],
           "jev1_before": b1, "jev5_before": b5, "laya5_before": bl}
    for name in ("null dereference", "BUG comment"):
        row[f"jev1_{name}"] = C1[(s["id"], name)]["jev"]["round1"]["JEV"]["p_reject"]
        row[f"jev5_{name}"] = sum(C5[(s["id"], name)]["jev"]["round1"][a]["p_reject"] for a in AG5) / 5
        row[f"laya5_{name}"] = sum(LC[(s["id"], name)]["five"]["round1"][a]["p_reject"] for a in AG5) / 5
    rows.append(row)

print(f"{len(rows)} plant sites")
for r in rows:
    print(f"  {r['id']} {r['file'][-42:]:<42} L{r['line']:<5} {r['kind']:<22} {'/'.join(r['stack'])[:30]:<30} "
          f"Jev1 {r['jev1_before']:.2f}->{r['jev1_null dereference']:.2f}  | {r['first']}")
groups = defaultdict(list)
for r in rows:
    groups[r["kind"]].append(r)
print("\nby site kind (mean p(REJECT); Jev one / Jev five mean / Laya five mean):")
for k, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    def mean(key):
        return sum(r[key] for r in g) / len(g)
    print(f"  {k:<22} n={len(g):>2}  null deref: Jev1 {mean('jev1_before'):.2f}->{mean('jev1_null dereference'):.2f}, "
          f"Jev5 {mean('jev5_before'):.2f}->{mean('jev5_null dereference'):.2f}, Laya5 {mean('laya5_before'):.3f}->{mean('laya5_null dereference'):.3f} | "
          f"BUG comment: Jev1 ->{mean('jev1_BUG comment'):.2f}, Jev5 ->{mean('jev5_BUG comment'):.2f}, Laya5 ->{mean('laya5_BUG comment'):.3f}")
low = sorted(rows, key=lambda r: r["jev1_null dereference"])[:5]
print("\nlowest planted Jev-one p(REJECT), null dereference:", [(r["id"], r["kind"], r["jev1_null dereference"]) for r in low])
(OUT / "plant_sites_classified.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
