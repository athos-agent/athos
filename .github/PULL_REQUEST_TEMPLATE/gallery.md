## A way of working for the gallery

**What it is for** (one line, in the words a professional would use):

**Profession:** law · finance · journalism · science · ops · other

**The branch it shows** (which step hands over to which page, and when):

### Checklist
- [ ] The same pages in `gallery/en/` and `gallery/es/` (or I said which language I need help with)
- [ ] Fictional: no real clients, people, companies, cases or data
- [ ] It leaves the professional decision to the person; no medical or health topics
- [ ] At least one `**Calls:**` or `**If:**` step, and every page it links to is in the gallery
- [ ] `python3 bin/athos gallery build` run, and `gallery/gallery.json` / `gallery/index.html` committed
- [ ] `python3 -m unittest tests.test_gallery` passes

See [gallery/CONTRIBUTING.md](../gallery/CONTRIBUTING.md) ([en español](../gallery/CONTRIBUIR.md)).
