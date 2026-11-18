"""The 14-seat Jev panel through WaRF's own run_review, from stored answers (development, no calls).

Panel (profile panel.json, written here):
  5 persona seats   ../history/profiles/uniform.json (LO with the project context), their WaRF sessions
                    ../history/sessions_LO_ctx.jsonl
  2 locate seats    question "locate", personas = ../locate/run_locate.py LOCATE; stand-in answers:
                    p(REJECT) = 1 - min p_window(NONE) from ../locate/answers.jsonl (the provider's rule)
  7 check seats     question "check", personas = ../history/run_checks.py CHECKS; stand-in answers:
                    p(REJECT) = p(YES) from ../history/answers_checks.jsonl (whole change; asked there
                    without the project context)
orchestrator._call_agent is stubbed to return a seat's stored answer for the change under review, in the
provider's readout. Training folds are written as labelled WaRF session logs; every test change then goes
through run_review(aggregate=...) with that log. Stratified 10-fold x 5 within RocksDB, the folds of
../history/stack.py.

    python replay_learned.py      # writes replay_learned.log"""
import json
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent.parent
sys.path.insert(0, str(EXP.parent))
from warf import orchestrator  # noqa: E402
from warf.calibration import Calibrator  # noqa: E402
from warf.state import AgentProfile, load_profiles, persona_hash, save_profiles  # noqa: E402

sys.path.insert(0, str(HERE.parent / "history")); sys.path.insert(0, str(HERE.parent / "locate"))
from run_checks import rn  # noqa: E402
from run_locate import LOCATE  # noqa: E402

out = []


def say(s=""):
    out.append(s); print(s, flush=True)


items = {json.loads(l)["id"]: json.loads(l) for l in (EXP / "rdb-set" / "items.jsonl").open(encoding="utf-8")}
ids = list(items)
Y = {i: (-1 if items[i]["kind"] == "defective" else 1) for i in ids}          # WaRF: +1 clean
CURRENT = [None]   # the change run_review is reviewing (two items, both defective, share their code)

personas = load_profiles(HERE.parent / "history" / "profiles" / "uniform.json", reconcile=False)
seats = list(personas)
for k, text in LOCATE.items():
    seats.append(AgentProfile(name=f"LOCATE-{k.upper()}", persona=text, provider="jev", model="jev-1.14",
                              persona_hash=persona_hash(text), question="locate"))
for k, text in rn.CHECKS.items():
    seats.append(AgentProfile(name=f"CHECK-{k.upper()}", persona=text, provider="jev", model="jev-1.14",
                              persona_hash=persona_hash(text), question="check"))
PANEL = HERE / "panel.json"
save_profiles(PANEL, seats)
BY_PERSONA = {s.persona: s for s in seats}

# Stored answers: p(REJECT) per (item, seat name), and the persona seats' own readouts.
P, READ = {}, {}
for l in (HERE.parent / "history" / "sessions_LO_ctx.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    for v in r["votes"]:
        P[(r["artifact"], v["agent"])] = v["p_reject"]; READ[(r["artifact"], v["agent"])] = v["reasoning"]
none = {}
for l in (HERE.parent / "locate" / "answers.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    for k in LOCATE:
        none[(r["id"], k)] = min(none.get((r["id"], k), 1.0), (r["answers"][k]["p"] or {}).get("NONE", 1.0))  # worst window, as the provider
for (i, k), pn in none.items():
    P[(i, f"LOCATE-{k.upper()}")] = 1.0 - pn
for l in (HERE.parent / "history" / "answers_checks.jsonl").open(encoding="utf-8"):
    r = json.loads(l)
    if r["state"] == "whole":
        for k in rn.CHECKS:
            P[(r["id"], f"CHECK-{k.upper()}")] = (r["answers"][k]["p"] or {}).get("YES", 0.0)
missing = [(i, s.name) for i in ids for s in seats if (i, s.name) not in P]
if missing:
    raise SystemExit(f"{len(missing)} stored answers missing, e.g. {missing[:3]}")


def readout(i, s):
    if (i, s.name) in READ:
        return READ[(i, s.name)]
    p = P[(i, s.name)]
    return f"p(APPROVE)={1 - p:.2f}  p(REJECT)={p:.2f}  [stored: decision model, no reasoning]"


def vote_of(i, s):
    return -1 if P[(i, s.name)] > 0.5 else 1


def stub(persona, code, domain, **kw):
    s = BY_PERSONA[persona]
    i = CURRENT[0]
    if code != items[i]["code"] and not (s.question == "locate" and "+[L1]" in code):
        raise RuntimeError(f"seat {s.name} was shown another input than change {i}")
    return vote_of(i, s), readout(i, s), 0, 0, kw["provider"], kw["model"]


def session(i, panel):
    return {"session_id": i, "domain": items[i]["domain"], "oracle": {"type": "DEVELOPER", "x_star": Y[i]},
            "votes": [{"agent": s.name, "vote": vote_of(i, s), "persona": s.persona_hash, "provider": "jev",
                       "model": s.model, "reasoning": readout(i, s), **({"question": s.question} if s.question else {})}
                      for s in panel]}


class FoldCalibrator(Calibrator):
    """WaRF's Calibrator, built once per fold: the learned fit is the same for every change of the fold."""
    def learned(self, reviewers):
        if not hasattr(self, "_fit"):
            self._fit = super().learned(reviewers)
        return self._fit


def ba(pred):
    pos = [i for i in ids if Y[i] == -1]; neg = [i for i in ids if Y[i] == 1]
    return (sum(pred[i] == "REJECT" for i in pos) / len(pos) + sum(pred[i] == "APPROVE" for i in neg) / len(neg)) / 2


def replay(panel, aggregate, reps=5):
    save_profiles(PANEL, panel)
    orchestrator._call_agent = stub
    res, modes = [], set()
    for rep in range(reps):
        rng = random.Random(300 + rep)
        Pd = [i for i in ids if Y[i] == -1]; N = [i for i in ids if Y[i] == 1]; rng.shuffle(Pd); rng.shuffle(N)
        folds = [Pd[k::10] + N[k::10] for k in range(10)]
        pred = {}
        for k in range(10):
            train = [i for f in folds[:k] + folds[k + 1:] for i in f]
            with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
                f.write("".join(json.dumps(session(i, panel)) + "\n" for i in train)); log = Path(f.name)
            cal = FoldCalibrator(log)
            orchestrator.Calibrator = lambda path, cal=cal: cal
            for i in folds[k]:
                CURRENT[0] = i
                r = orchestrator.run_review(items[i]["code"], items[i]["domain"], PANEL, verbose=False,
                                            aggregate=aggregate, log_path=log)
                pred[i] = r.decision.value; modes.add(r.aggregate)
            log.unlink()
        res.append(ba(pred))
    return sum(res) / len(res), min(res), max(res), modes


if __name__ == "__main__":
    say("WaRF run_review on 800 RocksDB changes, stored Jev answers, 10-fold x 5 (balanced accuracy)")
    for name, panel, agg in (("LO ctx (5 persona seats)", personas, "logodds"),
                             ("LO ctx (5 persona seats)", personas, "learned"),
                             ("14 seats (5 personas + 2 locate + 7 checks)", seats, "logodds"),
                             ("14 seats (5 personas + 2 locate + 7 checks)", seats, "learned")):
        m, a, b, modes = replay(panel, agg)
        say(f"  {name:<44} --aggregate {agg:<8} {100 * m:5.1f}%  ({100 * a:.1f}-{100 * b:.1f})  "
            f"ran as {sorted(modes)}")
    (HERE / "replay_learned.log").write_text("\n".join(out) + "\n", encoding="utf-8")
