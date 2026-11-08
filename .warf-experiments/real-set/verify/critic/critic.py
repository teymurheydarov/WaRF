"""Critic checks on the real-set (read-only; pure Python). Run from real-set/: python -B verify/critic/critic.py"""
import json, glob, collections, random, math, re
items=[json.loads(l) for l in open('items.jsonl',encoding='utf-8')]
by={i['id']:i for i in items}; D={i['id']:i['kind']=='defective' for i in items}; ids=[i['id'] for i in items]
recs={}
for a in ('claude','claude-strict','claude-advocate','claude-standard','jev'):
    recs[a]={}
    for p in sorted(glob.glob(f'{a}.w*.jsonl')):
        for l in open(p,encoding='utf-8'):
            r=json.loads(l); recs[a][r['planted']['id']]=r
rej={a:{i:recs[a][i]['decision']=='REJECT' for i in ids} for a in recs}
def ba(R,S):
    P=[i for i in S if D[i]];N=[i for i in S if not D[i]]
    if not P or not N: return float('nan')
    return (sum(R[i] for i in P)/len(P)+sum(not R[i] for i in N)/len(N))/2
print('domains',collections.Counter(i['domain'] for i in items), 'theta',collections.Counter(recs['claude-standard'][i]['theta'] for i in ids))
# cost
for a in ('claude','claude-strict','claude-advocate','claude-standard'):
    sec=sum(recs[a][i]['planted']['seconds'] for i in ids)
    calls=sum(len(recs[a][i]['planted'].get('calls',[0])) for i in ids)
    ch=sum(sum(c['sent_chars'] for c in recs[a][i]['planted'].get('calls',[recs[a][i]['planted'].get('call')])) for i in ids)
    print(f'cost {a:16s} calls {calls:4d} wall-s {sec:8.0f} sent_chars {ch}')
# persona hashes
ph=collections.defaultdict(set)
for a in ('claude','claude-strict','claude-advocate','claude-standard'):
    for i in ids:
        for v in recs[a][i]['votes']: ph[(a,v['agent'])].add(v['persona'])
for k,v in sorted(ph.items()): print('persona',k,v)
# seat-level in W1
seats=collections.defaultdict(dict)
for i in ids:
    for v in recs['claude-standard'][i]['votes']: seats[v['agent']][i]=v['vote']==-1
print('W1 seat presence', {s:len(m) for s,m in seats.items()})
for s,m in seats.items():
    S=list(m); P=[i for i in S if D[i]];N=[i for i in S if not D[i]]
    print(f'seat {s:14s} n={len(S)} recall {sum(m[i] for i in P)}/{len(P)} FA {sum(m[i] for i in N)}/{len(N)} BA {ba(m,S):.3f}')
# which seat order / which missing when stopped
miss=collections.Counter(tuple(sorted(set(seats)-{v['agent'] for v in recs['claude-standard'][i]['votes']})) for i in ids)
print('missing seats', miss)
# noise floor: W1 ADVOCATE seat vs standalone advocate on same item
for seat,arm in (('ADVOCATE','claude-advocate'),):
    S=[i for i in ids if i in seats[seat]]
    ag=sum(seats[seat][i]==rej[arm][i] for i in S)
    print(f'{seat} seat in W1 vs {arm} arm: agree {ag}/{len(S)}; seat BA on these {ba(seats[seat],S):.3f} arm BA on these {ba(rej[arm],S):.3f}')
# W1 seat with 5 seats only (unbiased by stopping)
full=[i for i in ids if len(recs['claude-standard'][i]['votes'])==5]
print('items with 5 seats',len(full), 'defective',sum(D[i] for i in full))
# Pareto
for a in rej: 
    P=[i for i in ids if D[i]]
    print(f'{a:16s} recall {sum(rej[a][i] for i in P)} FA {sum(rej[a][i] for i in ids if not D[i])} BA {ba(rej[a],ids):.3f}')
# W1 vs advocate item-level
w,s='claude-standard','claude-advocate'
print('W1 vs advocate discordant', [(i, 'W1 right' if rej[w][i]==D[i] else 'adv right') for i in ids if rej[w][i]!=rej[s][i]])
# simple non-preregistered single-call ensembles (no new calls)
def maj(arms): return {i: sum(rej[a][i] for a in arms)*2>len(arms) for i in ids}
def AND(arms): return {i: all(rej[a][i] for a in arms) for i in ids}
for name,R in (('maj(claude,strict,adv)',maj(['claude','claude-strict','claude-advocate'])),('strict AND adv',AND(['claude-strict','claude-advocate'])),('strict OR adv',{i:rej['claude-strict'][i] or rej['claude-advocate'][i] for i in ids})):
    print(f'{name:24s} BA {ba(R,ids):.3f} recall {sum(R[i] for i in ids if D[i])} FA {sum(R[i] for i in ids if not D[i])}')
# added lines
def added(it):
    return sum(1 for l in it['code'].splitlines() if l.startswith('+') and not l.startswith('+++'))
A={i:added(by[i]) for i in ids}
def med(x): x=sorted(x); n=len(x); return (x[n//2]+x[(n-1)//2])/2
print('median added: defective',med([A[i] for i in ids if D[i]]),'clean',med([A[i] for i in ids if not D[i]]))
# AUC of added
P=[A[i] for i in ids if D[i]];N=[A[i] for i in ids if not D[i]]
auc=sum((p>n)+0.5*(p==n) for p in P for n in N)/(len(P)*len(N)); print('AUC added lines',round(auc,3))
# best in-sample threshold
best=max(((ba({i:A[i]>=t for i in ids},ids),t) for t in sorted(set(A.values()))));print('best size rule (in-sample) BA %.3f at added>=%d'%best)
# strata by added lines
bins=[(0,2),(3,8),(9,30),(31,10**9)]
print('stratum counts and BA per arm')
for lo,hi in bins:
    S=[i for i in ids if lo<=A[i]<=hi]
    print(f' added {lo}-{hi}: def {sum(D[i] for i in S)} clean {sum(not D[i] for i in S)} | '+' '.join(f'{a.replace("claude-","")}:{ba(rej[a],S):.2f}' for a in ('claude','claude-strict','claude-advocate','claude-standard')))
# size-reweighted BA: weight clean items so clean size distribution matches defective one per stratum
def wba(R):
    tot=0;wsum=0;recall_num=0
    P=[i for i in ids if D[i]]
    rec=sum(R[i] for i in P)/len(P)
    spec=0
    for lo,hi in bins:
        Pp=[i for i in P if lo<=A[i]<=hi]; Nn=[i for i in ids if not D[i] and lo<=A[i]<=hi]
        if not Nn: continue
        w=len(Pp)/len(P); spec+=w*sum(not R[i] for i in Nn)/len(Nn); wsum+=w
    return (rec+spec/wsum)/2
print('size-reweighted BA (clean specificity reweighted to defective size mix):',{a:round(wba(rej[a]),3) for a in ('claude','claude-strict','claude-advocate','claude-standard','jev')})
json.dump({'added':A},open('verify/critic/added.json','w'))
