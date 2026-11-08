from load import *
ids = [it["id"] for it in items]; D = {i: by_id[i]["kind"]=="defective" for i in ids}
def nadd(i): return sum(1 for l in by_id[i]["code"].split("\n") if l.startswith("+") and not l.startswith("+++"))
def ba(pred):
    P=[i for i in ids if D[i]]; N=[i for i in ids if not D[i]]
    return (sum(pred[i] for i in P)/len(P)+sum(not pred[i] for i in N)/len(N))/2, sum(pred[i] for i in P), sum(pred[i] for i in N)
best = max(((ba({i: nadd(i)>=k for i in ids}), k) for k in range(1,60)), key=lambda x: x[0][0])
print("best in-sample threshold: added>=%d BA %.3f recall %d/66 FA %d/66" % (best[1], *best[0]))
for k in (3,5,10):
    b = ba({i: nadd(i)>=k for i in ids}); print(f"added>={k}: BA {b[0]:.3f} recall {b[1]}/66 FA {b[2]}/66")
# leave-one-out threshold choice (honest)
ok=0
for j in ids:
    rest=[i for i in ids if i!=j]
    def bar(k):
        P=[i for i in rest if D[i]]; N=[i for i in rest if not D[i]]
        return (sum(nadd(i)>=k for i in P)/len(P)+sum(nadd(i)<k for i in N)/len(N))/2
    k=max(range(1,60), key=bar); ok += ((nadd(j)>=k)==D[j])
print("LOO threshold accuracy (=BA, balanced classes):", ok/len(ids))
# arms by size bucket
for lo,hi in ((0,2),(3,9),(10,10**6)):
    S=[i for i in ids if lo<=nadd(i)<=hi]
    print(f"added {lo}-{hi}: n={len(S)} defective {sum(D[i] for i in S)} clean {sum(not D[i] for i in S)}; reject rate on clean:",
          {a: f"{sum(rej(a,i) for i in S if not D[i])}" for a in ("claude","claude-strict","claude-advocate","claude-standard","jev")},
          "recall:", {a: f"{sum(rej(a,i) for i in S if D[i])}" for a in ("claude","claude-strict","claude-standard")})
