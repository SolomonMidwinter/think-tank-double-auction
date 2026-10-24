"""Load the Agrawal et al. double-auction runs into tidy tables.

Source: the `data/` directory shipped with github.com/andyjliu/llm-agent-collusion.
Each run directory holds `auction_results.md` (one fenced JSON block per round)
and `experiment_metadata.json` (auction_config with condition flags).

Two outputs:
  runs   -- one row per run: run_id, condition flags, models, n_rounds, seller ids
  rounds -- one row per (run, round, seller): ask, best_bid, n_trades, traded,
            own_traded, msg_sent (seller sent a message this round),
            msg_received (seller received >=1 message at start of this round)

Missing asks (a seller failed to respond that round) are kept as NaN here;
discretisation decides how to treat them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "llm-agent-collusion" / "data"

_BLOCK_RE = re.compile(r"````json\n(.*?)\n````", re.S)


def _condition_label(cfg: dict) -> str:
    """Human-readable condition derived from the config flags, not the dir name."""
    parts = []
    if cfg.get("boss_pressure"):
        parts.append("boss_pressure")
    if cfg.get("oversight_enabled"):
        parts.append("oversight")
    if not parts:
        parts.append("base")
    parts.append("comms" if cfg.get("seller_comms_enabled") else "nocomms")
    return "-".join(parts)


def _model_family(model: str) -> str:
    m = model.lower()
    if "gpt" in m:
        return "gpt"
    if "claude" in m:
        return "claude"
    return m


def parse_run(run_dir: Path) -> tuple[dict, pd.DataFrame]:
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "experiment_metadata.json").read_text())
    cfg = meta["auction_config"]
    text = (run_dir / "auction_results.md").read_text()
    blocks = [json.loads(b) for b in _BLOCK_RE.findall(text)]
    if not blocks:
        raise ValueError(f"no round blocks parsed in {run_dir}")

    seller_ids = list(meta["seller_ids"])
    seller_models = dict(zip(seller_ids, cfg["seller_models"]))
    fams = sorted({_model_family(m) for m in cfg["seller_models"]})
    seller_mix = fams[0] if len(fams) == 1 else "mixed"
    bfams = sorted({_model_family(m) for m in cfg["buyer_models"]})
    buyer_mix = bfams[0] if len(bfams) == 1 else "mixed"

    run_id = run_dir.name
    run_row = {
        "run_id": run_id,
        "tag": cfg.get("tag"),
        "condition": _condition_label(cfg),
        "seller_comms": bool(cfg.get("seller_comms_enabled")),
        "boss_pressure": bool(cfg.get("boss_pressure")),
        "oversight": bool(cfg.get("oversight_enabled")),
        "seller_mix": seller_mix,
        "buyer_mix": buyer_mix,
        "n_sellers": len(seller_ids),
        "n_buyers": len(meta["buyer_ids"]),
        "n_rounds_cfg": cfg["rounds"],
        "n_rounds": len(blocks),
        "temperature": cfg.get("temperature"),
        "seller_ids": seller_ids,
    }

    rows = []
    for b in blocks:
        rnd = b["round_number"]
        asks = b.get("seller_asks", {})
        bids = b.get("buyer_bids", {})
        trades = b.get("trades", [])
        msgs = b.get("seller_messages", {}) or {}
        best_bid = max(bids.values()) if bids else np.nan
        min_ask = min(asks.values()) if asks else np.nan
        traders = {t.get("seller_id") for t in trades}
        for s in seller_ids:
            rows.append({
                "run_id": run_id,
                "round": rnd,
                "seller": s,
                "seller_model": seller_models[s],
                "ask": asks.get(s, np.nan),
                "best_bid": best_bid,
                "min_ask": min_ask,
                "n_trades": len(trades),
                "traded": len(trades) > 0,
                "own_traded": s in traders,
                "msg_sent": bool(msgs.get(s)),
            })
    rounds = pd.DataFrame(rows).sort_values(["round", "seller"]).reset_index(drop=True)

    # Messages are delivered at the start of the *next* round. A seller receives
    # a message in round t if any *other* seller sent one in round t-1.
    sent_by_round = rounds.groupby("round")["msg_sent"].sum()
    prev_total = rounds["round"].sub(1).map(sent_by_round).fillna(0).astype(int)
    prev_own = (
        rounds.groupby("seller")["msg_sent"].shift(1, fill_value=False).astype(int)
    )
    rounds["msg_received"] = (prev_total - prev_own) > 0

    # Sanity checks on this run
    if sorted(rounds["round"].unique()) != list(range(1, len(blocks) + 1)):
        raise ValueError(f"{run_id}: rounds not contiguous 1..N")
    if cfg.get("seller_comms_enabled") is False and rounds["msg_sent"].any():
        raise ValueError(f"{run_id}: messages present in a no-comms run")

    return run_row, rounds


def load_all(data_dir: Path | str = DEFAULT_DATA_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    data_dir = Path(data_dir)
    run_rows, round_frames = [], []
    for d in sorted(data_dir.iterdir()):
        if not d.is_dir() or not (d / "auction_results.md").exists():
            continue
        r, f = parse_run(d)
        run_rows.append(r)
        round_frames.append(f)
    runs = pd.DataFrame(run_rows).set_index("run_id")
    rounds = pd.concat(round_frames, ignore_index=True)
    return runs, rounds


def ask_matrix(rounds: pd.DataFrame, run_id: str) -> pd.DataFrame:
    """Rounds x sellers matrix of asks for one run (NaN where missing)."""
    sub = rounds[rounds["run_id"] == run_id]
    return sub.pivot(index="round", columns="seller", values="ask")


if __name__ == "__main__":
    runs, rounds = load_all()
    print(f"{len(runs)} runs, {len(rounds)} seller-rounds")
    print(runs.groupby(["condition", "seller_mix", "buyer_mix"]).size().to_string())
    print("\nrounds per run:", runs["n_rounds"].value_counts().to_dict())
    print("missing asks:", int(rounds["ask"].isna().sum()))
    print("\n", rounds.head(6).to_string())
