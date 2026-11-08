"""Re-run score_real.py's W2 replay (CLAUDE + JEV through warf's run_review(aggregate="logodds")) with the same
fold assignment, and store every item's verdict, Lambda and per-vote evidence. No network: both providers are
patched to return the stored answers, as score_real.py does. Writes only into this folder (WARF_HOME, profile,
training logs, replay_w2.json). Also checks fold leakage: no training log holds a session of a test item.

    python -B replay_w2.py
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
WARF_ROOT = SET.parents[1]
for name in [k for k in os.environ if k.upper().startswith(("WARF_", "CLAUDE"))]:
    del os.environ[name]
os.environ["WARF_HOME"] = str(HERE / "warf_home")          # nothing reaches any .warf/
os.environ["TYPESAFE_API_KEY"] = "replay-no-network"        # dummy; the provider's _post is replaced
sys.path.insert(0, str(WARF_ROOT))
import warf  # noqa: E402
import warf.providers as providers  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.providers import ClaudeCLIProvider, Completion, SystemOneProvider  # noqa: E402
from warf.state import load_profiles, save_profiles  # noqa: E402

print("warf imported from", Path(warf.__file__).resolve())
INPUT_LABEL = "Patch under review (unified diff)"
items = [json.loads(l) for l in (SET / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "defective" for it in items}
recs = {}
for arm in ("claude", "claude-strict", "claude-advocate", "claude-standard", "jev"):
    recs[arm] = {}
    for path in sorted(SET.glob(f"{arm}.w*.jsonl")):
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            recs[arm][r["planted"]["id"]] = r
ids = [it["id"] for it in items if all(it["id"] in recs[a] for a in recs)]

current = {"id": None}
asked = []
providers.find_claude_exe = lambda: Path(sys.executable)


def fake_claude(self, system, user, model, timeout):
    asked.append(("claude", current["id"]))
    return Completion(text=recs["claude"][current["id"]]["planted"]["call"]["reply"])


def fake_jev(self, request, timeout):
    asked.append(("jev", current["id"]))
    return recs["jev"][current["id"]]["planted"]["call"]["body"]


ClaudeCLIProvider.complete = fake_claude
SystemOneProvider._post = fake_jev
panel = HERE / "mixed.json"
save_profiles(panel, [load_profiles(SET / "profiles" / f"{s}.json")[0] for s in ("claude", "jev")])

rng = random.Random(7)
fold = {}
for cls in (True, False):
    members = [i for i in ids if defect[i] == cls]
    rng.shuffle(members)
    for k, i in enumerate(members):
        fold[i] = k % 5

out = {"fold": fold, "items": {}, "leakage": []}
logs = HERE / "trainlogs"
logs.mkdir(exist_ok=True)
for k in range(5):
    log = logs / f"train{k}.jsonl"
    with log.open("w", encoding="utf-8") as f:
        for seat in ("claude", "jev"):
            for i in ids:
                if fold[i] != k:
                    r = {key: v for key, v in recs[seat][i].items() if key != "planted"}
                    r["oracle"] = {"type": "DEVELOPER", "x_star": -1 if defect[i] else 1}
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # leakage check: sessions and artifacts in this training log vs the fold's test items
    train = [json.loads(l) for l in log.open(encoding="utf-8")]
    train_sessions = {s["session_id"] for s in train}
    train_artifacts = {s["artifact"] for s in train}
    for i in (i for i in ids if fold[i] == k):
        for seat in ("claude", "jev"):
            if recs[seat][i]["session_id"] in train_sessions:
                out["leakage"].append(("session", k, i, seat))
        art = f"{by_id[i]['commit']}:{by_id[i]['file']}"
        if art in train_artifacts:
            out["leakage"].append(("artifact", k, i))
    for i in (i for i in ids if fold[i] == k):
        current["id"] = i
        it = by_id[i]
        asked.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            res = run_review(it["code"], it["domain"], panel, verbose=False, debate=False, input_label=INPUT_LABEL,
                             context=it["context"], aggregate="logodds", log_path=log)
        out["items"][i] = {
            "fold": k, "decision": res.decision.value, "confidence": res.confidence.value,
            "lambda": res.sprt_lambda, "asked": [a for a, _ in asked],
            "votes": [{"agent": v.agent_name, "vote": v.vote, "p_reject": v.p_reject, "evidence": v.evidence,
                       "calibration": v.calibration, "provider": v.provider, "model": v.model} for v in res.votes]}
(HERE / "replay_w2.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
rej = {i: out["items"][i]["decision"] == "REJECT" for i in ids}
P = [i for i in ids if defect[i]]
N = [i for i in ids if not defect[i]]
print(f"replayed {len(out['items'])} items; recall {sum(rej[i] for i in P)}/{len(P)}, "
      f"false alarms {sum(rej[i] for i in N)}/{len(N)}; leakage entries {len(out['leakage'])}")
