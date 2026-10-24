# Double auction (Agrawal et al. data): can asks alone reveal the communication channel?

Code: `double_auction/` (loader, features, stats, controls, evaluate, grid; 18 tests). Statistics call `bonjour.py` unchanged. Data: the 75 runs shipped in `llm-agent-collusion/data/` (5 sellers x 5 buyers x 30 rounds; conditions read from `experiment_metadata.json`). Outputs and a chronological process log: `results/double_auction/` (see `ANALYSIS_LOG.md` there). No API calls; $0 spent.

**Status:** complete on the shipped data. Primary configuration at 1000 permutations over all 75 runs; sensitivity grid (15 configurations, 200 permutations) over the 30 headline-and-oversight runs. The model-matched null ("honest twins") and the subset-collusion pilot are not run; both cost API budget.

## Question

Agrawal et al. show that a seller communication channel raises prices, using an LLM judge on private chain-of-thought plus price level and dispersion, with the condition labels known. We ask the detection question: given only the public per-round ask sequence, can a state-conditioned dependence statistic (Bonjour et al.) separate channel-on from channel-off runs at a fixed false-alarm rate, and does it beat correlation and the paper's level metrics?

Two environment facts fix the design. Messages sent in round t are delivered at the start of round t+1, and every seller sees the same public state before acting. So same-round dependence beyond public state has only two sources: the channel, or being copies of the same model. Lag-1 dependence is ordinary undercutting and exists in both conditions.

## Setup
- **Runs:** base-nocomms 10 (gpt-4.1, honest), base-comms 35 (10 gpt/gpt + 25 model-mix variants), oversight-comms 10, boss_pressure-comms 10, boss_pressure-oversight-comms 10. Headline contrast: the 10 gpt/gpt base-comms vs the 10 base-nocomms.
- **Actions:** sign of the ask change with a 0.05 dead band ({cut, hold, raise}). Half of all nonzero changes are penny jitter under 5 cents; deliberate steps are >= 0.5% of price. Missing asks (82, clustered around what look like API outages) stay missing; a round is dropped from a pair's sequence if either seller is missing.
- **State:** whether any trade happened in the previous round (binary). Grid also covers no state, ask-bid gap, round phase; dead band 0.25; binary move/hold coding.
- **Statistics:** mean pairwise same-round conditional MI γ (pre-registered primary); max net influence Γ (subset detector); lag-1 γ; Pearson correlation of raw ask changes; the paper's ask dispersion. Effects are bias-corrected (observed minus permutation-null mean) because γ on 29 rounds carries ~0.14 bits of small-sample bias.
- **Nulls:** (i) 1000 within-state permutations of each seller's actions among their observed rounds; (ii) the empirical distribution over the 10 honest runs; (iii) cross-run pairs: sellers from two different honest runs, round-aligned (same model, prompt, valuations; no shared realized market, no channel).
- **Controls, honest runs only:** injected same-round copy, injected lagged copy, cross-run pairs, and the honest-run flag rate.
- **Declared in advance:** boss-pressure runs hold >90% of the time and are undetectable by any action statistic; the comms runs might show *lower* same-round γ because holding dominates.

## Results

**1. The permutation null is misspecified for same-model agents; net influence is the only calibrated statistic.** Honest runs flagged at p < 0.05 (of 10), 1000 permutations:

| Statistic | Honest runs flagged |
|---|---|
| mean pairwise γ (primary) | 9/10 |
| lag-1 γ | 9/10 |
| Pearson correlation | 8/10 |
| **max net influence Γ** | **1/10** |

No alternative state or coding repairs the group statistics (6 to 10 of 10 honest runs flagged across all 15 grid cells). Γ stays at 0 to 3 of 10 in every cell. Subtracting the strongest third-party influence removes exactly the group-wide common cause that sinks the others.

**2. Where the honest dependence comes from.** Cross-run pairs (channel impossible, market not shared) have mean γ 0.143. Pairs within the same honest run have 0.288. About half of honest same-round dependence is shared-model behaviour and half is reaction to the shared realized market that a coarse state does not absorb. The correct null is the model-matched twin (same realized states, channel removed), which is the next experiment.

**3. Controls.** Lagged-copy injection raises the lag-1 effect in 9/10 runs and leaves the same-round effect flat (falls slightly in 9/10): the two statistics separate. Same-round-copy injection makes Γ fire in 6/10 runs and single out the injected pair in 7/10; it fails where honest lockstep is already high.

**4. Detection of the channel.** Headline contrast, AUC of bias-corrected effect (dispersion: observed) vs the 10 honest runs:

| Statistic | 10 comms vs 10 honest | all 35 base-comms | oversight-comms |
|---|---|---|---|
| mean pairwise γ (primary) | **0.35** | 0.41 | 0.36 |
| lag-1 γ | 0.24 | 0.41 | 0.34 |
| max net influence Γ | 0.62 | 0.61 | 0.74 |
| Pearson correlation | 0.66 | 0.65 | 0.50 |
| paper's ask dispersion | 0.68 | 0.67 | 0.21 |

Flagging at the fixed false-alarm rate: Γ by permutation (the only valid p-value) flags 0/10 headline comms runs, 5/35 base-comms overall, 3/10 oversight. Against the empirical honest maximum, γ flags 1/10 comms runs, Γ 0/10, dispersion 0/10.

**5. The pre-registered hypothesis materialised.** Comms runs show *less* same-round dependence in asks than honest runs (mean γ effect 0.145 vs 0.177). Action marginals are nearly identical across the two conditions (~28% cut / 67% hold / 5% raise), so this is joint structure, not activity level. Once sellers have agreed by message they hold; honest sellers coordinate tacitly through the price signal and so move together more. Sign-discretised asks read the honest market as the more coupled one.

**6. Things that did not rescue it (post hoc, reported for completeness).** The correlation AUC of 0.66 is an artifact of bias correction (observed Pearson AUC 0.51; comms runs move less, so their null mean is lower). A pair-level "identical dollar move" score gives 0.56 on the headline runs, 0.46 on the 25 held-out base-comms runs, 0.19 on oversight; an earlier version that scored 0.80 was counting hold/hold matches and has been withdrawn. A magnitude-aware 4-symbol γ gives 0.26. Round-phase state lifts γ to 0.55 to 0.68 in 3 of 16 cells examined while still flagging 7 to 10 of 10 honest runs; not evidence.

**7. Sensitivity (grid, `results/double_auction/grid_n200_summary.csv`).** Γ: honest flags 0 to 3/10 in all 15 cells, AUC 0.54 to 0.79 (median ~0.66), comms detections 0 to 6/10; the oversight lead moves between 0 and 7/10 across cells and 3/10 at 1000 permutations in the primary cell, so it is not stable. γ: AUC 0.32 to 0.43 in 12 of 15 cells.

## Findings
- On this data, **no action-only dependence statistic detects the broadcast communication channel**. The channel changes where prices settle (the paper's result; dispersion AUC 0.68 here) but does not leave a positive signature in the dependence structure of price moves. It leaves a negative one.
- **The within-state permutation null does not control false alarms for same-model LLM agents.** Nine of ten honest runs are "colluding" by that test. Any market result that reports permutation p-values for a group dependence statistic on same-model agents without an honest-twin or cross-run calibration should be read with that in mind, including our own.
- **Net influence is correctly calibrated throughout and carries a weak positive signal** (AUC ~0.6 to 0.7, 0 to 6/10 detections). It is built for a colluding subset; Agrawal's channel is a broadcast to all five sellers, which is the worst case for it. The pilot with two of five sellers instructed to collude is the regime it was designed for.
- **Honest same-model sellers already share ~0.29 bits of same-round information per pair**, half from the model and half from the shared realized market. This is the quantity the model-matched null must subtract, and it is large relative to any channel effect we can see.

## Limitations
- 10 vs 10 runs for the headline contrast; AUC standard error is about 0.13.
- 30 rounds per run with ~67% holds leaves little entropy per sequence; pooling across runs is what makes the comparisons possible at all.
- All honest runs are gpt-4.1 vs gpt-4.1; the model-mix comms runs have no matching honest baseline, so the held-out 25 are compared to a gpt-only null.
- The oversight and pressure manipulations change seller behaviour in ways (gagging, rigid holding) that confound comparison to the base null.

## Next steps
1. **Model-matched null** on a few shipped runs: replay each seller's exact prompts with the message block blanked, same model, build the pairwise-γ distribution for "solo twins", compare the observed pair. Cost: one gpt-4.1-class call per seller-round; scope to 1 to 2 runs under the $1 cap, or use a cheaper model and accept the mismatch.
2. **Subset-collusion pilot (C3):** two of five sellers instructed to collude, cheap model, ZIP buyers (after fixing ZIP adaptation). This is the test net influence is designed for and the one the shipped data cannot provide.

**Pilot status (added 2026-10-24 23:45 UTC).** Infrastructure for both next steps is built and mock-tested (seeded subset collusion with a private channel, shadow twins, twin replay for the shipped logs, budget-guarded runner; see `results/double_auction/ANALYSIS_LOG.md` §8). Three-round smoke tests on gpt-4.1-nano, gpt-4o-mini and gpt-4.1-mini (total $0.05) show honest cheap-model sellers pricing at cost within two rounds, unlike gpt-4.1 in the shipped data, so a cheap-model pilot would not test the detector in the relevant regime. Both experiments are coded and await a budget of roughly $10-50 to run on gpt-4.1.
