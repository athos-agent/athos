---
id: write-the-postmortem
title: Write the postmortem of an incident
when: an incident is resolved and the team writes down what happened, why, and what will prevent it
profession: ops
lang: en
---

## #timeline
**When:** the service is back to normal.
**Do:** write the timeline with times (detection, escalation, containment, cause found, fix, all clear), taken from the incident channel and the tools, not from memory.
**Links:** [[write-the-postmortem#cause]]

## #cause
**When:** with the timeline.
**Do:** name the cause and the trap behind it (why nothing caught it earlier). Blameless: systems and decisions, not people.
**Links:** [[write-the-postmortem#actions]]

## #actions
**When:** the cause is written.
**Do:** agree at most three actions that prevent it or detect it earlier, each with an owner and a date.
**Because:** a postmortem with ten actions gets none of them done.
