# Add your way of working to the gallery

The gallery shows ways of working that anyone can take into their own Athos with one click
([see it](https://athos-agent.github.io/athos/)). Each one is a page of steps a professional follows, with the
branches it takes only when the case needs them. If you have a checklist you are proud of, share it here.
[En español](CONTRIBUIR.md).

## What makes a good entry

- **A real way of working from your field**, written as the steps you actually follow, in the order you follow them.
  Your criteria and your format, not a textbook summary.
- **At least one branch**: a step that hands over to another page, always (`**Calls:**`) or only in some cases
  (`**If:** <condition> → [[page]]`). That is what the gallery is for: showing the method expanding only where the
  case needs it.
- **Fictional**: no real clients, people, companies, cases or data.
- **It leaves the professional decision to the person**: list what an opinion would rest on, never give one in their
  name.
- **English and Spanish**: the same page in `gallery/en/` and `gallery/es/`. If you can only write one, open the pull
  request anyway and say so: we'll help with the other.
- **Not accepted for now**: medical or health topics, and anything that gives legal, tax or investment advice in
  someone's name.

## The format

Each page is a markdown file named after its id (`gallery/en/<id>.md`), the same format Athos keeps in
`~/.athos/know-how/`, plus `profession` and `lang`:

```markdown
---
id: verify-a-source
title: Verify a source before publishing
when: a source gives information for a story and it must be checked before it is published
profession: journalism
lang: en
---

## #who
**When:** with the source's information at hand.
**Do:** write down who the source is, how they know what they say and what they gain if it is published.
**Links:** [[verify-a-source#anonymous]]

## #anonymous
**When:** the source's role is clear.
**Do:** note whether the source asks not to be named.
**If:** the source is anonymous → [[double-confirm-an-anonymous-source]]
**Because:** readers can't judge an anonymous source, so the newsroom must have judged it for them.
```

- `profession` is one of `law`, `finance`, `journalism`, `science`, `ops`, `sports`, `other`.
- Each step (`## #step_id`) has **When** and **Do**; **Because** and **Links** when they help.
- Every page a step links to or hands over to must be in the gallery too, in the same language.

## Starting from your own Athos

If the way of working is already in your Athos, start from it: `athos show <id>` prints it. Copy it into
`gallery/en/<id>.md`, add `profession` and `lang` to its frontmatter, remove the `## History` section, the
`projects`, `created`, `last_used`, `origin` and `version` lines, and anything that names a real client, person or
project.

## Checking it and sending it

1. Fork the repository and add your pages under `gallery/en/` and `gallery/es/`.
2. Rebuild the gallery: `python3 bin/athos gallery build` (it updates `gallery/gallery.json` and `gallery/index.html`).
3. Run the checks: `python3 -m unittest tests.test_gallery` (pages parse, links lead to pages that exist, every entry
   branches, both languages have the same examples).
4. Open a pull request with the **gallery** template. Once it is merged, the gallery page updates by itself and anyone
   can add your way of working with `athos add <id>`.

No time for a pull request? [Propose an idea](https://github.com/athos-agent/athos/issues/new?template=gallery-idea.yml)
and describe the steps in your own words.
