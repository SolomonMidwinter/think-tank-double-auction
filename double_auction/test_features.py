import numpy as np
import pytest

from features import discretize_run, STATE_CHOICES
from loader import load_all


@pytest.fixture(scope="module")
def data():
    return load_all()


def test_actions_known_values(data):
    _, rounds = data
    rs = discretize_run(rounds, "20250516_211616_base-1", dead_band=0.05, state="traded_last")
    a = rs.actions
    assert list(rs.rounds) == list(range(2, 31))
    assert a.loc[3, "Seller Kai"] == -1            # 96.99 -> 95.00
    assert a.loc[3, "Seller Lena"] == 0            # 96.99 -> 96.98
    assert np.isnan(a.loc[7, "Seller Wei"])        # ask missing in round 7
    assert np.isnan(a.loc[8, "Seller Wei"])        # previous ask missing
    assert a.loc[17, "Seller Kai"] == 1            # 85.7 -> 86.2 (raise)


def test_dead_band_changes_coding(data):
    _, rounds = data
    lo = discretize_run(rounds, "20250516_211616_base-1", dead_band=0.05).actions
    hi = discretize_run(rounds, "20250516_211616_base-1", dead_band=0.5).actions
    assert lo.loc[2, "Seller Kai"] == -1           # -0.06 counts as a cut at 0.05
    assert hi.loc[2, "Seller Kai"] == 0            # ... but not at 0.5
    assert (hi == 0).sum().sum() >= (lo == 0).sum().sum()


def test_state_traded_last(data):
    _, rounds = data
    rs = discretize_run(rounds, "20250516_211616_base-1", state="traded_last")
    # first trade in base-1 happened in round 13 -> state is 1 from round 14 on
    assert rs.states.loc[13] == 0
    assert rs.states.loc[14] == 1
    assert set(rs.states.unique()) <= {0, 1}


def test_all_states_build(data):
    _, rounds = data
    for st in STATE_CHOICES:
        rs = discretize_run(rounds, "20250516_212322_base-seller_comms-1", state=st)
        assert len(rs.states) == 29
        assert rs.states.index.equals(rs.actions.index)


def test_pair_and_common_drop_missing(data):
    _, rounds = data
    rs = discretize_run(rounds, "20250516_213304_base-2")   # Jun missing rounds 6-15
    ai, aj, s = rs.pair("Seller Jun", rs.sellers[0])
    assert len(ai) == len(aj) == len(s) == 29 - 11
    others = [x for x in rs.sellers if x != "Seller Jun"]
    bi, bj, _ = rs.pair(others[0], others[1])
    assert len(bi) == 29
    acts, st = rs.common()
    assert all(len(v) == 29 - 11 for v in acts.values()) and len(st) == 29 - 11


def test_lag_alignment(data):
    _, rounds = data
    rs = discretize_run(rounds, "20250516_212322_base-seller_comms-1")
    a0, b0, _ = rs.pair(rs.sellers[0], rs.sellers[1], lag=0)
    a1, b1, _ = rs.pair(rs.sellers[0], rs.sellers[1], lag=1)
    assert len(a1) == len(a0) - 1
    assert a1 == a0[:-1] and b1 == b0[1:]
