"""A size-matched sample for a reference reviewer: every phase-A REJECT whose whole state
Laya read, each paired with the APPROVE of the same repository closest in patch size.
Writes blinded batch files (state text only, random ids) and a separate key."""
import json, math, random, secrets, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rebuild_state import HOME, load_plan, rebuild  # noqa: E402

BATCHES = int(sys.argv[1]) if len(sys.argv) > 1 else 8
OUT = Path(__file__).parent.parent / "claude-review"
(OUT / "batches").mkdir(parents=True, exist_ok=True)

labels = {}
with (HOME / "labels.jsonl").open(encoding="utf-8") as f:
    for lab in map(json.loads, f):
        labels[(lab["commit"], lab["file"])] = lab["label"]
rej, app = [], []
with (HOME / "sessions.jsonl").open(encoding="utf-8") as f:
    for s in map(json.loads, f):
        w = s.get("sweep")
        if not w or s.get("profile") != "laya_sweep" or w["phase"] != "A":
            continue
        if w["laya"]["usage"]["state_tokens_dropped"]:
            continue
        y = labels.get((w["commit"], w["file"]))
        if y not in ("REJECT", "APPROVE"):
            continue
        item = {"commit": w["commit"], "file": w["file"], "repo": w["repo"], "domain": s["domain"],
                "label": y, "p_laya": w["laya"]["probabilities"]["REJECT"], "patch_chars": w["patch_chars"],
                "state_chars": w["state_chars"]}
        (rej if y == "REJECT" else app).append(item)
print(f"fully read phase-A states: {len(rej)} REJECT, {len(app)} APPROVE")

rng = random.Random(11)
rng.shuffle(rej)
pairs_wanted = (len(rej) // BATCHES * 2 * BATCHES) // 2   # whole batches of equal size
rej = rej[:pairs_wanted]
used = set()
pairs = []
for r in rej:
    def dist(a):
        return abs(math.log(a["patch_chars"]) - math.log(r["patch_chars"]))
    same = [a for i, a in enumerate(app) if i not in used and a["repo"] == r["repo"]]
    cands = same or [a for i, a in enumerate(app) if i not in used]
    best = min(cands, key=dist)
    used.add(next(i for i, a in enumerate(app) if a is best))
    pairs.append((r, best))

plan = load_plan()
items = []
for r, a in pairs:
    for it in (r, a):
        state = rebuild(plan[it["commit"]], it["file"], it["domain"])
        if len(state) != it["state_chars"]:
            raise SystemExit(f"rebuilt state differs for {it['commit']} {it['file']}: {len(state)} vs {it['state_chars']}")
        it = dict(it, id=secrets.token_hex(3), state=state)
        items.append(it)
assert len({it["id"] for it in items}) == len(items)
rng.shuffle(items)

per = len(items) // BATCHES
key = []
for b in range(BATCHES):
    chunk = items[b * per:(b + 1) * per]
    with (OUT / "batches" / f"batch-{b + 1:02d}.txt").open("w", encoding="utf-8") as f:
        for it in chunk:
            f.write(f"<<<ITEM {it['id']}>>>\n{it['state']}\n<<<END {it['id']}>>>\n\n")
    for it in chunk:
        key.append({k: v for k, v in it.items() if k != "state"} | {"batch": b + 1})
    print(f"batch {b + 1:02d}: {len(chunk)} items, {sum(len(it['state']) for it in chunk)} chars, "
          f"{sum(it['label'] == 'REJECT' for it in chunk)} REJECT")
(OUT / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")


def auc(score, pos):
    P = [s for s, y in zip(score, pos) if y]
    N = [s for s, y in zip(score, pos) if not y]
    return sum((p > n) + 0.5 * (p == n) for p in P for n in N) / (len(P) * len(N))


y = [it["label"] == "REJECT" for it in key]
print(f"sample: {len(key)} items; AUC of patch size {auc([it['patch_chars'] for it in key], y):.3f}, "
      f"of state size {auc([it['state_chars'] for it in key], y):.3f}, of Laya's p(REJECT) "
      f"{auc([it['p_laya'] for it in key], y):.3f}; same repository in "
      f"{sum(r['repo'] == a['repo'] for r, a in pairs)}/{len(pairs)} pairs")
