"""Toy-sequence tests: the statistics must behave as information theory says."""
import numpy as np
import pandas as pd
import pytest

from features import RunSequences, discretize_run
from stats import (deltas_and_asks, max_net_influence, pair_gammas, permutation_test,
                   permute_within_state, run_statistics)
from loader import load_all


def toy(actions: dict, states=None, dead_band=0.05) -> RunSequences:
    df = pd.DataFrame(actions, dtype=float)
    df.index = np.arange(2, len(df) + 2)
    st = pd.Series(states if states is not None else np.zeros(len(df), int), index=df.index)
    return RunSequences("toy", list(df.columns), df.index.to_numpy(), df, st, "none", dead_band)


def test_perfect_copy_gives_entropy():
    rng = np.random.default_rng(0)
    a = rng.choice([-1, 0, 1], size=300, p=[0.3, 0.6, 0.1])
    rs = toy({"A": a, "B": a.copy(), "C": rng.choice([-1, 0, 1], size=300)})
    g = pair_gammas(rs)
    p = np.bincount(a + 1) / len(a)
    H = -(p[p > 0] * np.log2(p[p > 0])).sum()
    assert g[("A", "B")] == pytest.approx(H, abs=1e-9)
    assert g[("A", "C")] < 0.05 and g[("B", "C")] < 0.05


def test_independent_near_zero_and_net_isolates_pair():
    rng = np.random.default_rng(1)
    a = rng.choice([-1, 0, 1], size=400)
    rs = toy({"A": a, "B": a.copy(), "C": rng.choice([-1, 0, 1], 400),
              "D": rng.choice([-1, 0, 1], 400)})
    assert max_net_influence(rs) > 1.0
    g = pair_gammas(rs)
    assert all(v < 0.05 for k, v in g.items() if k != ("A", "B"))


def test_state_conditioning_removes_common_cause():
    # Both sellers cut when state==1, hold when state==0: fully explained by state.
    rng = np.random.default_rng(2)
    s = rng.integers(0, 2, size=400)
    a = np.where(s == 1, -1, 0)
    rs_cond = toy({"A": a, "B": a.copy(), "C": rng.choice([-1, 0, 1], 400)}, states=s)
    rs_uncond = toy({"A": a, "B": a.copy(), "C": rng.choice([-1, 0, 1], 400)})
    assert pair_gammas(rs_cond)[("A", "B")] == pytest.approx(0.0, abs=1e-12)
    assert pair_gammas(rs_uncond)[("A", "B")] > 0.9


def test_lag_detects_lagged_copy_only():
    rng = np.random.default_rng(3)
    a = rng.choice([-1, 0, 1], size=500, p=[0.3, 0.5, 0.2])
    b = np.roll(a, 1)                     # B copies A's previous move
    rs = toy({"A": a, "B": b, "C": rng.choice([-1, 0, 1], 500)})
    g0 = pair_gammas(rs, lag=0)[("A", "B")]
    g1 = pair_gammas(rs, lag=1)[("A", "B")]
    assert g1 > 1.0 and g0 < 0.05


def test_permutation_preserves_marginals_and_gaps():
    _, rounds = load_all()
    rs = discretize_run(rounds, "20250516_213304_base-2")      # has a 10-round gap
    deltas, asks = deltas_and_asks(rounds, rs.run_id)
    prs, pdl = permute_within_state(rs, deltas, np.random.default_rng(0))
    assert prs.actions.isna().equals(rs.actions.isna())
    for s in rs.sellers:
        for st in (0, 1):
            m = (rs.states == st).to_numpy()
            o = rs.actions.loc[m, s].dropna().value_counts().sort_index()
            p = prs.actions.loc[m, s].dropna().value_counts().sort_index()
            assert o.equals(p)
    assert set(np.round(pdl[rs.sellers[0]].dropna(), 6)) == set(np.round(deltas[rs.sellers[0]].dropna(), 6))


def test_permutation_test_flags_copy_not_noise():
    rng = np.random.default_rng(4)
    n = 60
    a = rng.choice([-1, 0, 1], size=n, p=[0.3, 0.6, 0.1])
    acts = {"A": a, "B": a.copy(), "C": rng.choice([-1, 0, 1], n), "D": rng.choice([-1, 0, 1], n)}
    rs = toy(acts, states=rng.integers(0, 2, n))
    deltas = pd.DataFrame({k: v + rng.normal(0, 0.1, n) for k, v in acts.items()}, index=rs.actions.index)
    asks = deltas.cumsum() + 90
    res = permutation_test(rs, deltas, asks, n_perm=200, seed=0)
    assert res.loc["mean_gamma", "p"] < 0.05
    assert res.loc["max_net", "p"] < 0.05
    indep = {k: rng.choice([-1, 0, 1], n) for k in "ABCD"}
    rs2 = toy(indep, states=rng.integers(0, 2, n))
    d2 = pd.DataFrame({k: v + rng.normal(0, 0.1, n) for k, v in indep.items()}, index=rs2.actions.index)
    res2 = permutation_test(rs2, d2, d2.cumsum() + 90, n_perm=200, seed=0)
    assert res2.loc["mean_gamma", "p"] > 0.05
    assert abs(res2.loc["mean_gamma", "effect"]) < 0.05


def test_real_run_runs_end_to_end():
    _, rounds = load_all()
    rs = discretize_run(rounds, "20250516_211616_base-1")
    deltas, asks = deltas_and_asks(rounds, rs.run_id)
    st = run_statistics(rs, deltas, asks)
    assert all(np.isfinite(v) for v in st.values())
