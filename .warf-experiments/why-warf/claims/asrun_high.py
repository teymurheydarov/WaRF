"""As-run (weights moved) HIGH verdicts per pool in the 12-file persona experiment. Stored data only."""
import sys
from pathlib import Path
sys.path.insert(0, 'C:/workdir/warf/WaRF')
sys.path.insert(0, 'C:/workdir/warf/WaRF/tools')
from _groundtruth import corpus_truth, truth_for   # noqa: E402
from compare_pools import load_pool                # noqa: E402

truths = corpus_truth()
home = Path('C:/workdir/warf/WaRF/.warf-experiments')
for prof in ('persona_v3', 'h2h_auditor5', 'h2h_skeptic5'):
    pool = load_pool(home, prof)
    hi = []
    for a, s in sorted(pool.items()):
        t = truth_for(a, truths)
        x = t.x_star if t else s['oracle']['x_star']
        if s['confidence'] == 'HIGH':
            right = (1 if s['decision'] == 'APPROVE' else -1) == x
            hi.append((Path(a.replace(chr(92), '/')).name, s['decision'], 'right' if right else 'WRONG'))
    print(prof, 'as run: HIGH', len(hi), 'wrong', [h for h in hi if h[2] == 'WRONG'])
