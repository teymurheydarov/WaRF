import json,glob,sys
ids=["0696ac5:gsCatmullClark.cpp:clean","15977e9:gsSquareDomain.h:clean","3cf80c7:gsRationalBasis.h:clean","6c02814:gsTHBSplineBasis.hpp:clean","bfbe226:gsComposedGeometry.h:clean","c0c88af:gsAABB.h:clean"]
r=json.loads(open('claude.w0.jsonl',encoding='utf-8').readline())
print([k for k in r.keys()])
def pid(rec):
    p=rec.get('planted') or {}
    return p.get('id')
out=open('verify/judgeB/replies.txt','w',encoding='utf-8')
for arm in ['claude','claude-standard']:
    for f in sorted(glob.glob(arm+'.w*.jsonl')):
        for line in open(f,encoding='utf-8'):
            rec=json.loads(line)
            if pid(rec) in ids:
                out.write(f"\n===== {pid(rec)} | {f} | final={rec.get('decision') or rec.get('final') or rec.get('verdict')}\n")
                for v in rec['votes']:
                    out.write(f"--- {v['agent']} {v['label']} persona={v.get('persona')}\n{v['reasoning']}\n")
items=[json.loads(l) for l in open('items.jsonl',encoding='utf-8')]
for it in items:
    if it['id'] in ids:
        open('verify/judgeB/'+it['id'].replace(':','_')+'.diff','w',encoding='utf-8').write(it['code'])
        print(it['id'],it['commit'],it['date'],it['file'],it['subject'])
