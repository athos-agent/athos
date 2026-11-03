How the newsroom checks a story's sources before publishing, in this order. Each stage goes in `factcheck.json` under
`stages` (the names below) once it is done.

1. `read_claims`: every row of `claims.csv` is one claim, with its sources from `sources.csv`. Write down for each
   source how they know (saw it, were told, hold the document) and what they gain if it is published (`stake`).
2. `records`: check every claim against the documents in `records.csv`. A record that states the claim makes it
   `confirmed` → action `keep`. A record that backs only part of it (a range, a different figure) makes it `partial` →
   action `attribute` (the story says who claims it). No record: `unconfirmed` → action `cut`, unless stage 5 confirms it.
3. `one_origin`: two sources who heard it from the same place are ONE source. A source whose `heard_from` is another
   source of the same claim does not confirm it; with no record, the claim stays `unconfirmed` → `cut`.
4. `stake`: a claim whose only source gains from its publication (a competitor, a rival) needs a record. Without one it
   is `unconfirmed` → `cut`, never kept or attributed.
5. `double_confirm`: a claim from an anonymous source goes in only when a second, independent source (one the first
   didn't tell) or a document confirms the key fact; then it is `confirmed` → `keep`.
6. `anonymity`: for each anonymous source the published story relies on, add an entry in `anonymous` with a
   description as precise as possible WITHOUT identifying them (role and place, never the name) and why they asked
   not to be named (risk to their job). Anonymous sources' names never appear in STORY.md or in `anonymous`.
7. `right_of_reply`: list every person and company the published story makes a claim about, with the questions for
   each one and a deadline of 48 hours before publication, written as a date and time (`2026-11-04 09:00`).
8. `story_written`: write STORY.md with only the kept and attributed claims (attributed ones say who claims them),
   and `factcheck.json` with `stages`, `claims`, `anonymous` and `right_of_reply`.
