---
id: triage-a-production-incident
title: Triage a production incident where the traps usually are
when: a service is down, slow or throwing errors in production; an alert fired or users report a failure, and the cause must be found and the damage contained before anything else
---

## #contain_first
**When:** the incident is reported.
**Do:** write down in three lines what fails, since when and for whom (all users, one region, one customer). Propose the fastest safe containment (roll back the last deploy, turn off the feature flag, fail over) and ask the person before running anything that changes production.
**Because:** stopping the damage comes before understanding it; a change in production is the on-call person's decision, never the agent's.
**Links:** [[triage-a-production-incident#what_changed]]

## #what_changed
**When:** the damage is contained, or containment is not possible yet.
**Do:** list everything that changed in the hour before the first error: deploys, config and flag changes, certificates and keys that expired, database migrations, traffic peaks, dependencies' status pages. Read it from the tools (deploy log, git log, the provider's status), not from memory.
**Because:** most incidents follow a change; the ones that don't are usually an expiry (certificate, token, quota) nobody remembered.
**Links:** [[triage-a-production-incident#evidence]]

## #evidence
**When:** with the list of changes.
**Do:** confirm or discard each candidate with evidence: the error rate and latency per version, the first log line of the failure, a request that reproduces it. Quote the lines; never conclude from a dashboard you did not read.
**Because:** a plausible cause that isn't proven sends the team to fix the wrong thing.
**Links:** [[triage-a-production-incident#fix]]

## #fix
**When:** the cause is proven.
**Do:** propose the smallest fix and how to verify it in production (which metric must go back to normal, for how long). The person approves and runs it.
**Links:** [[triage-a-production-incident#postmortem]]

## #postmortem
**When:** the service is back to normal.
**Do:** write the timeline (detection, containment, cause, fix, with times), the trap that caused it and one action that prevents it from happening again, with an owner. Blameless: systems and decisions, not people.
**Because:** what one engineer learnt the hard way is the team's know-how only if it is written where the next one will find it.
