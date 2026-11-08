"""Re-score all arms with relabelled clean controls (secondary; not the preregistered result).
Replays W2 exactly as score_real.py does, but with profiles copied into this folder and WARF_HOME here."""
import contextlib, io, json, math, os, random, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
RS = HERE.parents[1]; EXP = RS.parent
for name in [k for k in os.environ if k.upper().startswith(("WARF_", "CLAUDE"))]:
    del os.environ[name]
os.environ["WARF_HOME"] = str(HERE / "warf_home")
os.environ["TYPESAFE_API_KEY"] = "replay-no-network"
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(EXP / "laya-five"))
from run_five import INPUT_LABEL
import warf.providers as providers
from warf.orchestrator import run_review
from warf.providers import ClaudeCLIProvider, Completion, SystemOneProvider
from warf.state import load_profiles, save_profiles
from load import items, by_id, recs
from verdicts import V
defect0 = {it["id"]: it["kind"] == "defective" for it in items}
ids = [it["id"] for it in items]
cur = {"id": None}
providers.find_claude_exe = lambda: Path(sys.executable)
ClaudeCLIProvider.complete = lambda self, system, user, model, timeout: Completion(text=recs["claude"][cur["id"]]["planted"]["call"]["reply"])
SystemOneProvider._post = lambda self, request, timeout: recs["jev"][cur["id"]]["planted"]["call"]["body"]
panel = HERE / "profiles" / "mixed.json"
save_profiles(panel, [load_profiles(HERE / "profiles" / f"{s}.json")[0] for s in ("claude", "jev")])
def replay(defect, sample):
    rng = random.Random(7); fold = {}
    for cls in (True, False):
        m = [i for i in sample if defect[i] == cls]; rng.shuffle(m)
        for k, i in enumerate(m): fold[i] = k % 5
    tmp = Path(tempfile.mkdtemp(prefix="warf-verify-", dir=str(HERE))); out = {}
    for k in range(5):
        log = tmp / f"train{k}.jsonl"
        with log.open("w", encoding="utf-8") as f:
            for seat in ("claude", "jev"):
                for i in sample:
                    if fold[i] != k:
                        r = {kk: v for kk, v in recs[seat][i].items() if kk != "planted"}
                        r["oracle"] = {"type": "DEVELOPER", "x_star": -1 if defect[i] else 1}
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
        for i in (i for i in sample if fold[i] == k):
            cur["id"] = i; it = by_id[i]
            with contextlib.redirect_stdout(io.StringIO()):
                out[i] = run_review(it["code"], it["domain"], panel, verbose=False, debate=False, input_label=INPUT_LABEL,
                                    context=it["context"], aggregate="logodds", log_path=log).decision.value == "REJECT"
    return out
w2 = replay(defect0, ids)
from collections import Counter
c = Counter()
for i in ids:
    c[(("C-R" if recs["claude"][i]["decision"]=="REJECT" else "C-A"), ("J-R" if recs["jev"][i]["decision"]=="REJECT" else "J-A"), "def" if defect0[i] else "clean", "W2-R" if w2[i] else "W2-A")] += 1
for k in sorted(c): print(k, c[k])
print("jev labels:", Counter(recs["jev"][i]["decision"] for i in ids))
