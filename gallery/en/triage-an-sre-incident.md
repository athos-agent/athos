---
id: triage-an-sre-incident
title: Triage an incident as the on-call SRE
when: an alert fired or users report errors, slowness or an outage in production, and the on-call engineer must contain it and find the cause
profession: ops
lang: en
---

## #scope
**When:** the incident is reported.
**Do:** write in three lines what fails, since when and for whom; set the severity with the team's scale (example to replace with yours: SEV1 every user, SEV2 one feature or region, SEV3 degraded).
**Links:** [[triage-an-sre-incident#payments]]

## #payments
**When:** the scope is known.
**Do:** check whether checkout, payouts or billing are among what fails (the error rate of the payment endpoints, the payment provider's status page).
**If:** payments are affected → [[tell-customers-about-a-payments-incident]]
**Because:** customers who can't pay or get paid must hear it from us first, and support and finance need the same words.
**Links:** [[triage-an-sre-incident#contain]]

## #contain
**When:** with the scope and the severity.
**Do:** propose the fastest safe containment (roll back the last deploy, turn off the feature flag, fail over) and ask the person before running anything that changes production.
**Because:** a change in production is the on-call engineer's decision, never the agent's.
**Links:** [[triage-an-sre-incident#cause]]

## #cause
**When:** the damage is contained.
**Do:** list what changed in the hour before the first error (deploys, configuration, flags, expiring certificates, traffic) from the tools, and confirm or discard each candidate with a quoted log line or metric.
**Because:** a cause that isn't proven sends the team to fix the wrong thing.
**Links:** [[triage-an-sre-incident#close]]

## #close
**When:** the service is back to normal.
**Do:** write down what happened and what prevents it next time.
**Calls:** [[write-the-postmortem]]
