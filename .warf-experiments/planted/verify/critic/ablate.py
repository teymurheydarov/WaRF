"""Critic: member ablations of the log-odds panel, from stored answers, using WaRF's own Calibrator
and engine functions (no run_review, no providers, no network). Also a proper base bootstrap."""
import json, math, random, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]            # .../planted
ROOT = EXP.parents[1]           # WaRF repo
sys.path.insert(0, str(ROOT))
from warf.calibration import Calibrator, p_reject_from_text
from warf.engine import pool_evidence, logodds_boundary, logodds_decision, vote_evidence, capped_evidence
from warf.state import load_profiles

SEATS = ("claude", "jev", "laya")
items = [json.loads(l) for l in (EXP / "items.jsonl").open(encoding="utf-8")]
by_id = {it["id"]: it for it in items}
defect = {it["id"]: it["kind"] == "planted" for it in items}
recs = {s: {} for s in SEATS}
for s in SEATS:
    for p in sorted(EXP.glob(f"{s}.w*.jsonl")):
        for l in p.open(encoding="utf-8"):
            r = json.loads(l); recs[s][r["planted"]["id"]] = r
ids = [it["id"] for it in items]
bases = sorted({by_id[i]["base"] for i in ids})
rng = random.Random(7); order = bases[:]; rng.shuffle(order)
fold = {b: k % 5 for k, b in enumerate(order)}
prof = {s: load_profiles(EXP / "profiles" / f"{s}.json")[0] for s in SEATS}

def write_log(train, path):
    with path.open("w", encoding="utf-8") as f:
        for s in SEATS:
            for i in ids:
                if by_id[i]["base"] in train:
                    r = {k: v for k, v in recs[s][i].items() if k != "planted"}
                    r["oracle"] = {"type": "DEVELOPER", "x_star": -1 if defect[i] else 1}
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

tmp = HERE / "logs"; tmp.mkdir(exist_ok=True)
(tmp / "empty.jsonl").write_text("", encoding="utf-8")
cals = {}
for k in range(5):
    p = tmp / f"train{k}.jsonl"; write_log({b for b in bases if fold[b] != k}, p)
    cals[("cal", k)] = Calibrator(p)
    cals[("cold", k)] = Calibrator(tmp / "empty.jsonl")

def seat_ev(mode, s, i):
    v = recs[s][i]["votes"][0]
    vote = v["vote"]; pr = p_reject_from_text(v.get("reasoning") or "")
    omega = v.get("omega", 0.5)
    c = cals[(mode, fold[by_id[i]["base"]])]
    return c.evidence(prof[s], vote, pr, omega, v.get("provider") or "", v.get("model") or "")[0], vote, pr

ev = {(m, s, i): seat_ev(m, s, i) for m in ("cal", "cold") for s in SEATS for i in ids}

def decide(mode, members, i, early=True):
    """Seats asked in the panel order (claude, jev, laya); early stop on whole models as WaRF does."""
    items_ = []
    for s in members:
        items_.append((s, ev[(mode, s, i)][0]))
        lam, means = pool_evidence(items_)
        if early and logodds_boundary(lam, means) is not None:
            return logodds_boundary(lam, means).value == "REJECT", lam
    lam, means = pool_evidence(items_)
    d, conf, _ = logodds_decision(lam, means, by_id[i]["domain"])
    return d.value == "REJECT", lam

def ba(rj, sample):
    P = [i for i in sample if defect[i]]; N = [i for i in sample if not defect[i]]
    return (sum(rj[i] for i in P) / len(P) + sum(not rj[i] for i in N) / len(N)) / 2

claude = {i: recs["claude"][i]["decision"] == "REJECT" for i in ids}
jevv = {i: recs["jev"][i]["decision"] == "REJECT" for i in ids}
arms = {"Claude alone": claude}
for mode in ("cal", "cold"):
    for mem in (("claude", "jev", "laya"), ("claude", "jev"), ("claude", "laya")):
        arms[f"{mode} {'+'.join(mem)}"] = {i: decide(mode, mem, i)[0] for i in ids}
arms["AND rule: Claude REJ and Jev REJ"] = {i: claude[i] and jevv[i] for i in ids}
for thr in (0.55, 0.6, 0.65):
    arms[f"AND rule, Jev p>{thr}"] = {i: claude[i] and ev[("cal", "jev", i)][2] > thr for i in ids}

print(f"{'arm':<40} BA     caught passed  onlyArm onlyClaude  McNemar2s")
def mcn(a, b):
    n = a + b; k = min(a, b)
    return min(1.0, 2 * sum(math.comb(n, j) for j in range(k + 1)) / 2 ** n) if n else 1.0
for name, rj in arms.items():
    right = {i: rj[i] == defect[i] for i in ids}; rc = {i: claude[i] == defect[i] for i in ids}
    op = sum(right[i] and not rc[i] for i in ids); oc = sum(rc[i] and not right[i] for i in ids)
    print(f"{name:<40} {ba(rj, ids):.3f}  {sum(rj[i] for i in ids if defect[i]):>3}/54 {sum(not rj[i] for i in ids if not defect[i]):>3}/54   {op:>3}     {oc:>3}      {mcn(op, oc):.3f}")

# check that the full panel reproduces score.log's flips
full = arms["cal claude+jev+laya"]
print("cal full panel flips vs Claude:", sorted(i for i in ids if full[i] != claude[i]))
print("cold full panel flips vs Claude:", sorted(i for i in ids if arms["cold claude+jev+laya"][i] != claude[i]))
# Laya evidence ranges
for mode in ("cal", "cold"):
    xs = sorted(ev[(mode, "laya", i)][0] for i in ids)
    print(f"Laya evidence {mode}: min {xs[0]:+.3f} median {xs[54]:+.3f} max {xs[-1]:+.3f}; Laya votes REJECT {sum(ev[(mode,'laya',i)][1]==-1 for i in ids)}")

# proper paired bootstrap over bases (duplicates kept) of BA(full cal) - BA(Claude)
brng = random.Random(4)
def ba_w(rj, bs):
    P = N = cp = cn = 0
    for b in bs:
        P += 1; N += 1; cp += rj[f"{b}:planted"] if f"{b}:planted" in rj else 0
    return None
def ba_multi(rj, bs):
    tp = sum(rj[f"{b}:planted"] for b in bs); tn = sum(not rj[f"{b}:clean"] for b in bs)
    return (tp + tn) / (2 * len(bs))
# item ids are "<base>:planted"? check
ex = ids[0]; print("id form:", ex, by_id[ex]["base"])
pid = {by_id[i]["base"]: {} for i in ids}
for i in ids: pid[by_id[i]["base"]][by_id[i]["kind"]] = i
def ba_b(rj, bs):
    return (sum(rj[pid[b]["planted"]] for b in bs) + sum(not rj[pid[b]["clean"]] for b in bs)) / (2 * len(bs))
for name in ("cal claude+jev+laya", "cold claude+jev+laya", "cal claude+jev"):
    ds = []
    for _ in range(4000):
        bs = [brng.choice(bases) for _ in bases]
        ds.append(ba_b(arms[name], bs) - ba_b(claude, bs))
    ds.sort()
    print(f"proper bootstrap {name} - Claude: [{ds[99]:+.3f}, {ds[3899]:+.3f}], share <= 0: {sum(d <= 0 for d in ds)/len(ds):.3f}")
# the scorer's set-membership bootstrap: unique bases per resample
u = [len(set(brng.choice(bases) for _ in bases)) for _ in range(2000)]
print("unique bases per scorer resample: mean", sum(u) / len(u))

print("\nitems where cal full panel and cal claude+jev differ:")
for i in ids:
    if arms["cal claude+jev+laya"][i] != arms["cal claude+jev"][i]:
        print(" ", i, "defect" if defect[i] else "clean", {s: round(ev[("cal", s, i)][0], 3) for s in SEATS}, "jev p", ev[("cal","jev",i)][2])
print("disagreement items (cal), per-seat evidence:")
for i in sorted(i for i in ids if arms["cal claude+jev+laya"][i] != claude[i]):
    print(" ", i, {s: round(ev[("cal", s, i)][0], 3) for s in SEATS}, "jev p", ev[("cal","jev",i)][2], "sum", round(sum(ev[("cal", s, i)][0] for s in SEATS), 3))

print("\nper fold: Claude APPROVE evidence, Jev evidence at p=0.99 (clamp), Jev zero crossing p")
from warf.calibration import approve_logodds
for k in range(5):
    c = cals[("cal", k)]
    fit = c._platt(prof["jev"], "jev", recs["jev"][ids[0]]["votes"][0].get("model") or "")
    capp = c.evidence(prof["claude"], 1, None, 0.5, "claude_cli", "claude-opus-5-5")[0]
    crej = c.evidence(prof["claude"], -1, None, 0.5, "claude_cli", "claude-opus-5-5")[0]
    jmin = fit.evidence(approve_logodds(0.99))
    z = -(fit.a - fit.prior_logodds) / fit.b; pz = 1 / (1 + math.exp(z))
    print(f"  fold {k}: Claude APP {capp:+.3f} REJ {crej:+.3f}; Jev a {fit.a:.3f} b {fit.b:.3f} prior {fit.prior_logodds:+.3f}; Jev at p=.99 {jmin:+.3f}; Jev zero at p={pz:.3f}")
cl_app = [i for i in ids if not claude[i]]
print("Claude-APPROVE items with Jev p>=0.95:", sum(ev[("cal","jev",i)][2] >= 0.95 for i in cl_app), "of", len(cl_app),
      "; min Claude+Jev sum on them:", round(min(ev[("cal","claude",i)][0] + ev[("cal","jev",i)][0] for i in cl_app), 3))
