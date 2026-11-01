import urllib.parse

from athos import share, store
from tests.helpers import TempHome

BODY = ("## #parties\n**When:** with the contract at hand.\n**Do:** summarise the parties.\n"
        "**Links:** [[check-the-guarantee]]\n\n## #clauses\n**Do:** mark each clause.\n")
GUARANTEE = "## #guarantee\n**Do:** check the guarantee amount and who holds it.\n"


class ShareTest(TempHome):
    def setUp(self):
        super().setUp()
        store.create("Review a lease", "a client brings a lease to review", BODY, projects=["northwind-case"],
                     piece_id="review-a-lease")
        store.create("Check the guarantee", "the lease has a guarantee", GUARANTEE, piece_id="check-the-guarantee")
        self.opened = []

    def send(self, author=""):
        return share.send("review-a-lease", author, "en", opener=lambda u: self.opened.append(u) or True,
                          copier=lambda t: True)

    def test_the_draft_keeps_only_public_fields_and_takes_the_linked_pages(self):
        r = share.prepare("review-a-lease", "law")
        self.assertEqual([p["id"] for p in r["pages"]], ["review-a-lease", "check-the-guarantee"])
        text = (share.folder("review-a-lease") / "review-a-lease.md").read_text()
        self.assertIn("profession: law", text)
        self.assertIn("lang: en", text)
        for private in ("projects:", "created:", "last_used:", "origin:", "version:", "## History"):
            self.assertNotIn(private, text)

    def test_what_looks_private_is_flagged_and_blocks_the_send(self):
        p = store.get("review-a-lease")
        store.update(p.id, "client", body=BODY + "\nAsk ana@northwind.com, +54 11 4321 5678, CUIT 20-12345678-9, "
                     "file /Users/ana/cases/lease.pdf, for the northwind-case.\n")
        r = share.prepare("review-a-lease", "law")
        kinds = {k for k, _ in r["pages"][0]["findings"]}
        self.assertEqual(kinds, {"email", "phone", "id number", "folder", "project"})
        self.assertFalse(self.send()["sent"])
        self.assertEqual(self.opened, [])

    def test_a_clean_draft_opens_the_gallery_form_filled_in_with_every_page_and_the_credit(self):
        share.prepare("review-a-lease", "law")
        r = self.send("Laura G.")
        self.assertTrue(r["sent"])
        url = self.opened[0]
        self.assertTrue(url.startswith(share.FORM + "?usp=pp_url&"))
        got = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).items()}
        self.assertEqual(got[share.FIELDS["title"]], "Review a lease")
        self.assertEqual(got[share.FIELDS["author"]], "Laura G.")
        pages = got[share.FIELDS["pages"]]
        self.assertIn("===== review-a-lease.md =====", pages)
        self.assertIn("===== check-the-guarantee.md =====", pages)
        self.assertIn("author: Laura G.", pages)

    def test_pages_too_long_for_a_link_go_by_the_clipboard(self):
        store.update("review-a-lease", "long", body=BODY + "\n" + "**Do:** read every clause twice.\n" * 400)
        share.prepare("review-a-lease", "law")
        copied = []
        r = share.send("review-a-lease", "", "en", opener=lambda u: self.opened.append(u) or True,
                       copier=lambda t: copied.append(t) or True)
        self.assertTrue(r["clipboard"])
        self.assertIn("===== review-a-lease.md =====", copied[0])
        self.assertLess(len(self.opened[0]), share.URL_MAX)

    def test_the_agents_rewrite_replaces_a_draft_page(self):
        share.prepare("review-a-lease", "law")
        share.write_draft("review-a-lease", "check-the-guarantee",
                          "---\nid: check-the-guarantee\ntitle: Check the guarantee\nwhen: x\n---\n\n## #g\n**Do:** y.\n")
        self.assertIn("**Do:** y.", (share.folder("review-a-lease") / "check-the-guarantee.md").read_text())
        with self.assertRaises(ValueError):
            share.write_draft("review-a-lease", "check-the-guarantee", "---\nid: other\n---\nx")

    def test_the_persons_words_ask_for_a_share(self):
        self.assertTrue(share.asked("compartí mi forma de revisar contratos en la galería"))
        self.assertTrue(share.asked("share my lease review with the gallery"))
        self.assertFalse(share.asked("show me the gallery"))

    def test_fictional_stand_ins_do_not_block_the_send(self):
        self.assertEqual(share.findings("Ask contacto@ejemplo.com, CUIT 30-00000000-0, or ana@example.com.", []), [])
        self.assertTrue(share.findings("Ask ana@acme.com", []))
