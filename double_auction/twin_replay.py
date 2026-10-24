"""Model-matched null for the SHIPPED Agrawal runs: replay each seller as an "honest twin".

For every round, the twin receives the original seller's logged prompt with the
communication channel removed and with its OWN memory and scratchpad substituted:

  * the "# Messages Received from Other Sellers" block and the message fields in the
    output format are deleted;
  * the "# Your Memory" and "# Current Strategy Scratchpad" blocks are replaced by what
    the twin itself wrote in earlier rounds (the original's memory may paraphrase
    messages, so reusing it would leak the channel; see ANALYSIS_LOG limitations).

Everything else (market status, queues, past trades, the seller's own successful
trades, round counter, oversight/gag notices) is byte-identical to the original.

Usage:
  twin_replay.py RUN_DIR --model mock|openai/gpt-4.1|... [--sellers "Seller Kai" ...]
                 [--rounds N] [--out DIR] [--yes]
Paid models require --yes after the printed cost estimate. Reads OPENROUTER_API_KEY
from the environment (source Think-Tank/.env first).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ENV_ROOT = Path(__file__).resolve().parents[2] / "llm-agent-collusion"
sys.path.insert(0, str(ENV_ROOT))
os.chdir(ENV_ROOT)  # the env's clients/templating assume this cwd
from src.continuous_double_auction.util.json_util import extract_json  # noqa: E402
from src.continuous_double_auction.util.misc import get_client  # noqa: E402

PROMPT_RE = re.compile(r"## Prompt: Round (\d+) - .*?\n``````\n(.*?)\n``````", re.S)
MEM_RE = re.compile(r"# Your Memory\n.*?(?=\n\n# Market Status)", re.S)
# Shipped logs (older template) have no "Note: ..." line before the messages block; the current template does.
MSG_RE = re.compile(r"(Note: Your message has a maximum length limit[^\n]*\n)?# Messages Received from Other Sellers.*?(?=# Current Strategy Scratchpad|# Output Format)", re.S)
PAD_RE = re.compile(r"# Current Strategy Scratchpad\n.*?(?=\n\n# Output Format)", re.S)
FMT_MSG_RE = re.compile(r',\n\s*"plan_for_message": .*?"message_to_sellers": "<.*?>"', re.S)

# USD per 1M tokens (OpenRouter, 2026-10-24) for the cost estimate only
PRICES = {"openai/gpt-4.1": (2.0, 8.0), "openai/gpt-4.1-mini": (0.4, 1.6),
          "openai/gpt-4.1-nano": (0.1, 0.4), "openai/gpt-4o-mini": (0.15, 0.6)}


def load_prompts(md_path: Path) -> dict[int, str]:
    return {int(r): p for r, p in PROMPT_RE.findall(md_path.read_text(encoding="utf-8"))}


def make_twin_prompt(original: str, memory: str, scratch_pad: str) -> str:
    p = original
    n_mem = len(MEM_RE.findall(p))
    p = MEM_RE.sub(lambda m: f"# Your Memory\n{memory}", p)
    p = MSG_RE.sub("", p)
    if scratch_pad:
        if PAD_RE.search(p):
            p = PAD_RE.sub(lambda m: f"# Current Strategy Scratchpad\n{scratch_pad}", p)
        else:
            p = p.replace("# Output Format", f"# Current Strategy Scratchpad\n{scratch_pad}\n\n# Output Format", 1)
    else:
        p = PAD_RE.sub("", p)
    p = FMT_MSG_RE.sub("", p)
    # hard guarantees
    assert n_mem == 1, "memory block not found exactly once"
    assert "Messages Received from Other Sellers" not in p
    assert "message_to_sellers" not in p and "plan_for_message" not in p
    assert "This is Hour #" in p
    return p


def format_memory(mem: dict[int, str]) -> str:
    if not mem:
        return "No memories yet."
    return "\n".join(f"Hour {h}: {mem[h]}" for h in sorted(mem))


def replay_seller(run_dir: Path, seller: str, model: str, out_dir: Path, max_rounds: int | None, temperature: float):
    prompts = load_prompts(run_dir / f"{seller}.md")
    client = get_client(model=model, temperature=temperature)
    memory: dict[int, str] = {}
    scratch = ""
    asks: dict[int, float | None] = {}
    log = out_dir / f"{seller} (twin).md"
    for r in sorted(prompts):
        if max_rounds and r > max_rounds:
            break
        prompt = make_twin_prompt(prompts[r], format_memory(memory), scratch)
        resp = client.generate([{"role": "user", "content": prompt}])
        if resp is None:
            asks[r] = None
            with log.open("a", encoding="utf-8") as f:
                f.write(f"\n## Prompt: Round {r} - {datetime.now()}\n``````\n{prompt}\n``````\n\n## Response: Round {r} - FAILED\n")
            continue
        d = extract_json(resp)
        ask = d.get("ask")
        asks[r] = None if ask in (None, "null") else float(ask)
        if d.get("new_memory"):
            memory[r] = d["new_memory"]
        if d.get("scratch_pad_update"):
            scratch = d["scratch_pad_update"]
        with log.open("a", encoding="utf-8") as f:
            f.write(f"\n## Prompt: Round {r} - {datetime.now()}\n``````\n{prompt}\n``````\n")
            f.write(f"\n## Response: Round {r} - {datetime.now()}\n````json\n{json.dumps(d, indent=2)}\n````\n")
    return asks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--model", default="mock")
    ap.add_argument("--sellers", nargs="*", default=None)
    ap.add_argument("--rounds", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--yes", action="store_true", help="confirm spend for a paid model")
    a = ap.parse_args()
    run_dir = Path(a.run_dir).resolve()
    meta = json.loads((run_dir / "experiment_metadata.json").read_text())
    sellers = a.sellers or meta["seller_ids"]
    n_rounds = min(meta["auction_config"]["rounds"], a.rounds or 10**9)
    n_calls = len(sellers) * n_rounds
    tag = a.model.replace("/", "_").replace(":", "_")
    out_dir = Path(a.out) if a.out else Path(__file__).resolve().parents[1] / "results" / "twins" / f"{run_dir.name}__{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    if a.model in PRICES:
        pi, po = PRICES[a.model]
        est = n_calls * (2400 * pi + 600 * po) / 1e6
        print(f"{n_calls} calls to {a.model}: estimated ${est:.2f}")
        if not a.yes:
            print("paid model: re-run with --yes to proceed"); return
    elif not a.model.startswith("mock"):
        print(f"{n_calls} calls to {a.model} (no price on file)")
        if not a.yes:
            print("re-run with --yes to proceed"); return
    results = {"run_dir": str(run_dir), "model": a.model, "temperature": a.temperature,
               "rounds": n_rounds, "started": datetime.now().isoformat(), "twin_asks": {}}
    for s in sellers:
        print(f"replaying {s} ...", flush=True)
        results["twin_asks"][s] = replay_seller(run_dir, s, a.model, out_dir, a.rounds, a.temperature)
        (out_dir / "twin_asks.json").write_text(json.dumps(results, indent=2))
    results["finished"] = datetime.now().isoformat()
    (out_dir / "twin_asks.json").write_text(json.dumps(results, indent=2))
    print(f"done -> {out_dir}")


if __name__ == "__main__":
    main()
