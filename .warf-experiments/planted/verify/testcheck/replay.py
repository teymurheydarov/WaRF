"""Replay of score_planted.py's panel (same folds, same calibration), per-item output. Writes only here."""
import contextlib, io, json, os, random, sys, tempfile
from pathlib import Path
OUT = Path(__file__).resolve().parent
HERE = OUT.parents[1]
EXP = HERE.parent
for name in [k for k in os.environ if k.upper().startswith(("WARF_", "CLAUDE"))]:
    del os.environ[name]
os.environ["TYPESAFE_API_KEY"] = "replay-no-network"
sys.path.insert(0, str(EXP / "laya-five"))
from run_five import INPUT_LABEL
os.environ["WARF_HOME"] = str(OUT)
import warf.providers as providers
from warf.orchestrator import run_review
from warf.providers import ClaudeCLIProvider, Completion, SystemOneProvider
from warf.state import load_profiles, save_profiles
SEATS = ("claude", "jev", "laya")
items = [json.loads(l) for l in (HERE / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "planted" for it in items}
recs = {}
for seat in SEATS:
    recs[seat] = {}
    for p in sorted(HERE.glob(f"{seat}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l); recs[seat][r["planted"]["id"]] = r
ids = [it["id"] for it in items if all(it["id"] in recs[s] for s in SEATS)]
bases = sorted({by_id[i]["base"] for i in ids if all(f"{by_id[i]['base']}:{k}" in ids for k in ("clean", "planted"))})
ids = [i for i in ids if by_id[i]["base"] in bases]
current = {"id": None}
providers.find_claude_exe = lambda: Path(sys.executable)
def _claude(provider, system, user, model, timeout):
    return Completion(text=recs["claude"][current["id"]]["planted"]["call"]["reply"])
def _post(provider, request, timeout):
    return recs[provider.name][current["id"]]["planted"]["call"]["body"]
ClaudeCLIProvider.complete = _claude
SystemOneProvider._post = _post
panel_path = OUT / "panel.json"
seats = [load_profiles(HERE / "profiles" / f"{s}.json")[0] for s in SEATS]
save_profiles(panel_path, seats)
rng = random.Random(7); order = bases[:]; rng.shuffle(order)
fold = {b: k % 5 for k, b in enumerate(order)}
tmp = Path(tempfile.mkdtemp(prefix="warf-planted-verify-", dir=OUT))
def write_log(train, path):
    with path.open("w", encoding="utf-8") as f:
        for seat in SEATS:
            for i in ids:
                if by_id[i]["base"] in train:
                    r = {k: v for k, v in recs[seat][i].items() if k != "planted"}
                    r["oracle"] = {"type": "DEVELOPER", "x_star": -1 if defect[i] else 1}
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
def panel(log_for):
    res = {}
    for k in range(5):
        log = log_for(k)
        for i in (i for i in ids if fold[by_id[i]["base"]] == k):
            current["id"] = i; it = by_id[i]
            with contextlib.redirect_stdout(io.StringIO()):
                res[i] = run_review(it["code"], it["domain"], panel_path, verbose=False, debate=False,
                                    input_label=INPUT_LABEL, context=it["context"], aggregate="logodds", log_path=log)
    return res
def oof(k):
    p = tmp / f"train{k}.jsonl"; write_log({b for b in bases if fold[b] != k}, p); return p
empty = tmp / "empty.jsonl"; empty.write_text("", encoding="utf-8")
out = {}
for name, lf in (("cal", oof), ("cold", lambda k: empty)):
    res = panel(lf)
    for i, r in res.items():
        out.setdefault(i, {})[name] = {"decision": r.decision.value, "confidence": r.confidence.value,
            "lambda": round(r.sprt_lambda, 3),
            "votes": [(v.agent_name, v.vote, v.p_reject, None if v.evidence is None else round(v.evidence, 3), v.calibration) for v in r.votes]}
for i in ids:
    out[i]["claude"] = recs["claude"][i]["decision"]; out[i]["truth"] = "REJECT" if defect[i] else "APPROVE"
    out[i]["fold"] = fold[by_id[i]["base"]]
(OUT / "replay.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
n = 0
for i in ids:
    o = out[i]
    if o["cal"]["decision"] != o["claude"] or o["cold"]["decision"] != o["claude"]:
        n += 1
        print(i, "truth", o["truth"], "claude", o["claude"], "| cal", o["cal"]["decision"], o["cal"]["confidence"], o["cal"]["lambda"], o["cal"]["votes"], "| cold", o["cold"]["decision"], o["cold"]["confidence"], o["cold"]["lambda"], o["cold"]["votes"])
print("items differing:", n)
