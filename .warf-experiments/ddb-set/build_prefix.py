"""The first PREFIX candidates of build_ddb.py's list, written one by one as they are found, so that judging can
start while build_ddb.py mines the whole list (same rules, same seeded order; git only). When build_ddb.py
finishes, check_prefix() must find candidates_prefix.jsonl equal to the start of candidates.jsonl.

    python build_prefix.py      # writes candidates_prefix.jsonl"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_ddb as D  # noqa: E402

PREFIX = 520


def check_prefix():
    pre = [json.loads(l) for l in (HERE / "candidates_prefix.jsonl").open(encoding="utf-8")]
    full = [json.loads(l) for l in (HERE / "candidates.jsonl").open(encoding="utf-8")]
    same = pre == full[:len(pre)]
    print(f"prefix {len(pre)} candidates, full list {len(full)}: {'identical start' if same else 'DIFFERENT'}")
    return same


if __name__ == "__main__":
    D.B.N_DEFECT = PREFIX
    with (HERE / "candidates_prefix.jsonl").open("w", encoding="utf-8") as sink:
        D.defects(sink)
