import json, glob, sys
ids = ["8ca586f:gsParaviewUtils.h:clean","9b1851c:gsMobiusDomain.h:clean","a86cf94:gsSquareDomain.h:clean","a880e56:gsOptProblem.h:clean","af41faa:gsWriteParaview.hpp:clean","bfbe226:gsComposedGeometry.h:clean","c0c88af:gsAABB.h:clean","c826b44:gsComposedBasis.h:clean","d9fca63:gsComposedGeometry.h:clean","da35b0c:gsSysInfo.cpp:clean","db3aca7:gsXmlUtils.hpp:clean","e42bec0:gsExprEvaluator.h:clean"]
which = sys.argv[1]
out = {i:{} for i in ids}
for arm in ['claude','claude-standard']:
    for f in sorted(glob.glob(arm+'.w*.jsonl')):
        for line in open(f,encoding='utf-8'):
            r=json.loads(line)
            pid=r.get('planted',{}).get('id')
            if pid==which:
                print('=====',arm,f,r['decision'])
                for v in r['votes']:
                    print('---',v['agent'],v.get('persona'),v['label'])
                    print(v['reasoning'])
