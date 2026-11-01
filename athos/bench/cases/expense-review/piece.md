How the finance team reviews expense claims, in this order. Each stage goes in `review.json` under `stages` (the
names below) once it is done.

1. `read_claims`: every row of `claims.csv` is one claim; keep the file's order.
2. `duplicates`: two claims with the same employee, date, amount and currency are a duplicate. Keep the first one
   (lowest claim_id); reject the later ones with the reason "duplicate of <first id>".
3. `not_reimbursable`: categories `alcohol` and `personal` are never reimbursed: reject them.
4. `foreign_currency`: ONLY for claims whose currency is not USD. Skip this stage for USD claims: they get
   `fx_rate: null` and no fee.
   - 4a. The rate is the one in `rates.csv` for the month of the claim's date (a September claim uses September's
     rate, even when it is reviewed in October).
   - 4b. usd = amount × usd_per_unit, plus 1.5% for the card's foreign-exchange fee: usd = amount × rate × 1.015,
     rounded to cents (half up).
   - 4c. Record the rate in `fx_rate`. From here on, every limit is compared in USD, never in the claim's currency.
5. `receipts`: a claim over 75.00 USD without a receipt is not rejected: its decision is `ask` (ask the employee for
   the receipt) and `reimburse_usd` is 0 until it arrives.
6. `meal_cap`: meals are reimbursed up to 60.00 USD per claim. Over that, approve 60.00 and say "capped at 60" in the
   reason.
7. `approve_rest`: every other claim is approved for its USD amount.
8. `totals`: `totals` = reimbursed USD per employee (approved claims only), and `total_usd` their sum.
9. `open_decisions`: exceptions to the policy are the finance lead's decision, never the reviewer's. Apply the rule
   anyway (a meal stays capped) and list in `open_decisions` every claim whose note asks for an exception, and every
   claim waiting on a receipt (`ask`), by claim_id.
10. `review_written`: write `REVIEW.md` for the finance lead and `review.json` with `stages`, `claims` (one per claim:
    `claim_id`, `decision`, `reimburse_usd`, `fx_rate`, `reason`), `totals`, `total_usd` and `open_decisions`.
