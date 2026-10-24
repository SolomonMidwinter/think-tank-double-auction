"""Budget-guarded runner for the cheap pilot (and, with other models, the proper one).

Sessions: n_honest x (no comms) and n_c3 x (comms on, sellers 0 and 1 told to collude,
private channel, shadow twins of the colluders). Before every session the OpenRouter
key's usage is read from the free endpoint GET /api/v1/auth/key; the runner stops if
usage would exceed --cap_usd. Each session's usage delta is logged.

Usage (from Think-Tank/, after `set -a; . .env; set +a`):
  pilot_runner.py --model openai/gpt-4.1-nano --n_honest 5 --n_c3 5 --rounds 20 --cap_usd 0.90
  pilot_runner.py --smoke --model openai/gpt-4.1-nano          # 1 C3 session, 3 rounds
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ENV_ROOT = Path(__file__).resolve().parents[2] / "llm-agent-collusion"
PY = ENV_ROOT / ".venv" / "bin" / "python"
LOG = Path(__file__).resolve().parents[1] / "results" / "double_auction" / "pilot_log.txt"


def key_usage() -> dict:
    req = urllib.request.Request("https://openrouter.ai/api/v1/auth/key",
                                 headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["data"]


def log(msg: str):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def run_session(model: str, rounds: int, tag: str, c3: bool, n_sellers: int = 5, n_buyers: int = 5,
                buyers: str = "zip", twins: str = "colluders") -> int:
    cmd = [str(PY), "src/continuous_double_auction/simulation.py",
           "--seller_valuations", *(["80"] * n_sellers), "--buyer_valuations", *(["100"] * n_buyers),
           "--seller_models", *([model] * n_sellers), "--buyer_models", *([buyers] * n_buyers),
           "--rounds", str(rounds), "--tag", tag]
    if c3:
        cmd += ["--seller_comms_enabled", "--colluding_sellers", "0", "1", "--private_channel", "--shadow_twins", twins]
    log(f"START {tag}: {' '.join(cmd[2:])}")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=ENV_ROOT, capture_output=True, text=True)
    tail = "\n".join((res.stdout + res.stderr).strip().splitlines()[-3:])
    log(f"END {tag} rc={res.returncode} in {time.time()-t0:.0f}s | {tail[:300]}")
    return res.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--n_honest", type=int, default=5)
    ap.add_argument("--n_c3", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--cap_usd", type=float, default=0.90, help="stop when key usage reaches this")
    ap.add_argument("--buyers", default="zip")
    ap.add_argument("--twins", default="colluders", choices=["none", "colluders", "all"])
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--prefix", default="pilot")
    a = ap.parse_args()
    if "OPENROUTER_API_KEY" not in os.environ:
        sys.exit("OPENROUTER_API_KEY not set (source Think-Tank/.env)")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    u0 = key_usage()
    log(f"key usage at start: ${u0['usage']:.4f} of ${u0['limit']} (remaining ${u0.get('limit_remaining')})")
    if a.smoke:
        sessions = [(f"{a.prefix}-smoke-c3", True, 3)]
    else:
        sessions = [(f"{a.prefix}-honest-{k+1}", False, a.rounds) for k in range(a.n_honest)]
        sessions += [(f"{a.prefix}-c3-{k+1}", True, a.rounds) for k in range(a.n_c3)]
        # interleave so a budget stop leaves balanced conditions
        sessions = [s for pair in zip(sessions[:a.n_honest], sessions[a.n_honest:]) for s in pair] + sessions[2*min(a.n_honest, a.n_c3):]
    prev = u0["usage"]
    for tag, c3, rounds in sessions:
        u = key_usage()
        if u["usage"] >= a.cap_usd:
            log(f"STOP: usage ${u['usage']:.4f} >= cap ${a.cap_usd}"); break
        rc = run_session(a.model, rounds, tag, c3, buyers=a.buyers, twins=a.twins)
        time.sleep(3)  # let usage accounting catch up
        u = key_usage()
        log(f"usage after {tag}: ${u['usage']:.4f} (session cost ${u['usage']-prev:.4f})")
        prev = u["usage"]
        if rc != 0:
            log(f"STOP: {tag} failed (rc={rc})"); break
    u1 = key_usage()
    log(f"DONE. total spent this invocation: ${u1['usage']-u0['usage']:.4f}; key usage ${u1['usage']:.4f} of ${u1['limit']}")


if __name__ == "__main__":
    main()
