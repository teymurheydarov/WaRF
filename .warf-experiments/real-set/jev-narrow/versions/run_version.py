"""The frozen narrow-check request (../run_narrow.py) with another Jev version (development, ../../DEV.md 2026-11-11).

OpenRouter serves two System One versions: jev-1.14 (typesafe/jev-1.14-20261014, = jev-latest, used so far)
and jev-1.13 (typesafe/jev-1.13-20260917). Same questions, states and hunk split; only the model differs.

    python run_version.py jev-1.13 [--items ...] [--out ...]     # default out: answers_<model>.jsonl here"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import run_narrow  # noqa: E402

if __name__ == "__main__":
    run_narrow.MODEL = sys.argv.pop(1)       # ask() reads the module's MODEL at call time
    if "--out" not in sys.argv:
        sys.argv += ["--out", str(HERE / f"answers_{run_narrow.MODEL}.jsonl")]
    run_narrow.main()
