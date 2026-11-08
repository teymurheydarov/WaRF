"""Build a harder answer key, where a lenient reviewer pays for its leniency (the next step named in
../evidence-set/README.md): on that set every seat of every arm caught 49 of 50 plants, so leniency
cost nothing.

Two changes from ../evidence-set/build_set.py:

1. Clean versions are screened without Claude, before any reviewer runs. A base is kept only if every
   added, non-blank line of the reviewed file is still attributed to that commit by
   `git blame origin/dev` (gismo dev as of 2026-10-01). Nothing it added was later changed or fixed.
   Bases are committed between 2017-01-01 and 2026-04-01, so they have at least six months of later
   history. Survival is evidence, not proof: a latent defect can survive.

2. The plants are subtler and type-correct by construction:

     wrong_var     one identifier replaced by a sibling from the same code: its usual partner for a
                   single letter (i/j, u/v, x/y, m/n, p/q, r/c), else the same length at Hamming
                   distance 1 (du -> dv, x0 -> x1, m_u -> m_v), in use within 15 lines on the new side
                   of the diff (so likely in scope); declarations are left alone
     accumulate    one `+=` becomes `=`, so an accumulation keeps only its last term
     first_second  `.first` <-> `.second`
     plus_one      a binary `x + 1` loses its `+ 1`

   Applied as in build_set.py: to one added code line outside comments and string literals, and to the
   same text in the appended function bodies. wrong_var is capped at half of the candidates.

Bases used by ../evidence-set/ are excluded, so the two sets are disjoint.

    python .warf-experiments/hard-set/build_hard.py     # writes candidates.jsonl and build.log"""
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "evidence-set"))
from build_set import GISMO, apply, git, masked, one, prepare  # noqa: E402
from warf.context_extractor import _SEPARATOR  # noqa: E402

SINCE, UNTIL = "2017-01-01", "2026-04-01"
MAX_CHARS = 20000
N_CANDIDATES = 200
SCOPE = 15                   # a wrong_var sibling must appear within this many diff lines
OPS = ("wrong_var", "accumulate", "first_second", "plus_one")
CAP = {"wrong_var": N_CANDIDATES // 2}
IDENT = re.compile(r"\b[A-Za-z_]\w*\b")
NOT_VARS = {
    "if", "else", "for", "while", "do", "return", "switch", "case", "break", "continue", "const", "auto",
    "static", "inline", "virtual", "typename", "template", "class", "struct", "public", "private",
    "protected", "new", "delete", "this", "true", "false", "nullptr", "sizeof", "void", "bool", "int",
    "short", "long", "unsigned", "signed", "char", "float", "double", "size_t", "index_t", "short_t",
    "real_t", "T", "Scalar", "std", "math", "gismo", "using", "namespace", "operator", "default",
}
out_log = []


def say(s=""):
    out_log.append(s)
    print(s)


PAIRS = {"i": "j", "j": "i", "u": "v", "v": "u", "x": "y", "y": "x", "m": "n", "n": "m", "p": "q", "q": "p",
         "r": "c", "c": "r"}       # single letters swap only with their usual partner


def siblings(name: str, pool: set) -> list:
    if len(name) == 1:
        return [PAIRS[name]] if PAIRS.get(name) in pool else []
    return sorted(o for o in pool if len(o) == len(name) and o != name
                  and sum(a != b for a, b in zip(o, name)) == 1 and o not in NOT_VARS and not o[0].isupper())


def options(line: str, pool: set) -> list:
    body = line[1:]
    s = body.strip()
    if not s or s.startswith(("#", "//", "/*", "*")) or "/*" in body:
        return []
    code = masked(body)
    found = []
    for m in IDENT.finditer(code):
        name = m.group(0)
        if name in NOT_VARS or name[0].isupper() or len(re.findall(rf"\b{re.escape(name)}\b", code)) != 1:
            continue
        a, b = m.span()
        before, after = code[:a].rstrip(), code[b:].lstrip()
        if before.endswith(("::", ".", "->", "<")) or after.startswith(("(", "<", "::")):
            continue                 # a member, a call, a type or a template argument: not a variable
        if re.search(r"[\w*&]$", before):
            continue                 # a declaration ("index_t i", "T * x"): renaming it changes nothing
        for sib in siblings(name, pool):
            found.append(("wrong_var", "+" + body[:a] + sib + body[b:]))
            break                    # one sibling per name keeps the choice reproducible
    m = one(r"\+=", code)
    if m and not re.search(r"<<|>>|\"", code):
        a, b = m.span()
        found.append(("accumulate", "+" + body[:a] + "=" + body[b:]))
    m = one(r"\.(first|second)\b", code)
    if m:
        a, b = m.span()
        found.append(("first_second", "+" + body[:a] + (".second" if m.group(1) == "first" else ".first") + body[b:]))
    m = one(r"(?<=[\w\)\]])\s*\+\s*1\b(?!\.)", code)
    if m:
        a, b = m.span()
        found.append(("plus_one", "+" + body[:a] + body[b:]))
    return found


def candidates(code: str) -> list:
    """(operator, original line, mutated line), as in build_set.candidates, with this file's plants."""
    patch, _, block = code.partition(_SEPARATOR)
    block_lines = block.split("\n")
    lines = patch.splitlines()
    out, in_comment = [], False
    for k, ln in enumerate(lines):
        if ln.startswith(("+++", "---", "@@", "diff ", "index ", "new file", "deleted file")):
            continue
        text = ln[1:]
        was = in_comment
        if in_comment:
            in_comment = "*/" not in text
        elif "/*" in text and "*/" not in text.split("/*", 1)[1]:
            in_comment = True
        if was or in_comment or not ln.startswith("+") or patch.count("\n" + ln + "\n") != 1:
            continue
        if block_lines.count(text) > 1:
            continue
        # a sibling must be in use nearby on the new side (context or added lines within SCOPE lines),
        # so that it is likely in scope; never from the diff header or removed lines
        near = [x[1:] for x in lines[max(0, k - SCOPE):k + SCOPE + 1]
                if x[:1] in (" ", "+") and not x.startswith("+++")]
        pool = {t for x in near for t in IDENT.findall(masked(x))}
        for name, mutated in options(ln, pool):
            out.append((name, ln, mutated))
    return out


def survives(sha: str, path: str, code: str) -> bool:
    """Every added non-blank line of the file's diff is still blamed on this commit at origin/dev."""
    added = [ln[1:] for ln in code.split(_SEPARATOR, 1)[0].splitlines()
             if ln.startswith("+") and not ln.startswith("+++") and ln[1:].strip()]
    try:
        blame = git(str(GISMO / ".git"), "blame", "-l", "-s", "origin/dev", "--", path)
    except RuntimeError:
        return False                  # the file was moved or deleted since
    kept = [row.split(") ", 1)[1] for row in blame.splitlines() if row.startswith(sha) and ") " in row]
    remaining = list(kept)
    for line in added:
        if line in remaining:
            remaining.remove(line)
        else:
            return False
    return True


def main() -> None:
    used = {json.loads(line)["commit"] for line in (EXP / "evidence-set" / "candidates.jsonl").open(encoding="utf-8")}
    commits = git(str(GISMO / ".git"), "log", "origin/dev", "--no-merges", f"--since={SINCE}", f"--until={UNTIL}",
                  "--format=%H%x09%ad%x09%s", "--date=short", "--", "src/*.h", "src/*.hpp", "src/*.cpp").splitlines()
    reverted = set(re.findall(r"This reverts commit ([0-9a-f]{40})",
                              git(str(GISMO / ".git"), "log", "origin/dev", f"--since={SINCE}", "--format=%B")))
    say(f"{len(commits)} commits {SINCE}..{UNTIL}; {len(used)} used by ../evidence-set are excluded")
    rng = random.Random(20261105)
    rng.shuffle(commits)
    base = {"git_dir": str(GISMO / ".git"), "worktree": str(GISMO)}
    picked, ops, seen_lines = [], {}, set()
    skipped = {"used": 0, "revert": 0, "too long": 0, "changed later": 0, "no plant": 0}
    for row in commits:
        if len(picked) == N_CANDIDATES:
            break
        sha, date, subject = row.split("\t", 2)
        if sha in used:
            skipped["used"] += 1
            continue
        if subject.startswith("Revert") or sha in reverted:
            skipped["revert"] += 1
            continue
        files = [f for f in git(str(GISMO / ".git"), "show", "--format=", "--name-only", "--diff-filter=AM", sha).split()
                 if f.startswith("src/") and f.endswith((".h", ".hpp", ".cpp"))]
        rng.shuffle(files)
        chosen, why = None, "no plant"
        for f in files:
            code, domain, context, enrich_error = prepare({**base, "sha": sha}, f)
            if len(code) > MAX_CHARS:
                why = "too long"
                continue
            cands = [c for c in candidates(code) if c[1][1:].strip() not in seen_lines
                     and ops.get(c[0], 0) < CAP.get(c[0], N_CANDIDATES)]
            if not cands:
                continue
            if not survives(sha, f, code):
                why = "changed later"
                continue
            by_op = {}
            for c in cands:
                by_op.setdefault(c[0], []).append(c)
            rarest = min(by_op, key=lambda o: (ops.get(o, 0), OPS.index(o)))
            chosen = (f, code, domain, context, enrich_error, *rng.choice(by_op[rarest]))
            break
        if chosen is None:
            skipped[why] += 1
            continue
        f, code, domain, context, enrich_error, name, original, mutated = chosen
        planted = apply(code, original, mutated)
        assert planted != code
        ops[name] = ops.get(name, 0) + 1
        seen_lines |= {ln[1:].strip() for ln in code.split(_SEPARATOR, 1)[0].splitlines()
                       if ln.startswith("+") and not ln.startswith("+++")}
        picked.append({"base": f"{sha[:7]}:{Path(f).name}", "commit": sha, "date": date, "subject": subject,
                       "file": f, "domain": domain, "context": context, "enrich_error": enrich_error,
                       "operator": name, "original": original, "mutated": mutated,
                       "code_clean": code, "code_planted": planted})
    with (HERE / "candidates.jsonl").open("w", encoding="utf-8") as out:
        for p in picked:
            out.write(json.dumps(p, ensure_ascii=False) + "\n")
    say(f"candidates: {len(picked)}; operators: " + ", ".join(f"{o} {ops.get(o, 0)}" for o in OPS))
    say("skipped commits: " + ", ".join(f"{k} {v}" for k, v in skipped.items()))
    (HERE / "build.log").write_text("\n".join(out_log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
