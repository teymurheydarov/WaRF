"""My own replay of the stored answers through WaRF's run_review(aggregate="logodds") (does not import
score_planted.py). Providers are patched to return the stored answer; no network, nothing outside this folder
is written. Writes warf.jsonl with per-item verdicts, Lambda, and per-vote evidence/tag/reasoning."""
import contextlib
import io
import json
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
REPO = EXP.parents[1]
for name in [k for k in os.environ if k.upper().startswith(("WARF_", "CLAUDE"))]:
    del os.environ[name]
os.environ["WARF_HOME"] = str(HERE)
os.environ["TYPESAFE_API_KEY"] = "replay-dummy"          # placeholder so the provider constructs; never sent
os.environ["TYPESAFE_BASE_URL"] = "http://127.0.0.1:9"   # unreachable even if _post were not patched
os.environ["LAYA_BASE_URL"] = "http://127.0.0.1:9"
sys.path.insert(0, str(REPO))
import warf.providers as providers  # noqa: E402
from warf.orchestrator import run_review  # noqa: E402
from warf.providers import ClaudeCLIProvider, Completion, SystemOneProvider  # noqa: E402
from warf.state import load_profiles, save_profiles  # noqa: E402

INPUT_LABEL = "Patch under review (unified diff)"
SEATS = ("claude", "jev", "laya")
items = [json.loads(l) for l in (EXP / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "planted" for it in items}
recs = {s: {} for s in SEATS}
for s in SEATS:
    for p in sorted(EXP.glob(f"{s}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l)
            recs[s][r["planted"]["id"]] = r
ids = [it["id"] for it in items]
bases = sorted({by_id[i]["base"] for i in ids})

current = {"id": None}
calls = []
providers.find_claude_exe = lambda: Path(sys.executable)
ClaudeCLIProvider.complete = lambda self, system, user, model, timeout: (
    calls.append(("claude", current["id"])), Completion(text=recs["claude"][current["id"]]["planted"]["call"]["reply"]))[1]
SystemOneProvider._post = lambda self, request, timeout: (
    calls.append((self.name, current["id"])), recs[self.name][current["id"]]["planted"]["call"]["body"])[1]

panel = HERE / "panel.json"
save_profiles(panel, [load_profiles(EXP / "profiles" / f"{s}.json")[0] for s in SEATS])

rng = random.Random(7)
order = bases[:]
rng.shuffle(order)
fold = {b: k % 5 for k, b in enumerate(order)}


def write_log(train, path):
    with path.open("w", encoding="utf-8") as f:
        for s in SEATS:
            for i in ids:
                if by_id[i]["base"] in train:
                    r = {k: v for k, v in recs[s][i].items() if k != "planted"}
                    r["oracle"] = {"type": "DEVELOPER", "x_star": -1 if defect[i] else 1}
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")


empty = HERE / "empty.jsonl"
empty.write_text("", encoding="utf-8")
rows = {}
for mode in ("cal", "cold"):
    for k in range(5):
        if mode == "cal":
            log = HERE / f"train{k}.jsonl"
            write_log({b for b in bases if fold[b] != k}, log)
        else:
            log = empty
        for i in ids:
            if fold[by_id[i]["base"]] != k:
                continue
            current["id"] = i
            it = by_id[i]
            n0 = len(calls)
            with contextlib.redirect_stdout(io.StringIO()):
                res = run_review(it["code"], it["domain"], panel, verbose=False, debate=False, input_label=INPUT_LABEL,
                                 context=it["context"], aggregate="logodds", log_path=log)
            rows.setdefault(i, {})[mode] = {
                "decision": res.decision.value, "confidence": res.confidence.value, "lambda": res.sprt_lambda,
                "calls": [c[0] for c in calls[n0:]],
                "votes": [{"agent": v.agent_name, "vote": v.vote, "p": v.p_reject, "evidence": v.evidence,
                           "tag": v.calibration, "provider": v.provider, "model": v.model, "reasoning": v.reasoning}
                          for v in res.votes]}
with (HERE / "warf.jsonl").open("w", encoding="utf-8") as f:
    for i in ids:
        f.write(json.dumps({"id": i, **rows[i]}, ensure_ascii=False) + "\n")
print("replayed", len(rows))
