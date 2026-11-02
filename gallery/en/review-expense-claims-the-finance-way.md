---
id: review-expense-claims-the-finance-way
title: Review expense claims the finance team's way
when: reviewing the month's employee expense claims (several currencies, receipts, meal limits) before they are paid, and leaving the exceptions to the finance lead
profession: finance
lang: en
bench: expense-review
measured: "5/5 with this page, 0/5 without"
---

## #read_claims
**When:** the month's claims file and the exchange rates are at hand.
**Do:** take every row as one claim and keep the file's order. Two claims with the same employee, date, amount and currency are a duplicate: keep the first one and reject the later ones with "duplicate of <first id>".
**If:** a claim is in another currency → [[review-expense-claims-the-finance-way#foreign_currency]]
**Because:** the same receipt sent twice is the most common error in a month's claims.
**Links:** [[review-expense-claims-the-finance-way#not_reimbursable]]

## #not_reimbursable
**When:** the duplicates are out.
**Do:** reject the categories the policy never pays (examples to replace with yours: alcohol, personal expenses).
**Because:** the policy decides it, not the amount.
**Links:** [[review-expense-claims-the-finance-way#foreign_currency]]

## #foreign_currency
**When:** a claim is not in the company's currency. Skip this step for claims that are.
**Do:** use the rate of the month of the claim's date (a September claim uses September's rate, even when reviewed in October), add the card's foreign-exchange fee (example: 1.5%) and round to cents. From here on compare every limit in the company's currency, never in the claim's.
**Because:** a taxi under the receipt limit in euros can be over it in dollars; the fee is what the employee really paid.
**Links:** [[review-expense-claims-the-finance-way#receipts_and_caps]]

## #receipts_and_caps
**When:** every amount is in the company's currency.
**Do:** a claim over the receipt limit (example: 75.00) without a receipt is not rejected: ask the employee for it and pay 0 until it arrives. Meals are paid up to the cap (example: 60.00 per claim); over it, pay the cap and say "capped at 60". Approve the rest for its amount.
**Because:** a missing receipt is a question for the employee, not a rejection.
**Links:** [[review-expense-claims-the-finance-way#open_decisions]]

## #open_decisions
**When:** every claim has a decision.
**Do:** total what is paid per employee. List for the finance lead every claim whose note asks for an exception and every claim waiting on a receipt, by id. Apply the rule anyway (a meal stays capped): exceptions are the finance lead's decision, never the reviewer's.
**Because:** the reviewer applies the policy; the person who owns it decides the exceptions.
