import json,glob,os,sys
D=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ids=["06377a8:gsSurfMesh.cpp:clean","0696ac5:gsCatmullClark.cpp:clean","15977e9:gsSquareDomain.h:clean","2a29aa6:gsMultiPatch.hpp:clean","2f8cd81:gsBSpline.hpp:clean","38858cf:gsSquareDomain.h:clean","3cf80c7:gsRationalBasis.h:clean","5853a6f:gsExprEvaluator.h:clean","5f9ae79:gsExprAssembler.h:clean","6c02814:gsTHBSplineBasis.hpp:clean","6fc3f69:gsMultiBasis.hpp:clean","8058d91:gsHDomain.h:clean","890cd00:gsComposedGeometry.hpp:clean"]
def load(pat):
    r={}
    for f in sorted(glob.glob(os.path.join(D,pat))):
        for l in open(f,encoding='utf-8'):
            l=l.strip()
            if not l: continue
            j=json.loads(l); r[j['planted']['id']]=j
    return r
one=load('claude.w*.jsonl'); five=load('claude-standard.w*.jsonl')
items={json.loads(l)['id']:json.loads(l) for l in open(os.path.join(D,'items.jsonl'),encoding='utf-8')}
out=os.path.join(os.path.dirname(os.path.abspath(__file__)),'replies')
os.makedirs(out,exist_ok=True)
for i in ids:
    it=items[i]
    with open(os.path.join(out,i.replace(':','_')+'.txt'),'w',encoding='utf-8') as fh:
        fh.write(f"ID {i}\ncommit {it['commit']} file {it['file']} date {it['date']} subj {it['subject']}\n")
        o=one.get(i)
        fh.write(f"\n=== ONE decision {o['decision'] if o else None}\n")
        if o:
            for v in o['votes']: fh.write(f"[{v['label']}] {v['reasoning']}\n")
        f=five.get(i)
        fh.write(f"\n=== FIVE decision {f['decision'] if f else None}\n")
        if f:
            for v in f['votes']: fh.write(f"--- {v['agent']} [{v['label']}]\n{v['reasoning']}\n")
        fh.write("\n=== DIFF\n"+it['code']+"\n")
    print(i, o and o['decision'], f and f['decision'], f and [v['label'][0] for v in f['votes']])
