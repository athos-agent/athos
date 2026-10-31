from athos import load, session, start, store, trail, wiki
from tests.helpers import TempHome

DEAL = """## #facts
**When:** with the prospectus.
**Do:** summarise what is bought.

## #borders
**When:** the facts are clear.
**Do:** note the countries of the investor and the asset.
**If:** they are not all in the same country → [[cross-border-tax]]

## #table
**When:** at the end.
**Do:** build the risk table.
**Calls:** [[house-format#columns]]
"""
TAX = """## #residence
**When:** at the start.
**Do:** state each tax residence.

## #treaty
**When:** with the countries.
**Do:** check the treaty article.
"""
FORMAT = """## #intro
**When:** never mind.
**Do:** a heading.

## #columns
**When:** building a table.
**Do:** use the house columns.
"""


class ComposeTest(TempHome):
    def setUp(self):
        super().setUp()
        self.deal = store.create("Analyse a deal", "a client brings an investment deal to analyse", DEAL,
                                 piece_id="deal")
        store.create("Cross-border tax", "an investment crosses borders", TAX, piece_id="cross-border-tax")
        store.create("House format", "formatting tables the house way", FORMAT, piece_id="house-format")

    def test_calls_and_if_are_read_from_a_statement(self):
        s = {x.id: x for x in wiki.statements(self.deal)}
        self.assertEqual(s["borders"].calls, [{"page": "cross-border-tax", "statement": None,
                                               "if": "they are not all in the same country"}])
        self.assertEqual(s["table"].calls, [{"page": "house-format", "statement": "columns", "if": ""}])
        self.assertEqual(s["facts"].calls, [])

    def test_the_pages_a_piece_calls_load_with_it(self):
        found = load.relevant("analyse this investment deal for a client", load.enabled())
        self.assertEqual([p.id for p in found], ["deal", "cross-border-tax", "house-format"])
        self.assertIn("Steps that hand over", load.inject_text(found))

    def test_the_trail_shows_called_steps_under_the_step_that_calls_them(self):
        session.save("s", {"task_id": "t", "task_loaded": ["deal", "cross-border-tax"], "trail": []})
        trail.step("s", "deal#borders", None)
        trail.step("s", "cross-border-tax#residence", None)
        v = trail.view(session.load("s"))
        self.assertEqual([p["id"] for p in v["pieces"]], ["deal"])       # the called page is not listed again
        rows = [(x.get("piece", "deal"), x["id"], x["state"]) for x in v["pieces"][0]["steps"]]
        self.assertEqual(rows, [("deal", "facts", "ahead"), ("deal", "borders", "done"),
                                ("cross-border-tax", "residence", "now"), ("cross-border-tax", "treaty", "ahead"),
                                ("deal", "table", "ahead"), ("house-format", "columns", "ahead")])
        sub = v["pieces"][0]["steps"][2]
        self.assertEqual((sub["depth"], sub["if"]), (1, "they are not all in the same country"))
        self.assertTrue(sub["label"].startswith("↳ "))


class StartersTest(TempHome):
    def test_every_profession_installs_in_both_languages(self):
        for lang in start.LANGS:
            for profile in ("ops", "journalism", "science", "finance"):
                self.assertTrue(start.starters(lang, profile), (lang, profile))
                self.assertTrue(start.TRY[(lang, profile)])
        added, _ = start.install("en", "finance")
        self.assertEqual(sorted(p.id for p in added),
                         ["analyse-an-investment-with-my-committee-rules", "check-the-cross-border-tax-treatment"])
        self.assertEqual(wiki.lint()["broken"], [])
