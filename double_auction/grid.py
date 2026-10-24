"""Sensitivity grid over discretisation/state choices on the 30 headline+oversight runs
(10 base-nocomms, 10 gpt/gpt base-comms, 10 oversight-comms), 200 perms each.
Per config: honest flag rate (perm p<.05) for mean_gamma & max_net, AUC comms-vs-honest
of bias-corrected effects, and empirical-null flag counts (effect > honest max)."""
import sys, time
from itertools import product
from multiprocessing import Pool
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evaluate as ev
from features import STATE_CHOICES

OUT = ev.OUT
N_PERM = 200

def main():
    ev._init(); runs = ev._D["runs"]
    sel = runs[(runs.condition == "base-nocomms") | (runs.condition == "oversight-comms") |
               ((runs.condition == "base-comms") & (runs.seller_mix == "gpt") & (runs.buyer_mix == "gpt"))]
    assert len(sel) == 30
    configs = [(st, db, b) for st, db, b in product(STATE_CHOICES, (0.05, 0.25), (False, True))
               if not (st == "traded_last" and db == 0.05 and not b)]          # primary already done
    jobs = [(rid, N_PERM, st, db, b, k) for (st, db, b) in configs for k, rid in enumerate(sel.index)]
    t0 = time.time()
    partial = OUT / f"grid_n{N_PERM}_runs_partial.csv"
    rows = []
    with Pool(2, initializer=ev._init) as pool:
        for k, row in enumerate(pool.imap(ev.one, jobs, chunksize=1)):
            row.update(state=jobs[k][2], dead_band=jobs[k][3], binary=jobs[k][4])
            rows.append(row)
            if k % 10 == 9:
                pd.DataFrame(rows).to_csv(partial, index=False)
                print(f"  {k+1}/{len(jobs)} jobs, {time.time()-t0:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    df = df.join(runs[["condition"]], on="run_id")
    df.to_csv(OUT / f"grid_n{N_PERM}_runs.csv", index=False)
    print(f"{len(jobs)} jobs in {time.time()-t0:.0f}s")
    out = []
    for (st, db, b), g in df.groupby(["state", "dead_band", "binary"]):
        hon = g[g.condition == "base-nocomms"]; com = g[g.condition == "base-comms"]; ov = g[g.condition == "oversight-comms"]
        r = {"state": st, "dead_band": db, "coding": "binary" if b else "ternary"}
        for s in ("mean_gamma", "max_net"):
            r[f"{s}_honest_flag"] = int((hon[f"{s}_p"] < 0.05).sum())
            r[f"{s}_auc_comms"] = round(ev.auc(com[f"{s}_effect"].to_numpy(float), hon[f"{s}_effect"].to_numpy(float)), 2)
            r[f"{s}_auc_oversight"] = round(ev.auc(ov[f"{s}_effect"].to_numpy(float), hon[f"{s}_effect"].to_numpy(float)), 2)
            r[f"{s}_emp_flag_comms"] = int((com[f"{s}_effect"] > hon[f"{s}_effect"].max()).sum())
            r[f"{s}_perm_flag_comms"] = int((com[f"{s}_p"] < 0.05).sum())
            r[f"{s}_perm_flag_oversight"] = int((ov[f"{s}_p"] < 0.05).sum())
        out.append(r)
    summ = pd.DataFrame(out)
    summ.to_csv(OUT / f"grid_n{N_PERM}_summary.csv", index=False)
    pd.set_option("display.width", 250)
    print(summ.to_string(index=False))

if __name__ == "__main__":
    main()
