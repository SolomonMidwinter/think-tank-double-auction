"""Per-run dependence statistics and a gap-preserving permutation null.

Reuses the team's implementation in ../bonjour.py for the information-theoretic
quantities so there is exactly one definition of gamma / net influence.

Statistics per run (all higher = more dependence):
    mean_gamma   -- mean over unordered seller pairs of the state-conditioned
                    same-round mutual information gamma(i;j)       [PRIMARY]
    max_net      -- max over ordered pairs of net influence Gamma(i;j), computed on
                    rounds where all sellers are observed              [subset detector]
    mean_gamma_lag1 -- same as mean_gamma but pairs i's action at t-1 with j's at t
    mean_corr    -- mean pairwise Pearson correlation of raw ask changes (baseline)
    neg_dispersion -- minus the mean within-round std of asks (paper's metric; sign
                    flipped so that higher = more aligned)

The permutation null shuffles each seller's actions independently, within each
state, among the rounds where that seller is observed. Missing rounds stay missing.
This breaks same-round coupling between sellers while preserving each seller's
action distribution per state. Raw ask changes are shuffled with the same
permutation so the correlation baseline is calibrated identically.
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bonjour import calculate_individual_influence, calculate_net_influence  # noqa: E402

from features import RunSequences  # noqa: E402

STAT_NAMES = ("mean_gamma", "max_net", "mean_gamma_lag1", "mean_corr", "neg_dispersion")


def pair_gammas(rs: RunSequences, lag: int = 0) -> dict[tuple[str, str], float]:
    out = {}
    for i, j in combinations(rs.sellers, 2):
        ai, aj, st = rs.pair(i, j, lag=lag)
        out[(i, j)] = calculate_individual_influence(ai, aj, st) if len(st) >= 2 else np.nan
    return out


def max_net_influence(rs: RunSequences) -> float:
    acts, st = rs.common()
    if len(st) < 2:
        return np.nan
    _, net = calculate_net_influence(acts, st)
    return max(net.values())


def mean_corr(deltas: pd.DataFrame) -> float:
    c = deltas.corr(min_periods=3)
    vals = c.where(np.triu(np.ones(c.shape, bool), 1)).stack(future_stack=True).dropna()
    return float(vals.mean()) if len(vals) else np.nan


def neg_dispersion(asks: pd.DataFrame) -> float:
    return -float(asks.std(axis=1, ddof=0).mean())


def run_statistics(rs: RunSequences, deltas: pd.DataFrame, asks: pd.DataFrame) -> dict[str, float]:
    g = pair_gammas(rs, lag=0)
    g1 = pair_gammas(rs, lag=1)
    return {
        "mean_gamma": float(np.nanmean(list(g.values()))),
        "max_net": max_net_influence(rs),
        "mean_gamma_lag1": float(np.nanmean(list(g1.values()))),
        "mean_corr": mean_corr(deltas),
        "neg_dispersion": neg_dispersion(asks),
    }


def permute_within_state(rs: RunSequences, deltas: pd.DataFrame, rng: np.random.Generator
                         ) -> tuple[RunSequences, pd.DataFrame]:
    """Shuffle each seller's actions (and raw deltas, identically) within state,
    among that seller's observed rounds only."""
    acts = rs.actions.to_numpy(copy=True)
    dl = deltas.loc[rs.actions.index, rs.sellers].to_numpy(copy=True)
    states = rs.states.to_numpy()
    for k in range(acts.shape[1]):
        obs = ~np.isnan(acts[:, k])
        for s in np.unique(states[obs]):
            idx = np.flatnonzero(obs & (states == s))
            if len(idx) > 1:
                perm = rng.permutation(idx)
                acts[idx, k] = acts[perm, k]
                dl[idx, k] = dl[perm, k]
    new_rs = RunSequences(run_id=rs.run_id, sellers=rs.sellers, rounds=rs.rounds,
                          actions=pd.DataFrame(acts, index=rs.actions.index, columns=rs.sellers),
                          states=rs.states, state_name=rs.state_name, dead_band=rs.dead_band)
    return new_rs, pd.DataFrame(dl, index=rs.actions.index, columns=rs.sellers)


def permutation_test(rs: RunSequences, deltas: pd.DataFrame, asks: pd.DataFrame,
                     n_perm: int = 1000, seed: int = 0) -> pd.DataFrame:
    """Observed statistic, null mean/sd, bias-corrected effect and one-sided p-value
    (fraction of null >= observed, with +1 smoothing) for each statistic.
    neg_dispersion is level-based and not affected by the permutation, so it gets
    no p-value here; it is calibrated only against the empirical base-run null."""
    obs = run_statistics(rs, deltas, asks)
    rng = np.random.default_rng(seed)
    null = {k: [] for k in STAT_NAMES if k != "neg_dispersion"}
    for _ in range(n_perm):
        prs, pdl = permute_within_state(rs, deltas, rng)
        st = run_statistics(prs, pdl, asks)
        for k in null:
            null[k].append(st[k])
    rows = []
    for k in STAT_NAMES:
        if k in null:
            arr = np.asarray(null[k], float)
            ok = ~np.isnan(arr)
            p = (np.sum(arr[ok] >= obs[k]) + 1) / (ok.sum() + 1) if ok.any() and not np.isnan(obs[k]) else np.nan
            rows.append({"stat": k, "observed": obs[k], "null_mean": np.nanmean(arr), "null_sd": np.nanstd(arr),
                         "effect": obs[k] - np.nanmean(arr), "p": p})
        else:
            rows.append({"stat": k, "observed": obs[k], "null_mean": np.nan, "null_sd": np.nan,
                         "effect": np.nan, "p": np.nan})
    return pd.DataFrame(rows).set_index("stat")


def deltas_and_asks(rounds: pd.DataFrame, run_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    asks = rounds[rounds.run_id == run_id].pivot(index="round", columns="seller", values="ask").sort_index()
    return asks.diff().iloc[1:], asks
