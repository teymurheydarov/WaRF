"""The context seat's inputs and Jev answers for the 220 confirm items, with the dev lever's code unchanged
(../../real-set/jev-narrow/context/build_context.py and run_context.py; only their paths are pointed here).

    python run_confirm_context.py build      # context_items.jsonl (git only)
    python run_confirm_context.py run        # answers_context.jsonl (jev-1.14, verdict + 7 checks, whole change + block)"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CTX = HERE.parents[1] / "real-set" / "jev-narrow" / "context"
sys.path.insert(0, str(CTX))
ITEMS = HERE.parent / "items.jsonl"

if __name__ == "__main__":
    step = sys.argv.pop(1)
    if step == "build":
        import build_context as b
        b.ITEMS, b.OUT = ITEMS, HERE / "context_items.jsonl"
        b.main()
    else:
        import run_context as r
        r.HERE, r.OUT = HERE, HERE / "answers_context.jsonl"
        r.rn.ITEMS = ITEMS
        r.main()
