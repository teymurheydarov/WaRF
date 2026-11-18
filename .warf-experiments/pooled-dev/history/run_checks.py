"""Project-learned narrow checks (development, RocksDB matched set).

The checks turn the kinds of defects/defect_profile.md lists (written from the 37 confirmed RocksDB defects
outside the test set) into concrete YES/NO questions about the changed lines. One jev-1.14 call per item asks
WaRF's usual question and all checks, on the whole change ("whole") and on each hunk ("hunk"), as
../../real-set/jev-narrow/run_narrow.py does.

    python run_checks.py        # resumes; writes answers_checks.jsonl"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP / "real-set" / "jev-narrow"))
import run_narrow as rn  # noqa: E402

rn.CHECKS = {
    "inttype": "Do the changed lines put a size_t, uint64_t or other wide or unsigned integer into a narrower or "
               "signed type, or compare signed with unsigned values (including in ASSERT_EQ/ASSERT_LT)?",
    "format": "Do the changed lines use a printf-style format specifier (%d, %u, %lu, %llu, ...) that does not "
              "match its argument's type on every platform (for example %lu for uint64_t instead of PRIu64)?",
    "warning": "Would the changed lines raise a compiler warning that breaks a -Werror or /WX build on some "
               "compiler (an unused variable, field or parameter, a missing override, shadowing, a declaration "
               "mismatch, an enumerator or member that does not exist)?",
    "assert": "Does a changed assert() contain a side effect, or is a variable used only inside assert() so that "
              "release builds (NDEBUG) behave differently or warn?",
    "lifetime": "Do the changed lines keep a pointer, reference or Slice to memory that may be freed or go out of "
                "scope while still used (a temporary, a released buffer or Version), or change ownership so a "
                "caller now leaks or double-frees?",
    "concurrency": "Do the changed lines read or write shared state without holding the mutex that guards it, or "
                   "while the mutex is temporarily released?",
    "edge": "Do the changed lines get an edge case wrong: an inverted condition or assert, an empty key or "
            "string, zero, an off-by-one bound, or a lost error status?",
}
OUT = HERE / "answers_checks.jsonl"


def main():
    key = os.environ.get("TYPESAFE_API_KEY")
    base = (os.environ.get("TYPESAFE_BASE_URL") or "https://api.typesafe.ai").rstrip("/")
    if not key:
        sys.exit("TYPESAFE_API_KEY is not set")
    sys.argv = [sys.argv[0], "--items", str(EXP / "rdb-set" / "items.jsonl"), "--out", str(OUT), "--workers", "6"]
    rn.main()


if __name__ == "__main__":
    main()
