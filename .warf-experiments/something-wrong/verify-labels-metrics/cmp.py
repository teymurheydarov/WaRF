import json
c=json.load(open('feats.json',encoding='utf-8'))
F={json.loads(l)['id']:json.loads(l) for l in open('../../jev-five/verify/refute/features.jsonl',encoding='utf-8')}
n=0
for i,v in c.items():
    f=F[i]
    if v['added']!=f['added'] or v['removed']!=f['removed']:
        n+=1; print(i,f['label'],f['status'],'mine',v['added'],v['removed'],'theirs',f['added'],f['removed'],f['file'])
print('differ',n)
