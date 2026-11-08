import sys; sys.path.insert(0, r"C:/workdir/warf/WaRF")
from warf.plot_slide06 import build_trace
votes = [{"agent":a,"label":"REJECT","omega":0.5} for a in ["SKEPTIC","ADVOCATE","AUDITOR","TEST-FOCUSED","BOUNDARY"]]
for t in build_trace(votes): print(t["agent"], round(t["running"],3), t["crossed"])
