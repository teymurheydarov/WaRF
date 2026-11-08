"""HIGH set of the five-Jev Round 1 under each last seat (uniform weights: every order is valid)."""
import sys
sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
import vt_lib as V                                  # noqa: E402
from systems100 import S, truth, sel, five          # noqa: E402
ids = [s["id"] for s in sel]
AG = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
fixed = [1 if t == -1 else 0 for t in truth]
cumj = V.curve(fixed, S["jev_single"]["p"])
for last in AG:
    first4 = [a for a in AG if a != last]
    hi = [i for i, x in enumerate(ids) if all({v["agent"]: v["vote"] for v in five[x]["votes"]}[a] == -1 for a in first4)]
    k = len(hi)
    print(f"last seat {last:<13} HIGH {k:>2}, later fixed {sum(fixed[i] for i in hi)}/{k};"
          f" single Jev top-{k} by p later fixed {cumj[k]:.1f}/{k}")
