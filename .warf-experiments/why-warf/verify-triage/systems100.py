"""Build every (verdict, confidence) system on the 100 gismo6 commits from the stored runs,
re-deriving WaRF's verdicts with my own code (vt_lib.warf_round) and, separately, with
warf.engine, and checking both against every logged field. Stored data only."""
import sys

sys.path.insert(0, "C:/workdir/warf/WaRF")
sys.path.insert(0, "C:/workdir/warf/WaRF/.warf-experiments/why-warf/verify-triage")
from warf import engine as E                     # noqa: E402
import vt_lib as V                               # noqa: E402

AGENTS = ("SKEPTIC", "ADVOCATE", "AUDITOR", "TEST-FOCUSED", "BOUNDARY")
EXP = V.EXP

sel = V.load(f"{EXP}/laya-five/selection.jsonl")
ids = [s["id"] for s in sel]
truth = [V.xv(s["label"]) for s in sel]          # +1 never fixed, -1 later fixed
by = {}


def index(path, key):
    rows = V.load(path)
    m = {r[key]["id"]: r for r in rows}
    assert len(m) == len(rows) == 100 and set(m) == set(ids), path
    for r in rows:
        assert r[key]["label"] == sel[ids.index(r[key]["id"])]["label"], (path, r[key]["id"])
    return m


one = index(f"{EXP}/jev-five/sessions_one.jsonl", "jev")
five = index(f"{EXP}/jev-five/sessions_five.jsonl", "jev")
std = index(f"{EXP}/jev-five/sessions_standard.jsonl", "jev")
lay = index(f"{EXP}/laya-five/sessions.jsonl", "five")
rA = index(f"{EXP}/jev-five/verify/refute/rerun_A.jsonl", "jev")
rB = index(f"{EXP}/jev-five/verify/refute/rerun_B.jsonl", "jev")


def engine_round(votes, omegas, domain, early_stop):
    """The same Round with warf.engine's own sprt_update and synthesis."""
    st = E.SPRTState()
    first = None
    used = 0
    for v, w in zip(votes, omegas):
        st, b = E.sprt_update(st, v, w)
        used += 1
        if b is not None and first is None:
            first = b
            if early_stop:
                break
    if first is not None:
        return (1 if first == E.Decision.APPROVE else -1), "HIGH", st.lambda_
    dec, conf, _ = E.synthesis(votes[:used], omegas[:used], domain)
    return (1 if dec == E.Decision.APPROVE else -1), conf.value, st.lambda_


mism = {}


def note(name, ok):
    mism.setdefault(name, [0, 0])
    mism[name][0] += 1
    mism[name][1] += (not ok)


def single(m, key="jev", agent="JEV"):
    d, c, p, dp = [], [], [], []
    for i in ids:
        a = m[i][key]["round1"][agent]
        pr = a["p_reject"]
        d.append(V.xv(a["choice"]))
        dp.append(-1 if pr > 0.5 else 1)
        c.append(round(abs(pr - 0.5), 9))
        p.append(pr)
        # the logged vote is the argmax label
        note(f"{agent} logged vote = choice", m[i]["votes"][0]["vote"] == V.xv(a["choice"]))
    return {"d": d, "c": c, "p": p, "d_pgt": dp}


S = {}
S["jev_single"] = single(one)
S["jev_rerunA"] = single(rA)
S["jev_rerunB"] = single(rB)


def panel(m, key, early_stop, debate_used):
    """WaRF's Round-1 verdict (and the final one after any debate) recomputed."""
    out = {"r1": {"d": [], "band": [], "lam": [], "lam_at_cross": [], "margin": [], "k": [],
                  "rejects": [], "first4R": []},
           "fin": {"d": [], "band": [], "lam": [], "margin": [], "debated": []},
           "seat": {a: {"d": [], "c": [], "p": []} for a in AGENTS},
           "meanp": []}
    for i in ids:
        r = m[i]
        vv = [v["vote"] for v in r["votes"]]
        ww = [v["omega"] for v in r["votes"]]
        order = [v["agent"] for v in r["votes"]]
        note(f"{key}:{r['profile']} SKEPTIC asked first", order[0] == "SKEPTIC")
        note(f"{key}:{r['profile']} uniform omega 0.5", all(abs(w - 0.5) < 1e-12 for w in ww))
        dom = r["domain"]
        dec, band, lam, norm, k = V.warf_round(vv, ww, dom, early_stop=early_stop)
        # Lambda at the crossing (early stop) for the HIGH ones, else after every vote
        dec_e, band_e, lam_e, norm_e, k_e = V.warf_round(vv, ww, dom, early_stop=True)
        ed, eb, el = engine_round(vv, ww, dom, early_stop)
        note(f"{r['profile']}: my R1 == engine R1", (dec, band) == (ed, eb) and abs(lam - el) < 1e-9)
        note(f"{r['profile']}: top-level sprt_lambda == R1 lambda (4 dp)", abs(round(lam, 4) - r["sprt_lambda"]) < 1e-9)
        o = out["r1"]
        o["d"].append(dec)
        o["band"].append(band)
        o["lam"].append(lam)
        o["lam_at_cross"].append(lam_e)
        o["margin"].append(abs(norm - V.THETA[dom]))
        o["k"].append(k)
        o["rejects"].append(sum(1 for v in vv if v == -1))
        o["first4R"].append(all(v == -1 for v in vv[:4]))
        f = out["fin"]
        if debate_used and "debate" in r:
            dv = [v["vote"] for v in r["debate"]["votes"]]
            dw = [v["omega"] for v in r["debate"]["votes"]]
            note(f"{r['profile']}: debate only when R1 had no crossing", band != "HIGH")
            d2, b2, l2, n2, k2 = V.warf_round(dv, dw, dom, early_stop=False)
            ed2, eb2, el2 = engine_round(dv, dw, dom, False)
            note(f"{r['profile']}: my R2 == engine R2", (d2, b2) == (ed2, eb2))
            note(f"{r['profile']}: debate sprt_lambda == R2 lambda", abs(round(l2, 4) - r["debate"]["sprt_lambda"]) < 1e-9)
            f["d"].append(d2)
            f["band"].append(b2)
            f["lam"].append(l2)
            f["margin"].append(abs(n2 - V.THETA[dom]))
            f["debated"].append(True)
        else:
            if debate_used:
                note(f"{r['profile']}: no debate only after an R1 crossing", band == "HIGH")
            f["d"].append(dec)
            f["band"].append(band)
            f["lam"].append(lam)
            f["margin"].append(abs(norm - V.THETA[dom]))
            f["debated"].append(False)
        note(f"{r['profile']}: logged decision == final", V.xv(r["decision"]) == f["d"][-1])
        note(f"{r['profile']}: logged confidence == final", r["confidence"] == f["band"][-1])
        note(f"{r['profile']}: logged normalised_score == R1 norm", abs(r["normalised_score"] - round(norm, 4)) < 1e-9
             if r.get("normalised_score") is not None else band == "HIGH")
        ps = []
        for a in AGENTS:
            blk = r[key]["round1"].get(a)
            if blk is None:
                continue
            out["seat"][a]["d"].append(V.xv(blk["choice"]))
            out["seat"][a]["c"].append(round(abs(blk["p_reject"] - 0.5), 9))
            out["seat"][a]["p"].append(blk["p_reject"])
            ps.append(blk["p_reject"])
            vote = next(v["vote"] for v in r["votes"] if v["agent"] == a)
            note(f"{r['profile']}: seat vote == argmax", vote == V.xv(blk["choice"]))
        out["meanp"].append(sum(ps) / len(ps))
    return out


P5 = panel(five, "jev", early_stop=False, debate_used=True)
PS = panel(std, "jev", early_stop=True, debate_used=False)
PL = panel(lay, "five", early_stop=False, debate_used=True)

laya1 = [s["p_single_laya"] for s in sel]
claude = [s["p_claude"] for s in sel]
S["laya_single"] = {"d": [-1 if p > 0.5 else 1 for p in laya1], "c": [round(abs(p - 0.5), 9) for p in laya1], "p": laya1}
S["claude"] = {"d": [-1 if p > 0.5 else 1 for p in claude], "c": [round(abs(p - 0.5), 9) for p in claude], "p": claude}


def key_band(o, lamkey="lam"):
    return [(V.BAND_RANK[b], round(abs(l), 6)) for b, l in zip(o["band"], o[lamkey])]


def mk_panel_systems(prefix, P, has_final):
    r1 = P["r1"]
    S[f"{prefix}_R1_band"] = {"d": r1["d"], "c": key_band(r1)}
    S[f"{prefix}_R1_bandonly"] = {"d": r1["d"], "c": [V.BAND_RANK[b] for b in r1["band"]]}
    S[f"{prefix}_R1_band_lamcross"] = {"d": r1["d"], "c": key_band(r1, "lam_at_cross")}
    S[f"{prefix}_R1_lam"] = {"d": r1["d"], "c": [round(abs(l), 6) for l in r1["lam"]]}
    S[f"{prefix}_R1_margin"] = {"d": r1["d"], "c": [round(m, 6) for m in r1["margin"]]}
    S[f"{prefix}_R1_meanp"] = {"d": r1["d"], "c": [round(abs(p - 0.5), 9) for p in P["meanp"]]}
    if has_final:
        f = P["fin"]
        S[f"{prefix}_fin_band"] = {"d": f["d"], "c": key_band(f)}
        S[f"{prefix}_fin_lam"] = {"d": f["d"], "c": [round(abs(l), 6) for l in f["lam"]]}
        S[f"{prefix}_fin_margin"] = {"d": f["d"], "c": [round(m, 6) for m in f["margin"]]}
    for a in AGENTS:
        s = P["seat"][a]
        if len(s["d"]) == 100:
            S[f"{prefix}_seat_{a}"] = {"d": s["d"], "c": s["c"], "p": s["p"]}
    S[f"{prefix}_meanp_verdict"] = {"d": [-1 if p > 0.5 else 1 for p in P["meanp"]],
                                    "c": [round(abs(p - 0.5), 9) for p in P["meanp"]]}


mk_panel_systems("jev5", P5, True)
mk_panel_systems("jevdef", PS, False)
mk_panel_systems("laya5", PL, True)

for name, s in S.items():
    s["correct"] = [1 if d == t else 0 for d, t in zip(s["d"], truth)]

if __name__ == "__main__":
    print("Recomputation checks (items checked, mismatches):")
    for k, (n, bad) in mism.items():
        print(f"  {k:<70} {n:>4} {bad:>4}")
    print("\nSystems built:", len(S))
