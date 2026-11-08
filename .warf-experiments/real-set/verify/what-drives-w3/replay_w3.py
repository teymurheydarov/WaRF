"""Re-run score_commit.py's W3 replay (claude-strict + claude-commit-strict through warf's
run_review(aggregate="logodds")) with the same folds, and keep every item's verdict, Lambda and per-vote
evidence. No network: the CLI provider is patched to serve the stored answers, as score_commit.py does.
Writes only into this folder (WARF_HOME, panel profile, training logs, replay_w3.json).

    python -B replay_w3.py
"""
import contextlib
import io
import json
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SET = HERE.parents[1]
EXP = SET.parent
WARF_ROOT = EXP.parent
for name in [k for k in os.environ if k.upper().startswith(("WARF_", "CLAUDE"))]:
    del os.environ[name]
os.environ["WARF_HOME"] = str(HERE / "warf_home")          # nothing reaches any .warf/
sys.path.insert(0, str(WARF_ROOT))
sys.path.insert(1, str(EXP / "laya-five"))
import warf  # noqa: E402
from run_five import INPUT_LABEL  # noqa: E402
import warf.providers as providers  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.providers import ClaudeCLIProvider, Completion  # noqa: E402
from warf.state import load_profiles, save_profiles  # noqa: E402

print("warf imported from", Path(warf.__file__).resolve())
SEATS = ("claude-strict", "claude-commit-strict")
items = [json.loads(l) for l in (SET / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "defective" for it in items}
recs = {}
for arm in SEATS:
    recs[arm] = {}
    for path in sorted(SET.glob(f"{arm}.w*.jsonl")):
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            recs[arm][r["planted"]["id"]] = r
ids = [it["id"] for it in items if all(it["id"] in recs[a] for a in SEATS)]

queue = []
providers.find_claude_exe = lambda: Path(sys.executable)
ClaudeCLIProvider.complete = lambda self, system, user, model, timeout: Completion(text=queue.pop(0))
panel = HERE / "evidence-panel.json"
seats = [load_profiles(SET / "profiles" / f"{a}.json")[0] for a in SEATS]
save_profiles(panel, seats)
rng = random.Random(7)
fold = {}
for cls in (True, False):
    members = [i for i in ids if defect[i] == cls]
    rng.shuffle(members)
    for k, i in enumerate(members):
        fold[i] = k % 5
logs = HERE / "trainlogs"
logs.mkdir(exist_ok=True)
out = {"fold": fold, "items": {}}
for k in range(5):
    log = logs / f"train{k}.jsonl"
    with log.open("w", encoding="utf-8") as f:
        for arm in SEATS:
            for i in ids:
                if fold[i] != k:
                    r = {key: v for key, v in recs[arm][i].items() if key != "planted"}
                    r["oracle"] = {"type": "DEVELOPER", "x_star": -1 if defect[i] else 1}
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for i in (i for i in ids if fold[i] == k):
        queue[:] = [recs[a][i]["planted"]["call"]["reply"] for a in SEATS]
        it = by_id[i]
        with contextlib.redirect_stdout(io.StringIO()):
            res = run_review(it["code"], it["domain"], panel, verbose=False, debate=False, input_label=INPUT_LABEL,
                             context=it["context"], aggregate="logodds", log_path=log)
        out["items"][i] = {
            "fold": k, "domain": it["domain"], "decision": res.decision.value, "confidence": res.confidence.value,
            "lambda": res.sprt_lambda,
            "votes": [{"agent": v.agent_name, "vote": v.vote, "evidence": v.evidence, "calibration": v.calibration,
                       "source": v.evidence_source} for v in res.votes]}
(HERE / "replay_w3.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
P = [i for i in ids if defect[i]]
N = [i for i in ids if not defect[i]]
rej = {i: out["items"][i]["decision"] == "REJECT" for i in ids}
print(f"replayed {len(ids)}; recall {sum(rej[i] for i in P)}/{len(P)}, false alarms {sum(rej[i] for i in N)}/{len(N)}")
