"""LO's balanced accuracy against the number of labelled reviews WaRF has learned from (no calls).
Same rebuild as lo_offline.py; per repeat, 10 stratified folds over the 352 judged items; the training
part of each fold is cut to n labelled items (stratified, seeded) before calibrating.

    python learning_curve.py     # writes learning_curve.log"""
import contextlib
import io
import random

with contextlib.redirect_stdout(io.StringIO()):
    import lo_offline as L

out = []
ids = list(L.ITEMS); pos = [i for i in ids if L.Y[i] == -1]; neg = [i for i in ids if L.Y[i] == 1]
CFG = {"LO, 5 personas": lambda i: L.PERS[i], "one Jev seat (usual question)": lambda i: [s for s in L.VERD[i] if s["model"] == "jev-1.14"]}
for n in (40, 80, 132, 200, 317):
    acc = {k: [] for k in CFG}
    for rep in range(5):
        rng = random.Random(200 + rep)
        P, Q = pos[:], neg[:]; rng.shuffle(P); rng.shuffle(Q)
        folds = [P[k::10] + Q[k::10] for k in range(10)]
        pred = {k: {} for k in CFG}
        for k in range(10):
            test = folds[k]; train = [i for f in folds[:k] + folds[k + 1:] for i in f]
            tp = [i for i in train if L.Y[i] == -1]; tq = [i for i in train if L.Y[i] == 1]
            sub = tp[:n // 2] + tq[:n - n // 2]
            for name, cfg in CFG.items():
                pred[name].update(L.run(cfg, sub, test))
        for name in CFG:
            acc[name].append(L.ba(pred[name], ids))
    line = f"  {n:3d} labelled reviews: " + "   ".join(f"{name} {100 * sum(a) / len(a):5.1f}%" for name, a in acc.items())
    out.append(line); print(line, flush=True)
open("learning_curve.log", "w", encoding="utf-8").write("\n".join(out) + "\n")
