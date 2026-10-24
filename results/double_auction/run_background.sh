#!/bin/bash
# Detached runner: sensitivity grid (200 perms) then primary config at 1000 perms.
cd /root/Think_Tank_Project/Think-Tank
PY=../llm-agent-collusion/.venv/bin/python
OUT=results/double_auction
$PY double_auction/grid.py > $OUT/grid_log.txt 2>&1; echo "grid exit $?" >> $OUT/grid_log.txt
$PY double_auction/evaluate.py 1000 > $OUT/eval_primary_n1000_log.txt 2>&1; echo "eval1000 exit $?" >> $OUT/eval_primary_n1000_log.txt
echo ALL_DONE >> $OUT/grid_log.txt
