"""Controls, run on base no-comms runs ONLY (comms runs are never touched here).

1. honest      -- permutation test on each of the 10 honest runs (1000 perms).
                  Flag rate at alpha=0.05 is the calibration check for the null.
2. inject_same -- seller B's actions replaced by seller A's same-round actions with
                  20% noise. mean_gamma / max_net must fire; (A,B) must be the argmax
                  net-influence pair.
3. inject_lag  -- seller B's actions replaced by A's previous-round actions (20% noise).
                  lag-1 effect must rise; same-round effect should not rise relative
                  to the honest run.
4. cross_run   -- pairwise MI between sellers taken from two *different* honest runs
                  (round-aligned). These sellers share model, prompt, valuations and
                  market structure but cannot have communicated: a channel-free null
                  for within-run pair MI. No permutations needed.
"""
from __future__ import annotations

import sys
import time
from itertools import combinations, product
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bonjour import calculate_individual_influence  # noqa: E402
from features import discretize_run  # noqa: E402
from loader import load_all  # noqa: E402
from stats import deltas_and_asks, max_net_influence, pair_gammas, permutation_test  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "results" / "double_auction"
NOISE = 0.2
_DATA = {}


def _init():
    _DATA["runs"], _DATA["rounds"] = load_all()


def _inject(rs, deltas, mode: str, rng: np.random.Generator):
    """Return (rs', deltas', (A, B)). Picks A,B = the two sellers with fewest NaNs."""
    nan_counts = rs.actions.isna().sum().sort_values()
    A, B = nan_counts.index[0], nan_counts.index[1]
    acts = rs.actions.copy()
    dl = deltas.copy()
    src_a = acts[A].shift(1) if mode == "inject_lag" else acts[A]
    src_d = dl[A].shift(1) if mode == "inject_lag" else dl[A]
    new_b = src_a.copy()
    new_d = src_d.copy()
    noise = rng.random(len(new_b)) < NOISE
    # at noise positions keep B's own original action/delta
    new_b[noise] = acts[B][noise]
    new_d[noise] = dl[B][noise]
    # keep B's original gaps as gaps
    new_b[acts[B].isna()] = np.nan
    new_d[dl[B].isna()] = np.nan
    acts[B] = new_b
    dl[B] = new_d
    rs2 = type(rs)(run_id=rs.run_id, sellers=rs.sellers, rounds=rs.rounds, actions=acts,
                   states=rs.states, state_name=rs.state_name, dead_band=rs.dead_band)
    return rs2, dl, (A, B)


def one_job(args):
    run_id, mode, n_perm, seed = args
    rounds = _DATA["rounds"]
    rs = discretize_run(rounds, run_id, dead_band=0.05, state="traded_last")
    deltas, asks = deltas_and_asks(rounds, run_id)
    pair = None
    if mode != "honest":
        rs, deltas, pair = _inject(rs, deltas, mode, np.random.default_rng(seed + 100))
    t0 = time.time()
    res = permutation_test(rs, deltas, asks, n_perm=n_perm, seed=seed)
    row = {"run_id": run_id, "mode": mode, "n_perm": n_perm, "secs": round(time.time() - t0, 1)}
    for stat, r in res.iterrows():
        row[f"{stat}_obs"] = r["observed"]
        row[f"{stat}_effect"] = r["effect"]
        row[f"{stat}_p"] = r["p"]
    if pair is not None:
        from bonjour import calculate_net_influence
        acts, st = rs.common()
        _, net = calculate_net_influence(acts, st)
        best = max(net, key=net.get)
        row["injected_pair"] = f"{pair[0]}|{pair[1]}"
        row["argmax_net_pair"] = f"{best[0]}|{best[1]}"
        row["net_isolates_pair"] = set(best) == set(pair)
    return row


def cross_run(runs, rounds, base_ids, state: str):
    seqs = {rid: discretize_run(rounds, rid, dead_band=0.05, state=state) for rid in base_ids}
    within, cross = [], []
    for rid, rs in seqs.items():
        for (i, j), g in pair_gammas(rs).items():
            within.append({"run_a": rid, "run_b": rid, "i": i, "j": j, "gamma": g})
    for ra, rb in combinations(base_ids, 2):
        A, B = seqs[ra], seqs[rb]
        idx = A.actions.index.intersection(B.actions.index)
        st = A.states.loc[idx].to_numpy()               # state from run A (arbitrary but fixed)
        for i, j in product(A.sellers, B.sellers):
            ai = A.actions.loc[idx, i].to_numpy()
            aj = B.actions.loc[idx, j].to_numpy()
            ok = ~np.isnan(ai) & ~np.isnan(aj)
            if ok.sum() < 2:
                continue
            g = calculate_individual_influence(ai[ok].astype(int).tolist(), aj[ok].astype(int).tolist(), st[ok].tolist())
            cross.append({"run_a": ra, "run_b": rb, "i": i, "j": j, "gamma": g, "n": int(ok.sum())})
    return pd.DataFrame(within), pd.DataFrame(cross)


def main(n_perm_honest=1000, n_perm_inject=200, workers=2):
    _init()
    runs, rounds = _DATA["runs"], _DATA["rounds"]
    base_ids = list(runs.index[runs.condition == "base-nocomms"])
    assert len(base_ids) == 10

    jobs = [(rid, "honest", n_perm_honest, k) for k, rid in enumerate(base_ids)]
    jobs += [(rid, "inject_same", n_perm_inject, k) for k, rid in enumerate(base_ids)]
    jobs += [(rid, "inject_lag", n_perm_inject, k) for k, rid in enumerate(base_ids)]
    t0 = time.time()
    with Pool(workers, initializer=_init) as pool:
        rows = pool.map(one_job, jobs, chunksize=1)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "controls_permutation.csv", index=False)
    print(f"permutation jobs done in {time.time()-t0:.0f}s\n")

    pd.set_option("display.width", 200)
    cols = ["run_id", "mean_gamma_effect", "mean_gamma_p", "max_net_effect", "max_net_p",
            "mean_gamma_lag1_effect", "mean_gamma_lag1_p", "mean_corr_effect", "mean_corr_p"]
    for mode in ("honest", "inject_same", "inject_lag"):
        sub = df[df["mode"] == mode].copy()
        sub["run_id"] = sub["run_id"].str.replace(r"^\d+_\d+_", "", regex=True)
        print(f"=== {mode} ===")
        extra = ["net_isolates_pair"] if mode != "honest" else []
        print(sub[cols + extra].round(3).to_string(index=False))
        flags = {s: int((sub[f"{s}_p"] < 0.05).sum()) for s in ("mean_gamma", "max_net", "mean_gamma_lag1", "mean_corr")}
        print("flagged at alpha=0.05 (of 10):", flags, "\n")

    for state in ("none", "traded_last"):
        w, c = cross_run(runs, rounds, base_ids, state)
        w.to_csv(OUT / f"cross_run_within_{state}.csv", index=False)
        c.to_csv(OUT / f"cross_run_cross_{state}.csv", index=False)
        q = [0.05, 0.25, 0.5, 0.75, 0.95]
        print(f"=== cross-run control, state={state} ===")
        print(f"within-run pairs n={len(w)}: ", w.gamma.quantile(q).round(3).to_dict(), " mean", round(w.gamma.mean(), 3))
        print(f"cross-run  pairs n={len(c)}: ", c.gamma.quantile(q).round(3).to_dict(), " mean", round(c.gamma.mean(), 3))
        thr = c.gamma.quantile(0.95)
        print(f"within-run pairs above cross-run 95th pct ({thr:.3f}): {(w.gamma > thr).mean():.2f}")
        per_run = w.groupby("run_a").gamma.mean()
        cross_run_means = c.groupby(["run_a", "run_b"]).gamma.mean()
        print(f"per-run mean gamma (within) : {per_run.round(3).tolist()}")
        print(f"cross-run-pair mean gamma   : 5/50/95 pct = {cross_run_means.quantile([.05,.5,.95]).round(3).tolist()}\n")


if __name__ == "__main__":
    main()
