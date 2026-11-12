"""Lever "context" (../../DEV.md): a "Related code" block of retrieved declarations for every dev item.

For each item (clean and defective, same procedure, no labels or defect text used):
1. identifiers on the changed (+/-) lines, comments and string literals removed; C++ keywords, a fixed stoplist
   of very common names and names shorter than 3 characters dropped; option keys from get*/add*/ask*/set*("key")
   calls kept as quoted strings;
2. one `git grep -n -w` over src/ of gismo6 AT THE ITEM'S OWN COMMIT for all names (option keys: -F "key");
   hits inside the new-side lines the diff already shows are dropped; names hit in more than MAX_FILES files
   are "very common" and dropped;
3. names ordered most specific first (fewest files hit, then longer name); per name up to two declaration-like
   hits (class/typedef/define, function declaration or definition, member/variable declaration, option
   registration), headers preferred; a name without a declaration-like hit gets one plain hit if it is hit in at
   most FALLBACK_FILES files;
4. each hit shown with BEFORE lines above and AFTER below (git show <commit>:<path>), overlapping windows of the
   same file merged; snippets added in name order until the block would pass CAP characters.

gismo6 is read only through git grep / git show at the item's commit. Writes context_items.jsonl
(id, block, names) here.

    python build_context.py [--limit N]"""
import argparse
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ITEMS = HERE.parent.parent / "items.jsonl"
OUT = HERE / "context_items.jsonl"
GISMO6 = r"C:\Users\Teymur Heydarov\source\repos\gismo6"
CAP, MAX_FILES, FALLBACK_FILES, BEFORE, AFTER = 6000, 60, 10, 3, 6

KEYWORDS = set("""alignas alignof and asm auto bitand bitor bool break case catch char char16_t char32_t class compl
const constexpr const_cast continue decltype default delete do double dynamic_cast else enum explicit export extern
false float for friend goto if inline int long mutable namespace new noexcept not nullptr operator or private
protected public register reinterpret_cast return short signed sizeof static static_assert static_cast struct switch
template this thread_local throw true try typedef typeid typename union unsigned using virtual void volatile wchar_t
while override final include define ifdef ifndef endif elif pragma once undef defined NULL""".split())
COMMON = set("""std gismo Eigen index_t real_t size_t unsigned_t ptrdiff_t uint int64_t gsMatrix gsVector gsInfo gsWarn
gsDebug gsDebugVar endl GISMO_ASSERT GISMO_ENSURE GISMO_ERROR GISMO_NO_IMPLEMENTATION GISMO_EXPORT GISMO_UNUSED
GISMO_CLONE_FUNCTION memory unique_ptr shared_ptr make_shared vector string size rows cols resize setZero setOnes
push_back begin end value data Scalar ptr uPtr Ptr Self clone print iterator const_iterator first second row col
transpose dim domainDim targetDim degree basis coefs eval deriv deriv2 Base numElements nPatches patch info
cout cerr ostream swap min max abs sqrt pow at get set reserve clear empty insert find erase front back assert
Zero Identity Constant blockDiag reshape topRows leftCols middleCols middleRows bottomRows rightCols block segment
head tail norm squaredNorm sum dot cross inverse determinant inner outer""".split())
TYPE_END = re.compile(r"[\w>\*&]$")
NOT_TYPE = KEYWORDS - set("""auto bool char char16_t char32_t const constexpr double float inline int long mutable
register short signed static unsigned virtual void volatile wchar_t explicit typename struct class enum union
friend extern""".split())


def git(*args):
    r = subprocess.run(["git", "-C", GISMO6, *args], capture_output=True)
    if r.returncode not in (0, 1):
        raise RuntimeError(f"git {args[0]} failed: {r.stderr.decode('utf-8', 'replace')[:200]}")
    return r.stdout.decode("utf-8", "replace")


def changed_lines(code):
    out, incom = [], False          # incom: inside a /* */ comment (tracked over the changed lines)
    for ln in code.splitlines():
        if ln.startswith(("+++", "---")) or not ln.startswith(("+", "-")):
            continue
        s = ln[1:].strip()
        if incom:
            if "*/" not in s:
                continue
            s, incom = s.split("*/", 1)[1].strip(), False
        s = re.sub(r"/\*.*?\*/", "", s)
        if "/*" in s:
            s, incom = s.split("/*", 1)[0], True
        s = re.sub(r"//.*", "", s).strip()
        if s:
            out.append(s)
    return out


def names_of(code):
    ids, keys = [], []
    for s in changed_lines(code):
        keys += re.findall(r"\b(?:get|ask|add|set)\w*\s*\(\s*\"([A-Za-z][\w.]*)\"", s)
        s = re.sub(r"//.*", "", s)
        s = re.sub(r"/\*.*?\*/", "", s)
        s = re.sub(r"\"(\\.|[^\"\\])*\"", "\"\"", s)
        s = re.sub(r"'(\\.|[^'\\])*'", "''", s)
        ids += re.findall(r"\b[A-Za-z_]\w*\b", s)
    seen, out = set(), []
    for n in ids:
        if n in seen or n in KEYWORDS or n in COMMON or len(n) < 3 or re.fullmatch(r"[A-Z]\d*|_+\w?", n):
            continue
        seen.add(n); out.append(n)
    ks = []
    for k in keys:
        if k not in ks:
            ks.append(k)
    return out, ks


def shown_ranges(code):
    """New-side line ranges the diff already shows (1-based, inclusive)."""
    r = []
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", code, re.M):
        c, d = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        r.append((c, c + d - 1))
    return r


def decl_score(name, line, path, is_key):
    """(score, kind): score 0 = not a declaration; kind 'type', 'func', 'var' or 'key'."""
    s, kind = line.strip(), "var"
    if is_key:
        sc, kind = (3 if re.search(r"\badd\w*\s*\(", s) else 0), "key"
    elif re.search(rf"#\s*define\s+{re.escape(name)}\b", s) or \
            re.search(rf"\b(class|struct|enum|union|typedef|using|namespace)\b[^;{{(]*\b{re.escape(name)}\b", s):
        sc, kind = 4, "type"
    else:
        sc = 0
        for m in re.finditer(rf"\b{re.escape(name)}\b", s):
            pre, post = s[:m.start()].rstrip(), s[m.end():].lstrip()
            if not pre or any(t in pre for t in ("=", "(", "return", ".", "->", "<<", "?", "!", "+", "-", "/")):
                continue
            q = pre[:-2].rstrip() if pre.endswith("::") else pre
            toks = re.sub(r"(\w+<[^<>]*>|\w+)::$", "", pre).split() if pre.endswith("::") else pre.split()
            if not toks or not TYPE_END.search(q) or toks[-1] in NOT_TYPE:
                continue
            if post.startswith("("):
                sc, kind = 3, "func"
            elif re.match(r"(;|=|\[|\{|,|\)|$)", post) and sc < 3:
                sc = 2
    if sc and path.endswith(".h"):
        sc += 1
    elif sc and path.endswith(".hpp"):
        sc += 0.5
    return sc, kind


def build(it, show_cache):
    commit, own = it["commit"], it["file"]
    names, keys = names_of(it["code"])
    shown = shown_ranges(it["code"])
    hits = {}   # name -> [(path, lineno, text, in_shown)]
    inshown = lambda path, no: path == own and any(x <= no <= y for x, y in shown)
    if names:
        args = ["grep", "-n", "-w", "-I"]
        for n in names:
            args += ["-e", n]
        for ln in git(*args, commit, "--", "src").splitlines():
            m = re.match(rf"{commit}:([^:]+):(\d+):(.*)$", ln)
            if not m:
                continue
            path, no, text = m.group(1), int(m.group(2)), m.group(3)
            for n in names:
                if re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", text):
                    hits.setdefault(n, []).append((path, no, text, inshown(path, no)))
    for k in keys:
        for ln in git("grep", "-n", "-F", "-I", "-e", f'"{k}"', commit, "--", "src").splitlines():
            m = re.match(rf"{commit}:([^:]+):(\d+):(.*)$", ln)
            if m:
                hits.setdefault(f'"{k}"', []).append((m.group(1), int(m.group(2)), m.group(3),
                                                       inshown(m.group(1), int(m.group(2)))))
    stem = own.rsplit(".", 1)[0]
    cands = []
    for n, hs in hits.items():
        nfiles = len({h[0] for h in hs if not h[3]})
        if nfiles == 0 or nfiles > MAX_FILES:
            continue
        cands.append((nfiles, -len(n), n, hs))
    cands.sort()

    def distinct(xs, k):
        out = []
        for x in xs:
            if len(out) < k and not any(g[2] == x[2] and abs(g[3] - x[3]) <= BEFORE + AFTER for g in out):
                out.append(x)
        return out

    picks = []   # (name, path, lineno)
    for nfiles, _, n, hs in cands:
        is_key = n.startswith('"')
        sc = [(*decl_score(n.strip('"'), t, p, is_key), p, no, sh) for p, no, t, sh in hs]
        sc = [(a, p, no, sh, kind) for a, kind, p, no, sh in sc]
        # nearest scope first: the reviewed file, then its .h/.hpp/.cpp siblings, then the rest of src/
        scopes = ([x for x in sc if x[1] == own], [x for x in sc if x[1] != own and x[1].rsplit(".", 1)[0] == stem],
                  [x for x in sc if x[1].rsplit(".", 1)[0] != stem])
        good = None
        for k, scope in enumerate(scopes):
            decl = [x for x in scope if x[0] >= 2]
            if decl:
                if all(x[3] for x in decl) and k == 0:
                    # declared on lines the diff shows: for a function or type, show where other files use it
                    # (callers), if few; a variable or member declared there is resolved, its homonyms elsewhere are not
                    isfun = any(x[4] in ("type", "func") for x in decl)
                    use = [x for x in sc if x[1] != own] if isfun else []
                    good = distinct(sorted(use, key=lambda x: (not x[1].endswith(".h"), x[1], x[2])), 2) \
                        if 0 < len({x[1] for x in use}) <= FALLBACK_FILES else []
                else:
                    decl = [x for x in decl if not x[3]]
                    good = distinct(sorted(decl, key=lambda x: (-x[0], x[1], x[2])), 2)
                break
        if good is None and nfiles <= FALLBACK_FILES:   # no declaration found: one plain use, other files first
            use = [x for x in sc if not x[3]]
            good = sorted(use, key=lambda x: (x[1] == own, not x[1].endswith(".h"), x[1], x[2]))[:1]
        picks += [(n, x[1], x[2]) for x in (good or [])]
    block, used, taken = "", [], {}   # taken: path -> [(a, b)]
    for n, p, no in picks:
        if (commit, p) not in show_cache:
            show_cache[(commit, p)] = git("show", f"{commit}:{p}").splitlines()
        lines = show_cache[(commit, p)]
        a, b = max(1, no - BEFORE), min(len(lines), no + AFTER)
        if any(x <= no <= y for x, y in taken.get(p, [])):
            continue          # the hit is already shown by an earlier snippet
        for x, y in taken.get(p, []):
            if x <= a <= y:
                a = y + 1     # do not repeat lines an earlier snippet shows
            if x <= b <= y:
                b = x - 1
        snip = f"// {p}:{a}-{b}  [{n}]\n" + "\n".join(lines[a - 1:b]) + "\n\n"
        if len(block) + len(snip) > CAP:
            continue
        block += snip; used.append(n); taken.setdefault(p, []).append((a, b))
    return {"id": it["id"], "names": names, "keys": keys, "candidates": len(cands), "used": used,
            "block": block.rstrip() + "\n" if block else "(no related declarations found)\n"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    items = [json.loads(l) for l in ITEMS.open(encoding="utf-8")]
    if a.limit:
        items = items[:a.limit]
    cache = {}
    with OUT.open("w", encoding="utf-8") as f:
        for k, it in enumerate(items):
            r = build(it, cache)
            f.write(json.dumps(r) + "\n")
            print(f"{k+1:3d} {it['id'][:50]:<50} names {len(r['names']):3d} cand {r['candidates']:3d} "
                  f"used {len(r['used']):2d} chars {len(r['block']):5d}", flush=True)


if __name__ == "__main__":
    main()
