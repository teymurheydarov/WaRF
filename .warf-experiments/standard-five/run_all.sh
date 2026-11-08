#!/usr/bin/env bash
# Start N workers of one arm of run_standard.py and wait for all of them.
#     bash .warf-experiments/standard-five/run_all.sh five 4
#     bash .warf-experiments/standard-five/run_all.sh auditor5 4
cd /c/workdir/warf/WaRF || exit 1
arm=$1
n=${2:-4}
for k in $(seq 0 $((n - 1))); do
    PYTHONIOENCODING=utf-8 C:/workdir/claudeVersuch/gs/cf/python.exe -B .warf-experiments/standard-five/run_standard.py \
        --arm "$arm" --workers "$n" --worker "$k" > ".warf-experiments/standard-five/run.$arm.w$k.log" 2>&1 &
done
wait
