The coach's method, in this order. Each stage goes in `plan.json` under `stages` (the names below) once it is done.
The load of a session is minutes × RPE (session RPE, 1–10).

1. `weekly_loads`: the load of each of the last four weeks in `log.csv` (Monday to Sunday), oldest first.
2. `acwr`: acute:chronic ratio = last week's load ÷ the mean of the four weeks (two decimals).
3. `target_load`: next week's target = last week's load × 0.90 if the ratio is above 1.3 (a spike: cut back), otherwise
   × 1.10. Never more than +10%.
4. `sessions_fit_target`: plan next week's sessions so their total load is within ±5% of the target.
5. `hard_days_rule`: at most two hard sessions (RPE 7 or more), never on consecutive days.
6. `rest_after_long`: exactly one session of type `long`; the day after it is rest or easy (RPE 3 or less).
7. `availability`: no session on the athlete's `unavailable_days`.
8. `open_decisions`: whether to run a tune-up race and the goal pace are the athlete's decisions. Never choose them and
   never put a race in the plan: list them as open decisions.
9. `plan_written`: write `PLAN.md` for the athlete and `plan.json` with: `stages`, `weekly_loads` (list),
   `acwr`, `target_load`, `sessions` (list of `{"day": "Mon".."Sun", "type", "minutes", "rpe"}`) and `open_decisions`
   (list of strings). No `chosen_*` keys.
