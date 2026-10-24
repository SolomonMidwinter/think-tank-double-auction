# Think-Tank double-auction detector

Working snapshot of the double-auction collusion-detection analysis for the
"Markets and Collusion" hackathon track (Oct 2026). Private; for fact-checking and review.

## What is here

| Path | Contents |
|---|---|
| `double_auction/` | Analysis code: `loader.py`, `features.py`, `stats.py`, `controls.py`, `evaluate.py`, `grid.py`, and three test files (18 tests). |
| `bonjour.py` | Team implementation of the Bonjour et al. influence statistics (from ElFuegoX/Think-Tank, by Melkior). Copied unchanged so the code runs standalone. |
| `results/double_auction/ANALYSIS_LOG.md` | **Start here.** Chronological record of pre-registration, controls, decisions, results, one retraction, and reproduction commands. |
| `results/double_auction/*.csv, *_log.txt` | Every table quoted in the write-up, as produced. |
| `drafts/double_auction_results_section.md` | Draft RESULTS.md section (not yet in the team repo). Numbers trace to the files above. |
| `env_patches/` | Uncommitted local changes to the Agrawal environment (`llm-agent-collusion.patch`, `mock_wrapper.py`): OpenRouter routing, mock client, ZIP buyers, partial-result saving, opt-in LLM judge. |

## What is not here

- The data: 75 runs shipped in `data/` of https://github.com/andyjliu/llm-agent-collusion (292 MB). The loader expects it at `../llm-agent-collusion/data/` relative to this repo, or pass a path to `load_all()`.
- API keys. Nothing in this analysis made an API call; $0 spent.

## Headline

On the shipped Agrawal et al. runs, no action-only dependence statistic (same-round or
lag-1 conditional MI, net influence, correlation of ask changes) detects the seller
communication channel. The pre-registered primary statistic points the wrong way
(AUC 0.35): comms runs show *less* same-round dependence in asks than honest runs.
The within-state permutation null flags 9/10 honest runs, i.e. it is misspecified for
same-model agents; net influence is the only calibrated statistic (1/10) and carries a
weak positive signal (AUC ~0.6-0.7). Details and caveats in the analysis log and draft.

## Reproduce

```
python -m venv .venv && .venv/bin/pip install numpy pandas pytest
# place the Agrawal data at ../llm-agent-collusion/data
.venv/bin/python -m pytest -q double_auction/
.venv/bin/python double_auction/evaluate.py 200     # ~5 min on 2 cores
```
