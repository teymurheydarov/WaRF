"""Print agent weights from the talk snapshot profile. Run from project root."""
import json, sys
from pathlib import Path

# The table prints ω. A Windows console shows it; a pipe or a redirected stdout
# defaults to cp1252 there and print() raises UnicodeEncodeError instead.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

profile =sys.argv[1] if len(sys.argv) > 1 else ".warf/profiles/socrates2026_snapshot_20260813.json"
agents = json.load(open(profile))

domains = ["LOGIC", "SECURITY"]
header = f"{'AGENT':<16}" + "".join(f"  {d:<24}" for d in domains)
print(header)
print("-" * len(header))

for p in sorted(agents, key=lambda x: -(x["weights"]["LOGIC"]["alpha"] /
               (x["weights"]["LOGIC"]["alpha"] + x["weights"]["LOGIC"]["beta"]))):
    row = f"{p['name']:<16}"
    for d in domains:
        a = p["weights"][d]["alpha"]
        b = p["weights"][d]["beta"]
        row += f"  {int(a):>2}+{int(b):>2}  ω={a/(a+b):.2f}          "
    print(row)
