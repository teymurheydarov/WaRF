"""W1 decision vs its own seats; reasons for W1-only correct items. Run from real-set/."""
import json, glob, collections, itertools
items=[json.loads(l) for l in open('items.jsonl',encoding='utf-8')]
D={i['id']:i['kind']=='defective' for i in items}; ids=list(D)
W={}
for p in glob.glob('claude-standard.w*.jsonl'):
    for l in open(p,encoding='utf-8'):
        r=json.loads(l); W[r['planted']['id']]=r
dec={i:W[i]['decision']=='REJECT' for i in ids}
seat={i:{v['agent']:v['vote']==-1 for v in W[i]['votes']} for i in ids}
for s in ('ADVOCATE','SKEPTIC','AUDITOR','TEST-FOCUSED'):
    S=[i for i in ids if s in seat[i]]
    print(s,'W1 decision == seat vote on',sum(dec[i]==seat[i][s] for i in S),'/',len(S))
nrej=collections.Counter((D[i],len(seat[i]),sum(seat[i].values()),dec[i]) for i in ids)
print('(defective, nseats, nREJECT, W1 REJECT): count'); [print(' ',k,v) for k,v in sorted(nrej.items())]
# best 2-of / k-of-n rules over the 4 always-present seats (post hoc, in-sample)
four=['ADVOCATE','SKEPTIC','AUDITOR','TEST-FOCUSED']
def ba(R):
    P=[i for i in ids if D[i]];N=[i for i in ids if not D[i]]
    return (sum(R[i] for i in P)/len(P)+sum(not R[i] for i in N)/len(N))/2
for k in range(1,5):
    R={i:sum(seat[i].get(s,True) for s in four)>=k for i in ids}
    print(f'>= {k} of 4 seats REJECT: BA {ba(R):.3f}')
print('05e9cec', [(v['agent'],v['label']) for v in W['05e9cec:gsKnotVector_.cpp:clean']['votes']], W['05e9cec:gsKnotVector_.cpp:clean']['sprt_fired'], W['05e9cec:gsKnotVector_.cpp:clean']['planted']['seconds'])
