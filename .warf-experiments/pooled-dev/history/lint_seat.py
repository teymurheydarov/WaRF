"""A deterministic lint seat for WaRF (development): regular expressions over the added lines of the diff, for
the build-break kinds in defect_profile.md (written from the 37 RocksDB defects outside the test set).
No compiler is run. Each rule is a pattern a reviewer can see in the diff:

  format    a printf-style %lu/%ld/%llu/%lld/%zu-less size format in an added line (RocksDB prints 64-bit
            values with PRIu64 / ROCKSDB_PRIszt; %l* breaks one platform)
  assert    an added assert() whose argument has a side effect (++, --, or a plain assignment)
  override  an added `virtual ...;` declaration in a file that already uses `override`
            (clang -Winconsistent-missing-override)
  signcmp   an added ASSERT_/EXPECT_ comparison of a signed integer literal (no U suffix) with .size()
  narrow    an added `int` / `uint32_t` / `int32_t` / `unsigned` variable initialised from .size(), .count()
            or a uint64_t-returning call such as .GetFileSize()

    python lint_seat.py      # writes lint_seat.log (rule hit rates on the dev data, then on the test set)"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP.parent))
from warf.context_extractor import _SEPARATOR  # noqa: E402

RULES = {
    "format": re.compile(r'"[^"]*%(?:l|ll)[udx][^"]*"'),
    "assert": re.compile(r"\bassert\s*\((?=[^;]*(\+\+|--|[^=!<>+\-*/&|^]=[^=]))"),
    "override": re.compile(r"^\s*virtual\b[^;{]*\)\s*(const)?\s*;"),
    "signcmp": re.compile(r"\b(ASSERT|EXPECT)_(EQ|NE|LT|LE|GT|GE)\s*\(\s*-?\d+\s*,[^;]*\.size\(\)|"
                          r"\b(ASSERT|EXPECT)_(EQ|NE|LT|LE|GT|GE)\s*\([^;]*\.size\(\)\s*,\s*-?\d+\s*\)"),
    "narrow": re.compile(r"^\s*(int|int32_t|uint32_t|unsigned|unsigned int)\s+\w+\s*=\s*[^;]*"
                         r"(\.size\(\)|\.count\(\)|\.length\(\)|GetFileSize\(|NumEntries\(|file_size)"),
}


def added_lines(code):
    diff = code.split(_SEPARATOR, 1)[0]
    return [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]


def hits(code):
    lines = added_lines(code)
    uses_override = "override" in code
    h = set()
    for ln in lines:
        for name, rx in RULES.items():
            if name == "override" and not uses_override:
                continue
            if rx.search(ln):
                h.add(name)
    return h


def rate(rows, name=None):
    n = sum(1 for r in rows if (hits(r["code"]) if name is None else name in hits(r["code"])))
    return f"{n}/{len(rows)} ({100 * n / max(1, len(rows)):.0f}%)"


if __name__ == "__main__":
    out = []

    def say(s=""):
        out.append(s); print(s, flush=True)

    R = EXP / "rdb-set"
    test = {json.loads(l)["base"] for l in (R / "items.jsonl").open(encoding="utf-8")}
    V = {}
    for f in (R / "judgements").glob("*.jsonl"):
        for l in f.open(encoding="utf-8"):
            v = json.loads(l); V[(v["judge"], v["base"])] = v
    cands = [json.loads(l) for l in (R / "candidates.jsonl").open(encoding="utf-8")]
    hist = [c for c in cands if c["base"] not in test and V.get(("A", c["base"]), {}).get("introduced") == "yes"
            and V.get(("B", c["base"]), {}).get("introduced") == "yes"]
    pool = [json.loads(l) for l in (R / "clean_pool.jsonl").open(encoding="utf-8")]
    unused = [c for c in (json.loads(l) for l in (R / "clean_matched.jsonl").open(encoding="utf-8")) if c["base"] not in test]
    say("Dev data (outside the 800 test items): rule hits")
    say(f"  {'rule':<9} {'37 history defects':>20} {'700 first-pool clean':>22} {'unused matched clean':>22}")
    for name in list(RULES) + [None]:
        say(f"  {name or 'any':<9} {rate(hist, name):>20} {rate(pool, name):>22} {rate(unused, name):>22}")
    items = [json.loads(l) for l in (R / "items.jsonl").open(encoding="utf-8")]
    D = [x for x in items if x["kind"] == "defective"]; C = [x for x in items if x["kind"] == "clean"]
    say("\nTest set (800 RocksDB matched): rule hits")
    for name in list(RULES) + [None]:
        say(f"  {name or 'any':<9} defective {rate(D, name):>14}   clean {rate(C, name):>14}")
    (HERE / "lint_seat.log").write_text("\n".join(out) + "\n", encoding="utf-8")
