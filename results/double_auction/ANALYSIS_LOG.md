# Double-auction detector: analysis log

Chronological record of what was decided, run, and found. Written 2026-10-24 during the
analysis; entries are in the order they happened so that post-hoc choices are visible as
such. Numbers quoted here are copied from the files named in each entry.

Data: the 75 runs shipped in `llm-agent-collusion/data/` (Agrawal et al., "Evaluating LLM
Agent Collusion in Double Auctions"). 5 sellers x 5 buyers x 30 rounds each. Conditions
(from `experiment_metadata.json` flags, not directory names): base-nocomms 10 (gpt-4.1),
base-comms 35 (10 gpt/gpt + 25 model-mix variants), oversight-comms 10, boss_pressure-comms
10, boss_pressure-oversight-comms 10. No API calls were made for any result in this log.

Code: `double_auction/` (loader.py, features.py, stats.py, controls.py, evaluate.py,
grid.py, tests). Statistics reuse `bonjour.py` (team implementation) unchanged. Run with
`../llm-agent-collusion/.venv/bin/python`.

## 1. Question and how it differs from the paper

Paper: do LLM sellers collude and does it pay? Measured by an LLM judge reading private
chain-of-thought, plus price level / dispersion / profit, compared across known conditions.

Ours: can an outside observer with only the public ask sequence detect the communication
channel at a fixed false-alarm rate, using the state-conditioned mutual-information
statistics from Bonjour et al., versus correlation and level baselines?

Environment facts that shaped the design (from `market.py` and the seller prompt):
messages sent in round t are delivered at the start of t+1; all sellers see identical
public state before acting. So same-round dependence beyond public state can only come
from the channel or from being the same model. Lag-1 dependence is ordinary undercutting.

Note on the statistic: `calculate_net_influence` subtracts the strongest third-party
influence on the target, so it targets a colluding *subset*. Agrawal's channel is a
broadcast to all five sellers. Hence mean pairwise conditional MI (gamma) was chosen as
primary for this data and net influence kept as secondary.

## 2. Pre-registered configuration (fixed before any comms run was examined)

- Action: sign of ask change with 0.05 dead band -> {cut, hold, raise}; NaN if either ask
  missing. Dead band checked against the pooled |delta| histogram (no condition split):
  half of nonzero changes are <5c jitter; deliberate steps >= ~0.5%. 0.05 ~ 0.05% of price.
- State: whether any trade occurred in the previous round (binary; ~60/40 in base).
- Statistic: mean over 10 seller pairs of same-round conditional MI.
- Null: 1000 within-state permutations of each seller's actions among their observed
  rounds (gaps preserved). Alpha 0.05.
- Also reported: max net influence, lag-1 MI, Pearson correlation of raw ask changes,
  paper's ask dispersion. Sensitivity grid: dead band {0.05, 0.25} x {ternary, binary} x
  state {none, traded_last, gap_last, phase}.
- Missing asks (82 total, clustered: one comms run has all five sellers missing rounds
  9-14, two base runs have one seller missing ~10 rounds) stay NaN; a round is dropped
  from a pair's sequence if either member is missing. Never coded as an action.
- Hypothesis flagged in advance: comms runs may show *lower* same-round MI because
  holding dominates.

Marginal check (features.py, before statistics): base-comms and base-nocomms have near
identical action frequencies (~28% cut / 67% hold / 5% raise). Boss-pressure conditions
hold >90% of the time: no entropy, declared undetectable-by-construction before testing.

## 3. Controls (honest runs only; `controls.py`, `controls_log.txt`, `controls_*.csv`)

Toy tests (`test_stats.py`): perfect copy -> MI = action entropy; state conditioning zeroes
a common-cause pair; lagged copy fires lag-1 only; permutation preserves per-state counts.

Honest flag rate, 10 base-nocomms runs, 1000 perms, p<0.05:
mean_gamma 9/10, lag-1 9/10, corr 8/10, **max_net 1/10**.
=> The within-state permutation null does NOT control false alarms for group statistics
on same-model agents. Net influence is calibrated. No alternative state/coding fixes it
(`controls_state_sensitivity.csv`: none 10, gap_last 8, phase 6, binary 8, db .25 -> 9).

Injections (20% noise): same-round copy -> max_net flags 6/10, isolates injected pair
7/10 (fails where honest lockstep already high). Lagged copy -> lag-1 effect rises 9/10,
same-round effect does not rise (falls slightly 9/10).

Cross-run pairs (sellers from different honest runs, round-aligned; same model+prompt,
no shared realized market, no channel): mean gamma 0.143 vs 0.288 within honest runs
(traded_last). ~Half the honest within-run dependence is shared-model, half is shared
realized market that coarse state cannot absorb. The correct null is the model-matched
"honest twin" (same realized states, channel removed) -- not run here (costs API calls).

Decision taken (user, checkpoint 2): report net influence as the calibrated detector;
report group statistics as bias-corrected effects (observed minus permutation-null mean)
against the empirical 10-run base distribution and as AUCs. State plainly that the
permutation null is misspecified for same-model agents.

## 4. Primary evaluation, 200 perms (`evaluate.py`, `eval_primary_n200_log.txt`,
`eval_traded_last_db0.05_tern_n200.csv`)

Headline contrast = 10 gpt/gpt base-comms vs 10 base-nocomms. AUC of bias-corrected effect
(dispersion: observed):

| statistic | AUC |
|---|---|
| mean pairwise MI (primary) | 0.35 |
| lag-1 MI | 0.25 |
| max net influence | 0.62 |
| Pearson corr of changes | 0.66 |
| paper's ask dispersion | 0.68 |

Mean effect: mean_gamma 0.145 (comms) vs 0.177 (honest). The pre-registered hypothesis
materialised: comms runs show LESS same-round dependence in asks. Once agreed by message,
sellers hold; honest sellers coordinate tacitly through the price signal.
Permutation flagging: max_net 0/10 comms, 1/10 honest (calibrated, no power on broadcast
collusion). Oversight-comms: max_net 5/10 flagged (p<=.05, distinct pairs), AUC 0.73 --
a lead only, n=10. Pressure runs: uninformative as predicted.

## 5. Diagnostics and one retraction (post-hoc; `exploratory_identical_move.csv`)

- The correlation "advantage" is an artifact of bias correction: observed Pearson AUC
  is 0.51; comms runs move less, so their null mean is lower.
- A first "identical-magnitude move" score gave AUC 0.80 on the headline 20 runs. It was
  WRONG: it counted hold/hold matches, i.e. measured holding frequency. The proper
  pair-level version restricted to active rounds gives 0.56 (seen 10), 0.46 (25 held-out
  base-comms), 0.19 (oversight). Retracted.
- Magnitude-aware 4-symbol MI (hold / small cut / large cut / raise), observed: AUC 0.26.
- Held-out 25 by seller model (n=5 each): claude 0.82, gpt 0.68, mixed 0.58/0.04,
  claude-with-gpt-buyers 0.12. Noise at n=5; one sentence at most in any write-up.

## 6. Status (updated 2026-10-24 22:55 UTC)

- Sensitivity grid DONE (see 6a).
- Primary config at 1000 perms over all 75 runs DONE (`eval_primary_n1000_log.txt`,
  `eval_traded_last_db0.05_tern_n1000.csv`, 1453 s). Reproduces the 200-perm pass to two
  decimals: headline AUC mean_gamma 0.35, lag-1 0.24, max_net 0.62, corr 0.66,
  dispersion 0.68. Permutation flags: mean_gamma 9/10 honest, 9/10 comms; max_net 1/10
  honest, 0/10 comms, 5/35 all base-comms, 3/10 oversight (was 5/10 at 200 perms -- the
  oversight lead weakened). Empirical-null flags at honest-max threshold: mean_gamma 1/10,
  max_net 0/10, corr 5/10 (artifact, see 5), dispersion 0/10 on the headline 10.
- RESULTS.md section: drafted from these numbers. Nothing committed.
- Not done: model-matched null (honest twins), cheap-model pilot (C3 subset collusion is
  the regime net influence is built for). Both cost API budget ($1.00 cap).


## 6a. Sensitivity grid result (`grid_log.txt`, `grid_n200_summary.csv`; 15 configs x 30 runs, 200 perms)

Group statistic (mean pairwise MI): honest flag rate 5-10/10 in every config -- never
calibrated. AUC comms-vs-honest 0.32-0.43 in 12 of 15 configs (below chance, same
inversion as primary). Only the `phase` state lifts it: 0.55 (db .05), 0.59-0.68 (db .25),
with 1-2/10 empirical flags. Phase absorbs the shared early-cut/late-hold drift. Best cell
is 1 of 16 looked at, on 10v10: not evidence.

Net influence: honest flag rate 0-3/10 in all 15 configs (calibrated throughout). AUC
comms-vs-honest 0.54-0.79, median ~0.66; permutation detections on comms 0-6/10 (best:
state=none, db .25, 6/10 at 1-2/10 honest). Oversight AUC 0.55-0.81, detections 0-7/10,
unstable across configs (primary had 5/10). Reading: a weak, consistent, correctly
calibrated positive signal from the subset statistic; low power, config-dependent.

## 7. Reproduction

```
cd Think-Tank
PY=../llm-agent-collusion/.venv/bin/python
$PY -m pytest -q double_auction/            # 18 tests
$PY double_auction/features.py 0.05         # marginals / simultaneity tables
$PY double_auction/controls.py              # ~5 min on 2 cores
$PY double_auction/evaluate.py 200          # ~5 min; 1000 -> ~25 min
$PY double_auction/grid.py                  # ~30 min
```
