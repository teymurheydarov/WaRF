"""Dump seat replies: x5 on the four x5-only clean rejects; strict on REAL items claude rejected and strict approved."""
import json, glob, sys
from pathlib import Path
HERE = Path(__file__).resolve().parents[2]

def recs(arm):
    out = {}
    for f in sorted(HERE.glob(arm + '.w*.jsonl')):
        for l in f.open(encoding='utf-8'):
            l = l.strip()
            if l:
                r = json.loads(l); out[r['planted']['id']] = r
    return out

def show(k, r):
    print('=' * 100); print(k, r['decision'])
    for v in r.get('votes', []):
        print('--- seat', v.get('agent'), v.get('label')); print(v.get('reasoning'))

mode = sys.argv[1]
if mode == 'x5':
    x5 = recs('claude-x5')
    for t in ['1050623:gsFitting.h', 'a60880c:gsWriteParaview.hpp', 'cd9af47:gsHTensorBasis.hpp', 'fbcf2aa:gsHElementMarker.hpp']:
        show(t, x5[t + ':clean'])
else:
    REAL = "06377a8 2a29aa6 2f8cd81 38858cf 3cf80c7 5853a6f 5f9ae79 6fc3f69 8058d91 890cd00 8ca586f 9b1851c af41faa c826b44 da35b0c e42bec0".split()
    one, st = recs('claude'), recs('claude-strict')
    for k in sorted(st):
        if not k.endswith(':clean') or k.split(':')[0] not in REAL: continue
        if one[k]['decision'] == 'REJECT' and st[k]['decision'] == 'APPROVE':
            print('#### claude reasoning'); show(k, one[k])
            print('#### strict reasoning'); show(k, st[k])
