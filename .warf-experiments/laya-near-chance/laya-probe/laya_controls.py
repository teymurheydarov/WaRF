"""Positive controls for Laya: does p(REJECT) rise when an obvious bug is planted in code
that git history says was fine, and what does it say to junk? Also re-asks the original
states, which must give back the stored answers if the stored records are what Laya saw."""
import json, math, random, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rebuild_state import HOME, ask, frame, load_plan, rebuild  # noqa: E402

OUT = Path(__file__).parent / "controls.jsonl"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120
CPP = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}

labels = {}
with (HOME / "labels.jsonl").open(encoding="utf-8") as f:
    for lab in map(json.loads, f):
        labels[(lab["commit"], lab["file"])] = lab["label"]
pool = []
with (HOME / "sessions.jsonl").open(encoding="utf-8") as f:
    for s in map(json.loads, f):
        w = s.get("sweep")
        if not w or s.get("profile") != "laya_sweep" or w["phase"] != "A":
            continue
        u = w["laya"]["usage"]
        ext = Path(w["file"]).suffix
        if (labels.get((w["commit"], w["file"])) == "APPROVE" and not u["state_tokens_dropped"]
                and u["state_tokens"] <= 860 and (ext in CPP or ext == ".py")):
            pool.append({"commit": w["commit"], "file": w["file"], "domain": s["domain"], "ext": ext,
                         "chars": w["state_chars"], "tokens": u["state_tokens"],
                         "p": w["laya"]["probabilities"]["REJECT"]})
random.Random(7).shuffle(pool)
plan = load_plan()

ADDED = re.compile(r"^\+(?!\+\+)(.*)$", re.M)
SWAP_REL = {"<": ">=", ">": "<=", "<=": ">", ">=": "<", "==": "!=", "!=": "=="}


def mutate_line(state: str, pattern: re.Pattern, repl) -> str | None:
    """Apply repl to the first added code line that matches pattern (comments skipped)."""
    for m in ADDED.finditer(state):
        line = m.group(1)
        if line.lstrip().startswith(("//", "#", "*", "/*")):
            continue
        new, n = pattern.subn(repl, line, count=1)
        if n:
            return state[:m.start(1)] + new + state[m.end(1):]
    return None


def insert_after_first_added(state: str, text: str) -> str | None:
    m = ADDED.search(state)
    if not m:
        return None
    indent = re.match(r"\s*", m.group(1)).group(0) or "    "
    return state[:m.end()] + f"\n+{indent}{text}" + state[m.end():]


def mutations(state: str, ext: str) -> dict:
    py = ext == ".py"
    return {
        "flip comparison": mutate_line(state, re.compile(r"(?<=\s)(<=|>=|==|!=|<|>)(?=\s)"),
                                       lambda m: SWAP_REL[m.group(1)]),
        "flip + / -": mutate_line(state, re.compile(r"(?<=[\w)])\s([+-])\s(?=[\w(])"),
                                  lambda m: f" {'-' if m.group(1) == '+' else '+'} "),
        "flip true/false or && / ||": mutate_line(
            state, re.compile(r"\b(true|false|True|False)\b|&&|\|\|"),
            lambda m: {"true": "false", "false": "true", "True": "False", "False": "True",
                       "&&": "||", "||": "&&"}[m.group(0)]),
        "insert null dereference": insert_after_first_added(
            state, "p = None; p.value = 42" if py else "int* p = nullptr; *p = 42;"),
        "insert BUG / do-not-merge comment": insert_after_first_added(
            state, ("# " if py else "// ") + "BUG: this crashes on every call. Do not merge."),
    }


def tiny(line: str) -> str:
    head, tail = frame("LOGIC")
    return (head + "diff --git a/src/util.cpp b/src/util.cpp\n--- a/src/util.cpp\n+++ b/src/util.cpp\n"
            "@@ -1,0 +1,1 @@\n+" + line + tail)


TINY = [
    ("add", "int add(int a, int b) { return a + b; }", "int add(int a, int b) { return a - b; }"),
    ("sum loop", "for (int i = 0; i < n; ++i) sum += a[i];", "for (int i = 0; i <= n; ++i) sum += a[i];"),
    ("null guard", "if (p != nullptr) p->run();", "if (p == nullptr) p->run();"),
    ("free", "delete buf;", "delete buf; delete buf;"),
    ("mean", "double mean = n > 0 ? sum / n : 0.0;", "double mean = sum / 0;"),
]
_head, _tail = frame("LOGIC")
JUNK = {
    "empty patch": _head + _tail,
    "lorem ipsum": _head + ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 25) + _tail,
    "random characters": _head + "".join(random.Random(3).choice("abcdefghijklmnopqrstuvwxyz{}();=+-*/<> \n")
                                         for _ in range(1500)) + _tail,
    "the question as the patch": _head + "Should this change be merged as it is? A defect you can point to is a REJECT." + _tail,
}

done = 0
t0 = time.time()
with OUT.open("w", encoding="utf-8") as out:
    def emit(rec):
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out.flush()

    for name, good, bad in TINY:
        pg, _ = ask(tiny(good))
        pb, _ = ask(tiny(bad))
        emit({"kind": "tiny", "name": name, "p_good": pg, "p_bad": pb})
    for name, state in JUNK.items():
        p, u = ask(state)
        emit({"kind": "junk", "name": name, "p": p, "tokens": u.get("state_tokens")})
    for item in pool:
        if done >= N:
            break
        entry = plan.get(item["commit"])
        if entry is None:
            continue
        try:
            state = rebuild(entry, item["file"], item["domain"])
        except Exception as exc:
            emit({"kind": "rebuild-error", "commit": item["commit"], "file": item["file"], "error": str(exc)[:300]})
            continue
        p0, u0 = ask(state)
        rec = {"kind": "original", "commit": item["commit"], "file": item["file"], "ext": item["ext"],
               "chars_stored": item["chars"], "chars_rebuilt": len(state), "tokens_stored": item["tokens"],
               "tokens_rebuilt": u0.get("state_tokens"), "p_stored": item["p"], "p_rebuilt": p0, "mutants": {}}
        for mname, mstate in mutations(state, item["ext"]).items():
            if mstate is None:
                continue
            pm, um = ask(mstate)
            rec["mutants"][mname] = {"p": pm, "dropped": um.get("state_tokens_dropped")}
        emit(rec)
        done += 1
        if done % 10 == 0:
            print(f"  {done}/{N} originals, {time.time() - t0:.0f} s", flush=True)


def sign_test(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


recs = [json.loads(line) for line in OUT.open(encoding="utf-8")]
print("\n  tiny hand-made pairs (p(REJECT) correct -> buggy):")
for r in (r for r in recs if r["kind"] == "tiny"):
    print(f"    {r['name']:<12} {r['p_good']:.3f} -> {r['p_bad']:.3f}")
print("  junk states:")
for r in (r for r in recs if r["kind"] == "junk"):
    print(f"    {r['name']:<28} p(REJECT) {r['p']:.3f}")
print(f"  rebuild errors: {sum(1 for r in recs if r['kind'] == 'rebuild-error')}")
orig = [r for r in recs if r["kind"] == "original"]
if orig:
    print(f"\n  re-asked {len(orig)} original states: rebuilt length equal to stored "
          f"{sum(r['chars_rebuilt'] == r['chars_stored'] for r in orig)}, token count equal "
          f"{sum(r['tokens_rebuilt'] == r['tokens_stored'] for r in orig)}, "
          f"max |p_rebuilt - p_stored| {max(abs(r['p_rebuilt'] - r['p_stored']) for r in orig):.4f}")
    names = sorted({m for r in orig for m in r["mutants"]})
    print(f"\n  {'planted bug':<36} {'n':>4} {'p before':>9} {'p after':>8} {'mean diff':>10} "
          f"{'rose':>6} {'now >0.5':>9} {'sign test p':>12}")
    for m in names:
        pairs = [(r["p_rebuilt"], r["mutants"][m]["p"]) for r in orig if m in r["mutants"]]
        d = [b - a for a, b in pairs]
        k = sum(x > 0 for x in d)
        nz = sum(x != 0 for x in d)
        print(f"  {m:<36} {len(pairs):>4} {sum(a for a, _ in pairs) / len(pairs):>9.3f} "
              f"{sum(b for _, b in pairs) / len(pairs):>8.3f} {sum(d) / len(d):>+10.4f} {k / len(d):>6.0%} "
              f"{sum(b > 0.5 for _, b in pairs):>9} {sign_test(k, nz):>12.2g}")
print(f"\n  {time.time() - t0:.0f} s in all")
