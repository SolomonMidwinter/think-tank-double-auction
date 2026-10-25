# Think-Tank double-auction detector

Working snapshot of the double-auction collusion-detection analysis for the
"Markets and Collusion" hackathon track (Oct 2026). Private; for fact-checking and review.

## What is here

| Path | Contents |
|---|---|
| `double_auction/` | Analysis code: `loader.py`, `features.py`, `stats.py`, `controls.py`, `evaluate.py`, `grid.py`, `twin_replay.py`, `pilot_runner.py`, and three test files (20 tests). |
| `bonjour.py` | Team implementation of the Bonjour et al. influence statistics (from ElFuegoX/Think-Tank, by Melkior). Copied unchanged so the code runs standalone. |
| `results/double_auction/ANALYSIS_LOG.md` | **Start here.** Chronological record of pre-registration, controls, decisions, results, one retraction, and reproduction commands. |
| `results/double_auction/*.csv, *_log.txt` | Every table quoted in the write-up, as produced. |
| `drafts/double_auction_results_section.md` | Draft RESULTS.md section (not yet in the team repo). Numbers trace to the files above. |
| `env_patches/` | Uncommitted local changes to the Agrawal environment (`llm-agent-collusion.patch`, `mock_wrapper.py`): OpenRouter routing, mock client, ZIP buyers, partial-result saving, opt-in LLM judge. |

## What is not here

- The data: 75 runs shipped in `data/` of https://github.com/andyjliu/llm-agent-collusion (292 MB). The loader expects it at `../llm-agent-collusion/data/` relative to this repo, or pass a path to `load_all()`.
- API keys. Nothing in this analysis made an API call; $0 spent.


## Provenance: what is ours vs inherited (for fact-checking)

**Everything in this repo was written on 2026-10-24 (afternoon/evening, US Central) during
the hackathon session, except the two items marked inherited.** Chronology, decisions and
numbers are in `results/double_auction/ANALYSIS_LOG.md`.

| Path | Status |
|---|---|
| `bonjour.py` | **Inherited** (Melkior / ElFuegoX Think-Tank repo), copied unchanged |
| Agrawal et al. data | **Inherited, not included** (see above) |
| `double_auction/loader.py`, `features.py`, `stats.py`, `controls.py`, `evaluate.py`, `grid.py`, `test_*.py` | Ours, this session: detector pipeline on the shipped data |
| `double_auction/twin_replay.py`, `pilot_runner.py` | Ours, this session (evening): tools for the two pending experiments |
| `env_patches/llm-agent-collusion.patch`, `mock_wrapper.py` | Ours, this session: all local changes to the Agrawal environment (afternoon: OpenRouter routing, mock client, ZIP buyers, partial saves; evening: ZIP adaptation, collusion flag, private channel, shadow twins, JSON mode, raw-response logging) |
| `results/double_auction/ANALYSIS_LOG.md` | Ours: process log, sections 1-8 |
| `results/double_auction/*.csv`, `*_log.txt` | Ours: outputs of controls, evaluation (200 and 1000 perms), grid, exploratory check |
| `results/pilot_smokes/` | Ours: 2 mock runs + 3 paid smoke runs (nano, 4o-mini, 4.1-mini) + 1 failed 4.1-mini attempt, raw logs as produced by the environment |
| `results/twins/mocktest/` | Ours: mock run of twin_replay on one shipped comms run (surgery check) |
| `drafts/double_auction_results_section.md` | Ours: draft write-up, not yet in the team repo |

Spend on the team OpenRouter key: $0.0455 total, all from the three smoke runs under
`results/pilot_smokes/`. No other result here involved an API call.

All code and text marked "ours" was written with AI coding assistance during the sprint
and reviewed by the author. Numbers were independently recomputed from the CSVs on the
evening of 10/24 by a separate reviewer; the resulting corrections are recorded in the
analysis log (§9).

## Headline

On the shipped Agrawal et al. runs, no action-only dependence statistic (same-round or
lag-1 conditional MI, net influence, correlation of ask changes) separates comms-on from
comms-off at a 5% false-alarm rate. The pre-registered primary statistic points the wrong
way (observed AUC 0.25, bias-corrected 0.35): comms runs show *less* same-round dependence
in asks than honest runs. The within-state permutation null flags 9/10 honest runs: it
tests conditional independence given a coarse state, a weaker null than "no channel",
and same-model sellers in a shared market are not conditionally independent given a
binary trade flag. Net influence is the only calibrated statistic (1/10 honest flagged)
but shows no observed separation (observed AUC 0.53; the corrected 0.62 is driven by a
null-mean difference, see log §9). Details and caveats in the analysis log and draft.

## Reproduce

See also `results/double_auction/ANALYSIS_LOG.md` §7 for the full command list.

```
python -m venv .venv && .venv/bin/pip install numpy pandas pytest
# place the Agrawal data at ../llm-agent-collusion/data
.venv/bin/python -m pytest -q double_auction/
.venv/bin/python double_auction/evaluate.py 200     # ~5 min on 2 cores
```
