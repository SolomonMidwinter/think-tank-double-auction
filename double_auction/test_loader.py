"""Sanity tests for the double-auction loader (run: pytest double_auction/)."""
import numpy as np
import pytest

from loader import DEFAULT_DATA_DIR, ask_matrix, load_all, parse_run


@pytest.fixture(scope="module")
def data():
    return load_all()


def test_shapes(data):
    runs, rounds = data
    assert len(runs) == 75
    assert (runs["n_rounds"] == 30).all()
    assert (runs["n_sellers"] == 5).all()
    assert len(rounds) == 75 * 30 * 5


def test_conditions(data):
    runs, _ = data
    counts = runs["condition"].value_counts().to_dict()
    assert counts["base-nocomms"] == 10
    assert counts["base-comms"] == 35
    assert counts["oversight-comms"] == 10
    assert counts["boss_pressure-comms"] == 10
    assert counts["boss_pressure-oversight-comms"] == 10


def test_known_values(data):
    """Values read by hand from data/20250516_211616_base-1/auction_results.md."""
    _, rounds = data
    m = ask_matrix(rounds, "20250516_211616_base-1")
    assert m.loc[1, "Seller Nia"] == pytest.approx(97.00)
    assert m.loc[3, "Seller Kai"] == pytest.approx(95.00)
    assert np.isnan(m.loc[7, "Seller Wei"])
    assert m.loc[8, "Seller Lena"] == pytest.approx(89.99)


def test_message_timing(data):
    runs, rounds = data
    nocomms = rounds[rounds.run_id.isin(runs.index[~runs.seller_comms])]
    assert not nocomms["msg_sent"].any()
    assert not nocomms["msg_received"].any()
    # Nobody can receive a message in round 1.
    assert not rounds[rounds["round"] == 1]["msg_received"].any()
    # In a comms run where everyone messaged in round 1, everyone receives in round 2.
    r2 = rounds[(rounds.run_id == "20250516_212322_base-seller_comms-1") & (rounds["round"] == 2)]
    assert r2["msg_received"].all()


def test_parse_single_run_rejects_bad_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_run(tmp_path)


def test_pilot_fields_default_for_shipped_data(data):
    runs, rounds = data
    assert (runs["colluding_seller_ids"].map(len) == 0).all()
    assert rounds["shadow_ask"].isna().all()
    assert not rounds["is_colluder"].any()


def test_loader_reads_mock_c3_run():
    import glob
    from pathlib import Path
    cands = sorted(glob.glob(str(Path(DEFAULT_DATA_DIR).parent / "results" / "*mock-c3-twins")))
    if not cands:
        pytest.skip("no mock c3 run present")
    r, f = parse_run(Path(cands[-1]))
    assert r["condition"] == "base-comms-c3" and len(r["colluding_seller_ids"]) == 2
    assert f.loc[f.is_colluder, "shadow_ask"].notna().mean() > 0.9
    assert f.loc[~f.is_colluder, "shadow_ask"].isna().all()
