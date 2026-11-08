"""Replay W3 through warf.run_review(aggregate="logodds") without score_commit.py. Mode "frame": each call is
answered by the seat that asks (profile.name read from run_review's frame), so serving does not rely on call
order. Mode "queue": score_commit.py's mechanism (answers queued in seat order). Mode "swapped": queue reversed
(negative control). Compares per item with w3_pure.json. No network: the CLI provider is replaced."""
import contextlib, io, json, os, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
SET = HERE.parents[1]; ROOT = SET.parents[1]
for n in [k for k in os.environ if k.upper().startswith(("WARF_", "CLAUDE"))]: del os.environ[n]
os.environ["WARF_HOME"] = str(HERE / "warf_home")
sys.path.insert(0, str(ROOT))
import warf, warf.providers as providers
from warf.orchestrator import run_review
from warf.providers import ClaudeCLIProvider, Completion
from warf.state import load_profiles, save_profiles
print("warf from", Path(warf.__file__).resolve().parent)
SEATS = {"CLAUDE": "claude-strict", "CLAUDE-COMMIT": "claude-commit-strict"}
items = [json.loads(l) for l in (SET / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}; defect = {it["id"]: it["kind"] == "defective" for it in items}
recs = {a: {} for a in SEATS.values()}
for a in recs:
    for p in sorted(SET.glob(f"{a}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l); recs[a][r["planted"]["id"]] = r
ids = [it["id"] for it in items]
fold = json.load((HERE / "folds.json").open())
pure = json.load((HERE / "w3_pure.json").open())
panel = HERE / "evidence-panel.json"
seats = [load_profiles(SET / "profiles" / f"{a}.json")[0] for a in SEATS.values()]
save_profiles(panel, seats)
providers.find_claude_exe = lambda: Path(sys.executable)
state = {"mode": None, "id": None, "queue": [], "served": []}
def fake(self, system, user, model, timeout):
    if state["mode"] == "frame":
        f = sys._getframe(1)
        while "profile" not in f.f_locals or f.f_code.co_name != "run_review": f = f.f_back
        name = f.f_locals["profile"].name
        state["served"].append(name)
        return Completion(text=recs[SEATS[name]][state["id"]]["planted"]["call"]["reply"])
    return Completion(text=state["queue"].pop(0))
ClaudeCLIProvider.complete = fake
tmp = Path(tempfile.mkdtemp(prefix="audit-w3-", dir=HERE))
logs = {}
for k in range(5):
    log = tmp / f"train{k}.jsonl"
    with log.open("w", encoding="utf-8") as f:
        for a in SEATS.values():
            for i in ids:
                if fold[i] != k:
                    r = {key: v for key, v in recs[a][i].items() if key != "planted"}
                    r["oracle"] = {"type": "DEVELOPER", "x_star": -1 if defect[i] else 1}
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    logs[k] = log
    # leakage check: no session of a fold-k item in its training log
    arts = {json.loads(l)["artifact"] for l in log.open(encoding="utf-8")}
    test_arts = {f"{by_id[i]['commit']}:{by_id[i]['file']}" for i in ids if fold[i] == k}
    print(f"fold {k}: training sessions {sum(1 for _ in log.open(encoding='utf-8'))}, test artifacts in log {len(arts & test_arts)}")
out = {}
for mode in ("frame", "queue", "swapped"):
    state["mode"] = mode; res = {}
    for i in ids:
        state["id"] = i; state["served"] = []
        q = [recs[a][i]["planted"]["call"]["reply"] for a in SEATS.values()]
        state["queue"] = q[::-1] if mode == "swapped" else q
        it = by_id[i]
        with contextlib.redirect_stdout(io.StringIO()):
            r = run_review(it["code"], it["domain"], panel, verbose=False, debate=False, input_label="x",
                           context=it["context"], aggregate="logodds", log_path=logs[fold[i]])
        res[i] = {"decision": r.decision.value, "lam": r.sprt_lambda,
                  "votes": [(v.agent_name, v.vote, v.evidence, v.calibration, v.evidence_source, v.provider, v.model) for v in r.votes],
                  "served": list(state["served"])}
    out[mode] = res
bad = {m: 0 for m in out}
for m, res in out.items():
    for i in ids:
        p = pure[i]; r = res[i]
        ok = r["decision"] == p["decision"] and len(r["votes"]) == p["seats"] and abs(r["lam"] - p["lam"]) < 1e-3
        if m != "swapped":
            ok = ok and all(abs(v[2] - e) < 1e-3 for v, e in zip(r["votes"], p["e"]))
        if not ok: bad[m] += 1
print("items differing from the pure derivation:", bad)
fr = out["frame"]
own = sum(all(v[1] == recs[SEATS[v[0]]][i]["votes"][0]["vote"] for v in fr[i]["votes"]) for i in ids)
print("frame mode: items where every seat's vote equals its own arm's stored vote:", own)
qu = out["queue"]
own_q = sum(all(v[1] == recs[SEATS[v[0]]][i]["votes"][0]["vote"] for v in qu[i]["votes"]) for i in ids)
print("queue mode: same check:", own_q, "; order of asked seats always CLAUDE then CLAUDE-COMMIT:",
      all([v[0] for v in qu[i]["votes"]] == ["CLAUDE", "CLAUDE-COMMIT"][:len(qu[i]["votes"])] for i in ids))
print("queue vs frame decisions identical:", sum(qu[i]["decision"] == fr[i]["decision"] for i in ids))
sw = out["swapped"]
print("swapped control: decisions differing from frame:", sum(sw[i]["decision"] != fr[i]["decision"] for i in ids),
      "; seat votes not their own:", sum(not all(v[1] == recs[SEATS[v[0]]][i]["votes"][0]["vote"] for v in sw[i]["votes"]) for i in ids))
print("calibration tags:", sorted({v[3] for i in ids for v in fr[i]["votes"]}),
      "evidence_source:", sorted({v[4] for i in ids for v in fr[i]["votes"]}),
      "provider/model:", sorted({(v[5], v[6]) for i in ids for v in fr[i]["votes"]}))
from collections import Counter
print("seats asked:", Counter(len(fr[i]["votes"]) for i in ids))
P = [i for i in ids if defect[i]]; N = [i for i in ids if not defect[i]]
rj = {i: fr[i]["decision"] == "REJECT" for i in ids}
print(f"W3 replay BA {(sum(rj[i] for i in P)/66 + sum(not rj[i] for i in N)/66)/2:.3f} recall {sum(rj[i] for i in P)} FA {sum(rj[i] for i in N)}")
json.dump(out["frame"], (HERE / "replay_w3.json").open("w", encoding="utf-8"), indent=0)
