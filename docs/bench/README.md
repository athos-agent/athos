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
