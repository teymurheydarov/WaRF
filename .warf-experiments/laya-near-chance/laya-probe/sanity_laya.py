"""Could the pipeline fake a near-chance result? Checks on the stored sweep records."""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

home = Path(sys.argv[1])
labels = {}
with (home / "labels.jsonl").open(encoding="utf-8") as f:
    for line in f:
        lab = json.loads(line)
        labels[(lab["commit"], lab["file"])] = lab["label"]
R = []
with (home / "sessions.jsonl").open(encoding="utf-8") as f:
    for line in f:
        s = json.loads(line)
        if s.get("profile") != "laya_sweep" or "sweep" not in s:
            continue
        w = s["sweep"]; u = w["laya"].get("usage") or {}
        R.append(dict(chars=w["state_chars"], enriched=w["enriched_chars"], patch=w["patch_chars"], cut=w["cut"],
                      tok=u.get("state_tokens"), drop=u.get("state_tokens_dropped"), trunc=u.get("truncated"),
                      tq=u.get("truncated_questions"), inp=u.get("input_tokens"),
                      p=w["laya"]["probabilities"]["REJECT"], pa=w["laya"]["probabilities"]["APPROVE"],
                      choice=w["laya"]["choice"], dec=s["decision"], dom=s["domain"], ext=Path(w["file"]).suffix,
                      y=labels.get((w["commit"], w["file"])), phase=w["phase"], repo=w["repo"].split("/")[-1]))
n = len(R)
print(f"{n} reviews")

# 1. Does each stored answer belong to its request? Laya's own token count should track
#    the characters we sent, review by review; a mix-up of responses would scatter it.
ch = np.array([r["chars"] for r in R], float); tk = np.array([r["tok"] for r in R], float)
ratio = ch / tk
print(f"chars per Laya state token: median {np.median(ratio):.2f}, 1-99% {np.percentile(ratio, 1):.2f}-{np.percentile(ratio, 99):.2f}")
lc, lt = np.log(ch), np.log(tk)
corr = float(((lc - lc.mean()) * (lt - lt.mean())).mean() / (lc.std() * lt.std()))
print(f"corr(log chars sent, log tokens Laya counted) = {corr:.4f}")
odd = int(((ratio < 1.0) | (ratio > 6.0)).sum())
print(f"reviews with an implausible chars/token ratio (<1 or >6): {odd}")
print(f"truncated flag == (tokens dropped > 0): {sum(1 for r in R if bool(r['trunc']) == bool(r['drop']))}/{n}")
print(f"tokens read = state_tokens - dropped: max {max(r['tok'] - r['drop'] for r in R)}, "
      f"distribution of read tokens for truncated states: {Counter(r['tok'] - r['drop'] for r in R if r['drop']).most_common(3)}")
# 2. Did the question itself ever get cut?
tq = Counter(json.dumps(r["tq"]) for r in R)
print(f"truncated_questions values: {tq.most_common(4)}")
inp_minus_state = Counter(r["inp"] - r["tok"] for r in R)
print(f"input_tokens - state_tokens (question+criteria tokens): {inp_minus_state.most_common(5)}")
# 3. What sits in front of the code: the frame should be the bare 'Domain + label' header.
frames = Counter(r["chars"] - r["enriched"] for r in R if not r["cut"])
print(f"state chars - enriched chars (uncut): {frames.most_common(6)}")
# 4. Orientation: the vote must follow the larger probability, and p's must sum to ~1.
print(f"choice == decision: {sum(r['choice'] == r['dec'] for r in R)}/{n};  choice == argmax: "
      f"{sum((r['p'] > r['pa']) == (r['choice'] == 'REJECT') for r in R)}/{n};  "
      f"|pA+pR-1|>0.02: {sum(abs(r['p'] + r['pa'] - 1) > 0.02 for r in R)}")
# 5. How much does p(REJECT) move at all, and with what?
p = np.array([r["p"] for r in R])
print(f"p(REJECT): mean {p.mean():.3f} sd {p.std():.3f}; percentiles 1/10/50/90/99: "
      + " ".join(f"{np.percentile(p, q):.3f}" for q in (1, 10, 50, 90, 99)))
def by(key, min_n=200):
    g = defaultdict(list)
    for r in R:
        g[r[key]].append(r["p"])
    return {k: (len(v), round(float(np.mean(v)), 3)) for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])) if len(v) >= min_n}
print("mean p by domain:", by("dom"))
print("mean p by extension:", by("ext"))
print("mean p by repo:", by("repo", 300))
for lo, hi in ((0, 500), (500, 1000), (1000, 2000), (2000, 5000), (5000, 20000), (20000, 10**9)):
    v = [r["p"] for r in R if lo <= r["chars"] < hi]
    print(f"   state chars {lo:>5}-{hi:<10} n {len(v):>6}  mean p {np.mean(v):.3f}  sd {np.std(v):.3f}")
# share of p's variance that the domain header and the length explain (no BLAS: group means)
def r2_groups(keyf):
    g = defaultdict(list)
    for r in R:
        g[keyf(r)].append(r["p"])
    sse = sum(((np.array(v) - np.mean(v)) ** 2).sum() for v in g.values())
    return 1 - sse / ((p - p.mean()) ** 2).sum()
print(f"share of p's variance explained by domain: {r2_groups(lambda r: r['dom']):.3f}; by extension: "
      f"{r2_groups(lambda r: r['ext']):.3f}; by length decile: {r2_groups(lambda r: int(np.searchsorted(np.percentile(ch, range(10, 100, 10)), r['chars']))):.3f}; "
      f"by domain x length decile: {r2_groups(lambda r: (r['dom'], int(np.searchsorted(np.percentile(ch, range(10, 100, 10)), r['chars'])))):.3f}")
# 6. Shuffle test of the AUC code: random labels must give ~0.5.
lab = [(r["p"], r["y"] == "REJECT") for r in R if r["y"] in ("REJECT", "APPROVE")]
sc = np.array([a for a, _ in lab]); yy = np.array([b for _, b in lab])
def auc(score, pos):
    neg = np.sort(score[~pos]); lo = np.searchsorted(neg, score[pos], "left"); hi = np.searchsorted(neg, score[pos], "right")
    return float((lo + 0.5 * (hi - lo)).sum() / (pos.sum() * len(neg)))
rng = np.random.default_rng(1)
print(f"AUC with real labels {auc(sc, yy):.3f}; with shuffled labels: "
      + " ".join(f"{auc(sc, rng.permutation(yy)):.3f}" for _ in range(5)))
print(f"distinct p values: {len(set(np.round(sc, 6)))} of {len(sc)}")
