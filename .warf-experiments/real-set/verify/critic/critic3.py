"""Timing vs README, single-arm decision==vote, W1 zero-REJECT misses. Run from real-set/."""
import json, glob, os, datetime
items=[json.loads(l) for l in open('items.jsonl',encoding='utf-8')]
D={i['id']:i['kind']=='defective' for i in items}
for a in ('jev','claude','claude-strict','claude-advocate','claude-standard'):
    rs=[json.loads(l) for p in glob.glob(f'{a}.w*.jsonl') for l in open(p,encoding='utf-8')]
    ts=sorted(r['created_at'] for r in rs)
    mism=sum((r['decision']=='REJECT')!=(r['votes'][0]['vote']==-1) for r in rs) if a!='claude-standard' else '-'
    print(f'{a:16s} n={len(rs)} first {ts[0]} last {ts[-1]} decision!=vote: {mism}')
for f in ('README.md','score_real.py','items.jsonl'):
    print(f, datetime.datetime.fromtimestamp(os.path.getmtime(f),datetime.timezone.utc).isoformat())
for p in glob.glob('claude-standard.w*.jsonl'):
    for l in open(p,encoding='utf-8'):
        r=json.loads(l); i=r['planted']['id']
        if D[i] and r['decision']=='APPROVE':
            print('W1 miss', i, ''.join('R' if v['vote']==-1 else 'a' for v in r['votes']), [v['agent'][:3] for v in r['votes']])
