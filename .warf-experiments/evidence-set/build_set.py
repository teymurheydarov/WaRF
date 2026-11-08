"""Build a small answer key for the evidence-seat test (docs/spec/evidence-seats-test-plan.md): 50 recent
G+Smo changes, each reviewed twice, as committed (clean) and with one planted defect (planted), so
100 reviewed changes with a known right answer.

Bases: non-merge commits on gismo's `origin/dev` (in the gismo6 clone) since 2024-01-01 that change a
C++ file under src/. One file per commit, no reverts and no reverted commits, a state of at most
MAX_CHARS characters. The input is built exactly as WaRF's review path builds it
(../laya-five/run_five.py prepare: `git show -U30`, enrich_patch, detect_domain).

Plants are harder than the one-token operator flips of ../planted/, which one Claude caught 52 of 54
times. Each is applied to one added code line (not a comment, preprocessor line or string literal),
and to the same text in the function bodies WaRF appends after the diff, so the two never disagree:

  swap_ij      (i, j) -> (j, i) in an index or call       rows_cols   .rows() <-> .cols()
  arg_swap     f(a, b) -> f(b, a), two plain identifiers   loop_bound  for (...; i < n; ...) <-> <=
  start_index  for (... i = 0; ...) <-> i = 1              minus_one   drop a "- 1" / "-1"
  drop_stmt    remove an added statement (an assignment, increment or call); the hunk header is
               corrected so the diff stays consistent

The operator is chosen rarest-first among those that apply, so the mix stays even, and dropped
statements, which apply almost everywhere, are capped at a third of the candidates. Whether a plant is
a real defect, compiles, and is visible from the diff is judged separately (check_plants.py), and
plants that fail are replaced from the remaining bases.

    python .warf-experiments/evidence-set/build_set.py     # writes candidates.jsonl and build.log"""
import json
import random
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "laya-five"))
from run_five import INPUT_LABEL, git, prepare  # noqa: E402,F401
from warf.context_extractor import _SEPARATOR  # noqa: E402

GISMO = Path(r"C:\Users\Teymur Heydarov\source\repos\gismo6")
SINCE = "2024-01-01"
MAX_CHARS = 12000
N_CANDIDATES = 120          # more than 50, so that plants rejected by the check can be replaced
DROP_CAP = N_CANDIDATES // 3  # dropped statements apply almost everywhere; keep them to a third
CPP = (".h", ".hpp", ".cpp")
LITERAL = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'")
CALL_SKIP = {"if", "for", "while", "switch", "return", "sizeof", "static_cast", "dynamic_cast",
             "const_cast", "reinterpret_cast", "decltype", "defined", "GISMO_ASSERT", "GISMO_ENSURE",
             "GISMO_ERROR", "std", "typename", "template"}
OPS = ("swap_ij", "rows_cols", "arg_swap", "loop_bound", "start_index", "minus_one", "drop_stmt")
out_log = []


def say(s=""):
    out_log.append(s)
    print(s)


def masked(body: str) -> str:
    """The line's code with literals blanked (same length, by a character no pattern matches) and
    any trailing // comment cut."""
    return LITERAL.sub(lambda m: "\x01" * len(m.group(0)), body).split("//", 1)[0]


def one(pattern: str, code: str):
    hits = list(re.finditer(pattern, code))
    return hits[0] if len(hits) == 1 else None


def options(line: str) -> list[tuple[str, str | None]]:
    """(operator, mutated line or None for a dropped line) for every plant that applies once."""
    body = line[1:]
    s = body.strip()
    if not s or s.startswith(("#", "//", "/*", "*")) or "/*" in body:
        return []
    code = masked(body)
    found = []
    m = one(r"([\(\[]\s*)([ijk])(\s*,\s*)([ijk])(\s*[\)\]])", code)
    if m and m.group(2) != m.group(4):
        a, b = m.span()
        found.append(("swap_ij", "+" + body[:a] + m.group(1) + m.group(4) + m.group(3) + m.group(2) + m.group(5) + body[b:]))
    m = one(r"\.(rows|cols)\(\)", code)
    if m:
        a, b = m.span()
        found.append(("rows_cols", "+" + body[:a] + (".cols()" if m.group(1) == "rows" else ".rows()") + body[b:]))
    m = one(r"\b([a-z_]\w*)\(\s*([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*)\s*\)", code)
    if m and m.group(1) not in CALL_SKIP and m.group(2) != m.group(3) and {m.group(2), m.group(3)} - {"i", "j", "k"}:
        (a2, b2), (a3, b3) = m.span(2), m.span(3)
        found.append(("arg_swap", "+" + body[:a2] + body[a3:b3] + body[b2:a3] + body[a2:b2] + body[b3:]))
    if re.match(r"\s*for\s*\(", code) and ";" in code:
        m = one(r" <= | < ", code)
        if m:
            a, b = m.span()
            found.append(("loop_bound", "+" + body[:a] + (" < " if m.group(0) == " <= " else " <= ") + body[b:]))
        m = one(r"(for\s*\(\s*(?:index_t|int|size_t|unsigned|short_t|unsigned int)?\s*\w+\s*=\s*)([01])(\s*;)", code)
        if m:
            a, b = m.span(2)
            found.append(("start_index", "+" + body[:a] + ("1" if m.group(2) == "0" else "0") + body[b:]))
    m = one(r"(?<=[\w\)\]])\s*-\s*1\b(?!\.)", code)          # binary "x - 1" only, not a unary -1
    if m:
        a, b = m.span()
        found.append(("minus_one", "+" + body[:a] + body[b:]))
    if (s.endswith(";") and "{" not in s and "}" not in s and not s.startswith(("return", "break", "continue", "delete"))
            and re.match(r"(?:this->)?[A-Za-z_][\w\.\->\[\]\(\)]*\s*(?:[+\-*/]?=(?!=)|\+\+|--|\()", s)
            and not re.match(r"(?:const\s+)?(?:[A-Za-z_][\w:<>,\s\*&]*\s+)[A-Za-z_]\w*\s*=", s)):
        found.append(("drop_stmt", None))
    return found


def candidates(code: str) -> list[tuple[str, str, str | None]]:
    """(operator, original line, mutated line) for added code lines outside /* */ blocks that occur
    once in the diff."""
    patch, _, block = code.partition(_SEPARATOR)
    block_lines = block.split("\n")
    out, in_comment = [], False
    for ln in patch.splitlines():
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
        if block_lines.count(text) > 1:      # the same line in another appended function: ambiguous
            continue
        for name, mutated in options(ln):
            out.append((name, ln, mutated))
    return out


def apply(code: str, original: str, mutated: str | None) -> str:
    """The planted version. A dropped line leaves the diff and its function body, and the hunk
    header's new-side count drops by one."""
    patch, sep, block = code.partition(_SEPARATOR)
    if mutated is not None:
        patch = patch.replace("\n" + original + "\n", "\n" + mutated + "\n", 1)
        block_lines = [mutated[1:] if x == original[1:] else x for x in block.split("\n")]
        return patch + sep + "\n".join(block_lines)
    lines = patch.split("\n")
    k = lines.index(original)
    h = max(i for i in range(k) if lines[i].startswith("@@"))
    m = re.match(r"@@ -(\d+(?:,\d+)?) \+(\d+)(?:,(\d+))? @@(.*)", lines[h])
    count = int(m.group(3) if m.group(3) is not None else 1) - 1
    lines[h] = f"@@ -{m.group(1)} +{m.group(2)},{count} @@{m.group(4)}"
    del lines[k]
    block_lines = block.split("\n")
    block = "\n".join(x for x in block_lines if x != original[1:])
    return "\n".join(lines) + sep + block


def main() -> None:
    commits = git(str(GISMO / ".git"), "log", "origin/dev", "--no-merges", f"--since={SINCE}",
                  "--format=%H%x09%ad%x09%s", "--date=short", "--", "src/*.h", "src/*.hpp", "src/*.cpp").splitlines()
    reverted = set(re.findall(r'This reverts commit ([0-9a-f]{40})',
                              git(str(GISMO / ".git"), "log", "origin/dev", f"--since={SINCE}", "--format=%B")))
    say(f"{len(commits)} non-merge commits on origin/dev since {SINCE} touch src/ C++; {len(reverted)} reverted")
    rng = random.Random(20261104)
    rng.shuffle(commits)
    entry_base = {"git_dir": str(GISMO / ".git"), "worktree": str(GISMO)}
    picked, ops, skipped = [], {}, {"revert": 0, "no file": 0, "too long": 0, "no plant": 0, "error": 0}
    seen_lines = set()          # copies of a change on other branches would repeat a plant site
    for row in commits:
        if len(picked) == N_CANDIDATES:
            break
        sha, date, subject = row.split("\t", 2)
        if subject.startswith("Revert") or sha in reverted:
            skipped["revert"] += 1
            continue
        files = [f for f in git(str(GISMO / ".git"), "show", "--format=", "--name-only", "--diff-filter=AM", sha).split()
                 if f.startswith("src/") and f.endswith(CPP)]
        if not files:
            skipped["no file"] += 1
            continue
        rng.shuffle(files)
        chosen = None
        for f in files:
            try:
                code, domain, context, enrich_error = prepare({**entry_base, "sha": sha}, f)
            except Exception:
                skipped["error"] += 1
                continue
            if len(code) > MAX_CHARS:
                skipped["too long"] += 1
                continue
            cands = [c for c in candidates(code) if c[1][1:].strip() not in seen_lines]
            if not cands:
                continue
            by_op = {}
            for c in cands:
                by_op.setdefault(c[0], []).append(c)
            if set(by_op) == {"drop_stmt"} and ops.get("drop_stmt", 0) >= DROP_CAP:
                continue
            rarest = min(by_op, key=lambda o: (ops.get(o, 0), OPS.index(o)))
            name, original, mutated = rng.choice(by_op[rarest])
            chosen = (f, code, domain, context, enrich_error, name, original, mutated)
            break
        if chosen is None:
            skipped["no plant"] += 1
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
    say(f"dates: {min(p['date'] for p in picked)} to {max(p['date'] for p in picked)}; "
        f"after 2026-06-30: {sum(p['date'] > '2026-06-30' for p in picked)}")
    (HERE / "build.log").write_text("\n".join(out_log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
