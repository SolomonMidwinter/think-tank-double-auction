"""Discretise ask trajectories into actions and states for the influence statistics.

Actions are defined on transitions: the action at round t is the direction of the
ask change from round t-1 to round t, so actions exist for rounds 2..N.

    action_t = +1 (raise) if ask_t - ask_{t-1} >= dead_band
             = -1 (cut)   if ask_t - ask_{t-1} <= -dead_band
             =  0 (hold)  otherwise
             = NaN        if either ask is missing

States are what every seller observed *before* acting in round t, i.e. functions of
round t-1's public outcome. Candidates (all small alphabets, on purpose):

    none        -- a single state (memoryless)
    traded_last -- did any trade happen in round t-1?            {0, 1}
    gap_last    -- lowest ask minus best bid in round t-1, binned  {wide, mid, tight}
    phase       -- round index in thirds                           {early, mid, late}

Missing asks stay NaN. Pair-level sequences drop any round where either member is
missing; all-seller sequences drop any round where anyone is missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

STATE_CHOICES = ("none", "traded_last", "gap_last", "phase")
ACTION_LABELS = {-1: "cut", 0: "hold", 1: "raise"}


@dataclass
class RunSequences:
    run_id: str
    sellers: list[str]
    rounds: np.ndarray                 # round indices for which actions exist (2..N)
    actions: pd.DataFrame              # rounds x sellers, values in {-1,0,1} or NaN
    states: pd.Series                  # indexed by round, discrete labels
    state_name: str
    dead_band: float
    meta: dict = field(default_factory=dict)

    def pair(self, i: str, j: str, lag: int = 0) -> tuple[list, list, list]:
        """Action sequences for sellers i and j plus the state sequence, restricted
        to rounds where both are observed. With lag=k, pairs i's action at t-k with
        j's action at t (and the state at t)."""
        ai = self.actions[i]
        aj = self.actions[j]
        if lag:
            ai = ai.shift(lag)
        ok = ai.notna() & aj.notna()
        return (ai[ok].astype(int).tolist(), aj[ok].astype(int).tolist(),
                self.states[ok].tolist())

    def common(self) -> tuple[dict[str, list], list]:
        """All sellers' action sequences on rounds where everyone is observed."""
        ok = self.actions.notna().all(axis=1)
        acts = {s: self.actions.loc[ok, s].astype(int).tolist() for s in self.sellers}
        return acts, self.states[ok].tolist()

    def n_dropped_common(self) -> int:
        return int((~self.actions.notna().all(axis=1)).sum())


def _states_for_run(sub: pd.DataFrame, rounds_idx: np.ndarray, state: str) -> pd.Series:
    per_round = sub.groupby("round").agg(n_trades=("n_trades", "first"),
                                         best_bid=("best_bid", "first"),
                                         min_ask=("min_ask", "first"))
    n = per_round.index.max()
    if state == "none":
        vals = np.zeros(len(rounds_idx), dtype=int)
    elif state == "traded_last":
        prev = per_round["n_trades"].reindex(rounds_idx - 1)
        vals = (prev.to_numpy() > 0).astype(int)
    elif state == "gap_last":
        prev = per_round.reindex(rounds_idx - 1)
        gap = (prev["min_ask"] - prev["best_bid"]).to_numpy()
        # wide: >5, mid: 1..5, tight: <1 (dollars). NaN gap (all asks missing) -> mid.
        vals = np.where(gap > 5, 0, np.where(gap >= 1, 1, 2))
        vals = np.where(np.isnan(gap), 1, vals)
    elif state == "phase":
        vals = np.minimum((rounds_idx - 1) * 3 // n, 2)
    else:
        raise ValueError(f"unknown state {state!r}; choose from {STATE_CHOICES}")
    return pd.Series(vals, index=rounds_idx, name=state)


def discretize_run(rounds: pd.DataFrame, run_id: str, dead_band: float = 0.05,
                   state: str = "traded_last") -> RunSequences:
    sub = rounds[rounds["run_id"] == run_id]
    asks = sub.pivot(index="round", columns="seller", values="ask").sort_index()
    delta = asks.diff().iloc[1:]                      # rounds 2..N
    acts = pd.DataFrame(np.sign(delta.where(delta.abs() >= dead_band, 0.0)),
                        index=delta.index, columns=delta.columns)
    acts = acts.where(delta.notna())                  # keep NaN where either ask missing
    rounds_idx = delta.index.to_numpy()
    states = _states_for_run(sub, rounds_idx, state)
    return RunSequences(run_id=run_id, sellers=list(asks.columns), rounds=rounds_idx,
                        actions=acts, states=states, state_name=state, dead_band=dead_band)


def discretize_all(rounds: pd.DataFrame, run_ids, **kw) -> dict[str, RunSequences]:
    return {rid: discretize_run(rounds, rid, **kw) for rid in run_ids}


# ---------------------------------------------------------------- diagnostics

def action_table(seqs: dict[str, RunSequences], runs: pd.DataFrame) -> pd.DataFrame:
    """Action frequencies per condition (pooled over sellers and rounds)."""
    rows = []
    for rid, rs in seqs.items():
        a = rs.actions.stack(future_stack=True).dropna().astype(int)
        rows.append({"condition": runs.loc[rid, "condition"], **a.map(ACTION_LABELS).value_counts().to_dict(),
                     "missing": int(rs.actions.isna().sum().sum())})
    df = pd.DataFrame(rows).fillna(0)
    out = df.groupby("condition").sum()
    tot = out[["cut", "hold", "raise"]].sum(axis=1)
    for c in ("cut", "hold", "raise"):
        out[c + "_pct"] = (100 * out[c] / tot).round(1)
    return out


def state_table(seqs: dict[str, RunSequences], runs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for rid, rs in seqs.items():
        vc = rs.states.value_counts()
        rows.append({"condition": runs.loc[rid, "condition"], **{f"s{k}": v for k, v in vc.items()}})
    return pd.DataFrame(rows).fillna(0).groupby("condition").sum().astype(int)


def simultaneity_table(seqs: dict[str, RunSequences], runs: pd.DataFrame) -> pd.DataFrame:
    """Per condition: of rounds where at least one seller moved, how many sellers moved
    (mean), and fraction of moving rounds where >=3 of the observed sellers moved.
    This is a model-free peek at the 'synchronised rare moves' signature."""
    rows = []
    for rid, rs in seqs.items():
        moved = (rs.actions != 0) & rs.actions.notna()
        n_obs = rs.actions.notna().sum(axis=1)
        n_moved = moved.sum(axis=1)
        active = n_moved > 0
        rows.append({
            "condition": runs.loc[rid, "condition"],
            "rounds": len(rs.rounds),
            "active_rounds": int(active.sum()),
            "mean_movers_when_active": float(n_moved[active].mean()) if active.any() else np.nan,
            "frac_active_ge3": float((n_moved[active] >= 3).mean()) if active.any() else np.nan,
            "frac_active_all": float((n_moved[active] == n_obs[active]).mean()) if active.any() else np.nan,
        })
    df = pd.DataFrame(rows)
    return df.groupby("condition").agg(runs=("rounds", "size"), active_rounds=("active_rounds", "mean"),
                                       mean_movers=("mean_movers_when_active", "mean"),
                                       frac_ge3=("frac_active_ge3", "mean"),
                                       frac_all=("frac_active_all", "mean")).round(2)


if __name__ == "__main__":
    import sys
    from loader import load_all
    runs, rounds = load_all()
    db = float(sys.argv[1]) if len(sys.argv) > 1 else 0.05
    print(f"=== dead band {db} ===")
    seqs = discretize_all(rounds, runs.index, dead_band=db, state="traded_last")
    print("\n-- action frequencies by condition --")
    print(action_table(seqs, runs).to_string())
    print("\n-- simultaneity of moves by condition --")
    print(simultaneity_table(seqs, runs).to_string())
    for st in STATE_CHOICES[1:]:
        s2 = discretize_all(rounds, runs.index, dead_band=db, state=st)
        print(f"\n-- state '{st}' counts by condition --")
        print(state_table(s2, runs).to_string())
    print("\n-- rounds dropped from all-seller sequences (runs with any) --")
    d = {rid: rs.n_dropped_common() for rid, rs in seqs.items() if rs.n_dropped_common()}
    print(d)
