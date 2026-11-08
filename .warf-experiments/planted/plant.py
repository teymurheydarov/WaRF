"""Build the planted-defect set: gismo6 changes that git history says were fine, each reviewed twice,
once as it was (clean) and once with one planted defect (planted). The right answer is known.

Base changes (from the Laya sweep, ../laya-sweep/):
  * gismo6, phases A and B (not the shallow-clone snapshots), label APPROVE (never blamed by a later fix in >= 180 days);
  * a C/C++ file (.h .hpp .cpp .cc .cxx .c), one per commit, not one of the 100 commits of
    ../laya-five/selection.jsonl;
  * Laya reads the whole change: the sweep's state is at most 940 tokens (its window is 959);
  * the change adds at least one code line that a mutation below applies to.

Mutations, one per base change, applied to one added code line (no preprocessor line or comment,
not inside a /* */ block, the operator outside string literals and a trailing comment) and to the same text in any function body WaRF appends
after the diff (enrich_patch), so the two never disagree:
  ==  <-> !=          &&  <-> ||          ' < ' <-> ' <= '   ' > ' <-> ' >= '  (conditions only)
  ' + ' <-> ' - '     += <-> -=           ++ <-> --          return true; <-> return false;
Each is a one-token change that alters what the code does.

    python .warf-experiments/planted/plant.py      # writes items.jsonl and plant.log

The pick is seeded and stops at N_BASE base changes."""
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "laya-five"))
from run_five import PLAN, has_code, prepare  # noqa: E402
from warf.context_extractor import _SEPARATOR  # noqa: E402

N_BASE = 60
ROOM = 940          # Laya's 959-token state window, less a margin; one short question
CPP = {".h", ".hpp", ".cpp", ".cc", ".cxx", ".c"}
LITERAL = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'")
COND = re.compile(r"\b(if|for|while|return|assert|GISMO_ASSERT|GISMO_ENSURE)\b|\?")
SWAPS = [
    ("eq", r"==", "!="), ("ne", r"!=", "=="),
    ("and", r" && ", " || "), ("or", r" \|\| ", " && "),     # spaced: not an rvalue reference T&&
    ("lt", r" < ", " <= "), ("le", r" <= ", " < "), ("gt", r" > ", " >= "), ("ge", r" >= ", " > "),
    ("plus", r" \+ ", " - "), ("minus", r" - ", " + "),
    ("plus_eq", r"\+=", "-="), ("minus_eq", r"-=", "+="),
    ("true", r"return true;", "return false;"), ("false", r"return false;", "return true;"),
    ("inc", r"\+\+", "--"), ("dec", r"--", "++"),
]
out_log = []


def say(s=""):
    out_log.append(s)
    print(s)


def options(line: str) -> list[tuple[str, str]]:
    """(operator, mutated line) for every mutation that applies once to the code of this added line,
    outside its string and character literals and any trailing // comment."""
    body = line[1:]
    s = body.strip()
    if not s or s.startswith(("#", "//", "/*", "*")) or "/*" in body:
        return []
    code = LITERAL.sub(lambda m: "_" * len(m.group(0)), body)     # same length, literals blanked
    code = code.split("//", 1)[0]
    if "template" in code or "<<" in code or ">>" in code:
        return []
    found = []
    for name, pat, rep in SWAPS:
        if name in ("lt", "le", "gt", "ge") and not COND.search(code):
            continue
        if name in ("minus", "minus_eq") and "->" in code:
            continue
        if name in ("plus", "minus", "plus_eq", "minus_eq") and ('"' in body or "string" in body):
            continue                    # string concatenation: the mutant would not compile
        hits = list(re.finditer(pat, code))
        if len(hits) == 1:
            a, b = hits[0].span()
            found.append((name, "+" + body[:a] + rep + body[b:]))
    return found


def candidates(code: str) -> list[tuple[str, str, str]]:
    """(operator, original line, mutated line) for added code lines outside comments that occur once
    in the diff. The same text in the function bodies enrich_patch appended is mutated with it."""
    patch = code.split(_SEPARATOR, 1)[0]
    out, in_comment = [], False
    for ln in patch.splitlines():
        if ln.startswith(("+++", "---", "@@", "diff ", "index ", "new file", "deleted file")):
            continue
        text = ln[1:]
        was_comment = in_comment
        if in_comment:
            in_comment = "*/" not in text
        elif "/*" in text and "*/" not in text.split("/*", 1)[1]:
            in_comment = True
        if was_comment or in_comment or not ln.startswith("+") or patch.count("\n" + ln + "\n") != 1:
            continue
        for name, mutated in options(ln):
            out.append((name, ln, mutated))
    return out


def apply(code: str, original: str, mutated: str) -> str:
    patch, sep, block = code.partition(_SEPARATOR)
    patch = patch.replace("\n" + original + "\n", "\n" + mutated + "\n", 1)
    return patch + sep + block.replace(original[1:], mutated[1:])


used = {json.loads(line)["commit"] for line in (EXP / "laya-five" / "selection.jsonl").open(encoding="utf-8")}
labels = {}
for r in map(json.loads, (EXP / "laya-sweep" / "labels.jsonl").open(encoding="utf-8")):
    labels[(r["commit"], r["file"])] = r["label"]
pool = []
with (EXP / "laya-sweep" / "sessions.jsonl").open(encoding="utf-8") as f:
    for line in f:
        w = json.loads(line)["sweep"]
        if ("gismo6" in w["repo"] and w["phase"] in ("A", "B") and Path(w["file"]).suffix.lower() in CPP
                and labels.get((w["commit"], w["file"])) == "APPROVE" and w["commit"] not in used
                and w["laya"]["usage"]["state_tokens"] <= ROOM):
            pool.append(w)
say(f"pool: {len(pool)} never-fixed gismo6 C/C++ changes in phases A/B that Laya reads whole, outside the 100")

plan = {e["sha"]: e for e in map(json.loads, PLAN.open(encoding="utf-8"))}
rng = random.Random(20261104)
rng.shuffle(pool)
items, taken, seen_lines, ops = [], set(), set(), {}
for w in pool:
    if len(items) == 2 * N_BASE:
        break
    if w["commit"] in taken:
        continue
    code, domain, context, enrich_error = prepare(plan[w["commit"]], w["file"])
    if enrich_error or not has_code(code.split(_SEPARATOR, 1)[0]):
        continue
    # one base change per added line: copies of a change on other branches would repeat an item
    cands = [c for c in candidates(code) if c[1][1:].strip() not in seen_lines]
    if not cands:
        continue
    by_op = {}
    for c in cands:
        by_op.setdefault(c[0], []).append(c)
    rarest = min(by_op, key=lambda o: (ops.get(o, 0), o))   # spread the operators
    name, original, mutated = rng.choice(by_op[rarest])
    ops[name] = ops.get(name, 0) + 1
    taken.add(w["commit"])
    seen_lines |= {ln[1:].strip() for ln in code.split(_SEPARATOR, 1)[0].splitlines()
                   if ln.startswith("+") and not ln.startswith("+++")}
    base =f"{w['commit'][:7]}:{Path(w['file']).name}"
    planted = apply(code, original, mutated)
    assert planted != code and original not in planted.split(_SEPARATOR, 1)[0].split("\n")
    common = {"base": base, "commit": w["commit"], "file": w["file"], "domain": domain, "context": context}
    items.append({**common, "id": base + ":clean", "kind": "clean", "code": code})
    items.append({**common, "id": base + ":planted", "kind": "planted", "code": planted,
                  "operator": name, "original": original, "mutated": mutated})

with (HERE / "items.jsonl").open("w", encoding="utf-8") as out:
    for it in items:
        out.write(json.dumps(it, ensure_ascii=False) + "\n")
say(f"base changes: {len(items) // 2}; operators: " + ", ".join(f"{k} {v}" for k, v in sorted(ops.items())))
say(f"domains: " + ", ".join(f"{d} {sum(it['domain'] == d for it in items) // 2}" for d in sorted({it['domain'] for it in items})))
say(f"state chars: median {sorted(len(it['code']) for it in items)[len(items) // 2]}, max {max(len(it['code']) for it in items)}")
(HERE / "plant.log").write_text("\n".join(out_log) + "\n", encoding="utf-8")
