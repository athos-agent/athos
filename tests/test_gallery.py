import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from athos import gallery, start, store, wiki
from tests.helpers import TempHome

ROOT = Path(__file__).resolve().parents[1]
ATHOS = str(ROOT / "bin" / "athos")
# No medicine anywhere in the gallery (the hackathon doesn't allow it), in either language.
MEDICINE = re.compile(r"\b(medic\w*|médic\w*|patient\w*|paciente\w*|clinic\w*|clínic\w*|diagnos\w*|diagnós\w*|"
                      r"hospital\w*|nurs\w*|enfermer\w*|drug\w*|fármaco\w*|medicament\w*|symptom\w*|síntoma\w*|"
                      r"therap\w*|terap\w*|surg\w*|cirug\w*|prescri\w*|receta\w*)\b", re.I)


def local_fetch(calls):
    """The gallery as raw.githubusercontent.com would serve it, from this checkout: no network."""
    def fetch(url):
        calls.append(url)
        assert url.startswith(gallery.RAW), url
        rel = url[len(gallery.RAW):]
        if rel == "gallery.json":
            return json.dumps(gallery.catalog())
        return (gallery.DIR / rel).read_text()
    return fetch


class GalleryEntriesTest(TempHome):
    """Every entry in gallery/: a valid page whose links and branches lead to pages that exist."""

    def pages(self):
        return [(f, *gallery.parse(f.read_text())) for lang in gallery.LANGS
                for f in sorted((gallery.DIR / lang).glob("*.md"))]

    def test_every_page_parses_with_its_frontmatter(self):
        pages = self.pages()
        self.assertGreaterEqual(len(pages), 30)
        for f, meta, p in pages:
            with self.subTest(page=f.name):
                self.assertEqual(p.id, f.stem)
                self.assertEqual(meta["lang"], f.parent.name)
                self.assertIn(meta["profession"], start.PROFILES)
                self.assertTrue(p.title and p.when)
                self.assertEqual(store.slugify(p.id), p.id)                # saved under the same id
                st = wiki.statements(p)
                self.assertTrue(wiki.is_wiki(p) and len(st) >= 2)
                for s in st:
                    self.assertTrue(s.when and s.do, f"{p.id}#{s.id}")

    def test_links_and_branches_lead_to_pages_of_the_same_language(self):
        for lang in gallery.LANGS:
            pieces = [p for f, _, p in self.pages() if f.parent.name == lang]
            lint = wiki.lint(pieces)
            self.assertEqual(lint["broken"], [], lang)
            self.assertEqual(lint["duplicate_ids"], [], lang)
            ids = {p.id for p in pieces}
            for p in pieces:
                for s in wiki.statements(p):
                    for c in s.calls:
                        self.assertIn(c["page"], ids, f"{p.id}#{s.id}")

    def test_every_entry_branches_and_both_languages_have_the_same_examples(self):
        cat = gallery.catalog()
        entries = [e for e in cat["entries"] if e["entry"]]
        for e in entries:
            self.assertTrue(any(s["branches"] for s in e["steps"]), e["id"])
            self.assertTrue(any(b["if"] for s in e["steps"] for b in s["branches"]) or e["calls"], e["id"])
        per = {lang: sorted(e["profession"] for e in entries if e["lang"] == lang) for lang in gallery.LANGS}
        self.assertEqual(per["en"], per["es"])
        self.assertEqual(set(per["en"]), {"law", "ops", "journalism", "science", "sports", "finance"})
        dd = next(e for e in entries if e["id"] == "due-diligence-of-a-latam-sme")
        profs = {next(x for x in cat["entries"] if x["id"] == c)["profession"] for c in dd["calls"]}
        self.assertEqual(profs, {"finance", "law"})             # several specialists' pages

    def test_the_finance_starter_is_in_the_gallery_as_it_is(self):
        for lang in gallery.LANGS:
            for f in start.starters(lang, "finance"):
                _, body = store.parse_frontmatter(f.read_text())
                _, p = gallery.parse((gallery.DIR / lang / f.name).read_text())
                self.assertEqual(p.body.strip(), body.strip())

    def test_no_medicine(self):
        for f, _, _ in self.pages():
            self.assertIsNone(MEDICINE.search(f.read_text()), f.name)

    def test_public_guard(self):
        guard = os.environ.get("ATHOS_PUBLIC_GUARD")         # the maintainers' own name check, when they have it
        if not guard:
            self.skipTest("ATHOS_PUBLIC_GUARD not set")
        r = subprocess.run([sys.executable, guard, str(gallery.DIR)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_built_files_are_up_to_date(self):
        self.assertEqual(json.loads((gallery.DIR / "gallery.json").read_text()), gallery.catalog())
        with tempfile.TemporaryDirectory() as d:
            j, h = gallery.build(Path(d))
            self.assertEqual(h.read_text(), (gallery.DIR / "index.html").read_text())
            page = h.read_text()
            self.assertNotIn("__GALLERY__", page)
            self.assertIn('"review-a-services-contract"', page)
            self.assertIn("Athos · add from gallery: {id}", page)


class GalleryAddTest(TempHome):
    def test_the_request_is_recognised_in_both_languages(self):
        self.assertEqual(gallery.requested("Athos · add from gallery: verify-a-source"), "verify-a-source")
        self.assertEqual(gallery.requested("  Athos · agregar desde la galería: verificar-una-fuente."),
                         "verificar-una-fuente")
        self.assertIsNone(gallery.requested("add verify-a-source from the gallery"))

    def test_only_this_repositorys_gallery(self):
        self.assertEqual(gallery.check_url(gallery.RAW + "es/verificar-una-fuente.md"), ("es", "verificar-una-fuente"))
        for bad in ["http://raw.githubusercontent.com/athos-agent/athos/main/gallery/en/x.md",
                    "https://raw.githubusercontent.com/someone/athos/main/gallery/en/x.md",
                    "https://raw.githubusercontent.com/athos-agent/athos/dev/gallery/en/x.md",
                    "https://raw.githubusercontent.com/athos-agent/athos/main/gallery/en/../../x.md",
                    "https://raw.githubusercontent.com/athos-agent/athos/main/gallery/en/x.md?a=1",
                    "https://raw.githubusercontent.com.evil.io/athos-agent/athos/main/gallery/en/x.md",
                    "https://github.com/athos-agent/athos/blob/main/gallery/en/x.md",
                    "file:///etc/passwd"]:
            with self.assertRaises(ValueError, msg=bad):
                gallery.check_url(bad)
        with self.assertRaises(ValueError):
            gallery.add("../secrets", fetch=local_fetch([]))
        with self.assertRaises(ValueError):
            gallery.fetch_url("https://example.com/gallery/en/x.md")       # refused before any request

    def test_add_saves_the_entry_and_the_pages_it_calls_as_version_1(self):
        calls = []
        r = gallery.add("review-a-services-contract", fetch=local_fetch(calls))
        self.assertTrue(all(u.startswith(gallery.RAW) for u in calls))
        ids = [x["id"] for x in r["pages"]]
        self.assertEqual(ids, ["review-a-services-contract", "add-a-data-protection-clause",
                               "draft-a-clause-in-the-firm-format"])
        for pid in ids:
            p = store.get(pid)
            self.assertEqual(p.version, 1)
            self.assertEqual(p.origin["platform"], "gallery")
        self.assertIn("Added from Athos's gallery", gallery.summary(r))
        self.assertIn("If:** the provider processes personal data", store.get(ids[0]).body)

    def test_add_never_overwrites_what_the_person_has(self):
        store.create("Mine", "my own way", "## #a\n**When:** x.\n**Do:** mine.\n", piece_id="write-the-postmortem")
        r = gallery.add("triage-an-sre-incident", fetch=local_fetch([]))
        self.assertEqual({x["id"]: x["status"] for x in r["pages"]}["write-the-postmortem"], "exists")
        self.assertEqual(store.get("write-the-postmortem").title, "Mine")
        again = gallery.add("triage-an-sre-incident", fetch=local_fetch([]))
        self.assertEqual({x["status"] for x in again["pages"]}, {"exists"})
        self.assertIn("Ya estaba en tu know-how", gallery.summary(again, "es"))
        self.assertEqual(store.get("triage-an-sre-incident").version, 1)

    def test_dry_run_and_url_and_errors(self):
        r = gallery.add(gallery.RAW + "es/hacer-un-analisis-reproducible.md", fetch=local_fetch([]), dry_run=True)
        self.assertEqual([x["status"] for x in r["pages"]], ["new", "new"])
        self.assertEqual(store.all_pieces(), [])
        self.assertIn("se agregaría", gallery.summary(r, "es"))
        with self.assertRaises(LookupError):
            gallery.add("no-such-entry", fetch=local_fetch([]))

        def lying(url):
            return json.dumps(gallery.catalog()) if url == gallery.INDEX_URL else "---\nid: other\n---\nhi\n"
        with self.assertRaises(ValueError):
            gallery.add("verify-a-source", fetch=lying)
        self.assertEqual(store.all_pieces(), [])

    def test_the_prompt_hook_hands_the_request_to_the_agent(self):
        ev = {"session_id": "s1", "cwd": self.home, "prompt": "Athos · add from gallery: verify-a-source"}
        r = subprocess.run([sys.executable, ATHOS, "hook", "prompt"], input=json.dumps(ev), capture_output=True,
                           text=True, cwd=self.home, env=os.environ.copy())
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("add verify-a-source", ctx)
        self.assertEqual(store.all_pieces(), [])                 # the hook itself downloads nothing

    def test_athos_find_and_athos_add(self):
        from athos import mcp
        text = mcp.call("athos_find", {"request": "Athos · agregar desde la galería: verificar-una-fuente"})
        self.assertIn("athos_add", text)
        orig = gallery.fetch_url
        gallery.fetch_url = local_fetch([])
        try:
            out = mcp.call("athos_add", {"id": "verificar-una-fuente"})
        finally:
            gallery.fetch_url = orig
        self.assertIn("verificar-una-fuente", out)
        self.assertIsNotNone(store.get("publicar-una-nota-de-correccion"))
