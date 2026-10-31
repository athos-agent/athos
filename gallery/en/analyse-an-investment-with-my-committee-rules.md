---
id: analyse-an-investment-with-my-committee-rules
title: Analyse an investment with my committee's rules
when: a client brings an investment, a fund, a trust or a property deal to analyse; preparing the risk and net-return table an advisor or accountant reviews before giving their opinion
profession: finance
lang: en
---

## #data_out
**When:** before pasting the prospectus or the client's details.
**Do:** ask whether the material holds the client's identity, account numbers or tax IDs; if so, propose removing them, running the task through [[connector:pii-guard]], or a local model.
**Because:** a hosted model sees everything shown to it; the client's financial data is confidential.
**Links:** [[analyse-an-investment-with-my-committee-rules#facts]]

## #facts
**When:** with the material at hand.
**Do:** summarise in five lines: what is bought, the vehicle, the currency, the term and exit, the costs (entry, management, exit). Say what is missing.
**Links:** [[analyse-an-investment-with-my-committee-rules#jurisdictions]]

## #jurisdictions
**When:** the facts are clear.
**Do:** note in which countries the investor, the asset and the vehicle are.
**If:** they are not all in the same country → [[check-the-cross-border-tax-treatment]]
**Because:** the net return of a cross-border investment depends on treaties and withholding the prospectus never shows.
**Links:** [[analyse-an-investment-with-my-committee-rules#numbers]]

## #numbers
**When:** with the facts and the tax treatment.
**Do:** compute with code the net return after costs and taxes in three scenarios (bad, expected, good) using MY committee's assumptions (examples to replace with yours: inflation, exchange rate path, vacancy for property). Show the formulas.
**Because:** arithmetic is done with code; assumptions are the committee's, not the prospectus's.
**Links:** [[analyse-an-investment-with-my-committee-rules#risks]]

## #risks
**When:** the numbers are done.
**Do:** a table: risk, how likely, how much it costs, how to mitigate (liquidity, currency, counterparty, concentration, legal). Then the open questions for the client.
**Because:** this is the table the committee reads.
**Links:** [[analyse-an-investment-with-my-committee-rules#opinion]]

## #opinion
**When:** the table is ready.
**Do:** leave the recommendation to the person: list what an opinion would rest on, never give one in their name.
**Because:** investment and tax advice is the licensed professional's responsibility.
