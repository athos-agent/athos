# Bench results, November 1, 2026

The raw runs behind the README's numbers, one JSON line per run:
[results-2026-11-01.jsonl](results-2026-11-01.jsonl). Each line holds the case, the agent and model, whether the
know-how was given, the verdict (`g` right, `f` failed) from the case's own check, the stages done, what was missed,
time, tokens and cost. Nothing in a verdict comes from the agent: each case's `check.py` reads what the run left behind
(files, git, tests).

## Meta's Muse Spark through the Meta Model API, 5 runs each arm

| Case | Domain | With the know-how | Without it | Cost a run (with) |
|---|---|---|---|---|
| expense-review | finance operations, 10 stages | 5/5 (10/10 stages) | 0/5 (6/10) | $0.037 |
| tile-plan | a planning method, 8 stages | 5/5 (8/8) | 0/5 (5/8) | $0.022 |
| monthly-report | data | 5/5 | 0/5 | $0.026 |
| release | code | 5/5 | 2/5 | $0.026 |
| device-setup | devices | 5/5 | 0/5 | $0.008 |
| **Total** | | **25/25** | **2/25** | |

## Meta's open weights: Muse Spark Open through OpenRouter, November 2, 5 runs each arm

`meta/muse-spark-open` (816B open-weights mixture of experts) through OpenRouter, which served it from inference
providers such as BaseTen and Fireworks, in Athos's own loop (`athos bench --agents openrouter`): the model reads the
case's files, follows the know-how step by step with tools, and writes what the check reads.

| Case | Domain | With the know-how | Without it | Cost a run (with) |
|---|---|---|---|---|
| release | code | 5/5 | 0/5 | $0.020 |
| monthly-report | data | 5/5 | 0/5 | $0.018 |
| device-setup | devices | 5/5 | 0/5 | $0.010 |
| tile-plan | a planning method | 5/5 (8/8 stages) | 0/5 (5/8) | $0.018 |
| expense-review | finance operations | 5/5 (10/10 stages) | 0/5 | $0.028 |
| contract-transfer | law | 5/5 | 0/5 | $0.016 |
| support-tickets | customer support | 5/5 (10/10 stages) | 0/5 (4/10) | $0.024 |
| **Total** | | **35/35** | **0/35** | |

Runs in [results-2026-11-02-openrouter.jsonl](results-2026-11-02-openrouter.jsonl), cost at OpenRouter's list price
(US$1.25 / 4.25 per million tokens in and out). To run it: an `OPENROUTER_API_KEY` in `~/.athos/.env`, then
`athos bench expense-review --agents openrouter --runs 1 --without`.

## The gallery's measured examples, November 2: Muse Spark through the Meta Model API, 5 runs each arm

| Case | Who | With the page | Without it | What the runs without it missed |
|---|---|---|---|---|
| expense-review | an accountant | 5/5 (10/10 stages) | 0/5 (6/10) | the card fee on foreign claims, the meal cap |
| contract-transfer | a lawyer | 5/5 | 0/5 | the table's columns and priorities, the governing-law row, `Push first:`, leaving the decision to the client |
| support-tickets | a support team | 5/5 | 0/5 (4/10 stages) | the window counted from delivery, shipping only for damage, the second-late credit, no promised dates, card numbers, the signature |

These are the three examples shown first in the [gallery](../../gallery/), each with its result on the page. Runs in
[results-2026-11-02.jsonl](results-2026-11-02.jsonl).

## The gallery's journalism and science examples, November 3: Muse Spark Open through OpenRouter, 5 runs each arm

| Case | Who | With the page | Without it | What the runs without it missed |
|---|---|---|---|---|
| source-check | a newsroom | 5/5 (8/8 stages) | 0/5 (5/8) | the right of reply with its deadline (every run), cutting a claim whose second source heard it from the first or whose only source is a competitor, the anonymous source's description |
| small-sample | a lab | 5/5 (8/8 stages) | 0/5 (7/8) | why a non-parametric test (n under 30) and the seed in the write-up; one run reported means instead of medians. Without the page the model already picked Mann-Whitney: the gap here is small |

With these, every profession in the gallery shows a measured result. $0.021 and $0.033 a run with the page. Runs in
[results-2026-11-03-openrouter.jsonl](results-2026-11-03-openrouter.jsonl).

## Meta's agents on the expense review, 2 runs each arm

| Muse Spark via | With the know-how | Without it | Median time | Cost a run |
|---|---|---|---|---|
| Meta Model API (direct) | 5/5 (10/10 stages) | 0/5 (6/10) | 16 s | $0.037 |
| Muse Code | 2/2 (10/10) | 0/2 (6/10) | 94 s | $0.49 |
| OpenCode | 2/2 (10/10) | 0/2 (6/10) | 33 s | $0.22 |

Without the know-how all three miss the same stages: the card fee on foreign claims and the meal cap (and so the
approvals and the totals that depend on them).

## Run it yourself

With a Meta Model API key in `MODEL_API_KEY` (about $0.07 for one run each arm):

```sh
athos bench expense-review --agents meta --runs 1 --without
athos bench report
```

`athos bench --list` shows every case; `--agents muse,opencode` runs the same case in Muse Code and OpenCode.
