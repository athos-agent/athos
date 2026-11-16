"""An ambiguous project name is decided by context: a project named like a common word ("api") is named by a request
only with a reference cue ("in api", "from the api repo", "~/api", a backtick); a distinctive name keeps working without
one; on a frontier model an ambiguous mention without a cue becomes one index line, so the model decides; never in a
public repository. All data here is synthetic."""

from athos import control, store
from tests.test_audit import HookCase, events, piece

BODY = "## #one\n**When:** at the start.\n**Do:** the first thing.\n"


class CueTest(HookCase):
    def test_reference_cues_in_english_and_spanish(self):
        cue = control.has_cue
        for text in ("fix it like we did in api", "copy the handler from the api repo", "in the api project, please",
                     "como hicimos en api", "usá lo del proyecto api", "the api repo has it", "open ~/api/src/main.py",
                     "see api/handlers.py", "it is under /work/api/ too", 'the "api" folder',
                     "en el repo api", "from api", "desde api"):
            self.assertTrue(cue("api", text), text)
        # A name in backticks or quotes alone is no cue: `api` may be a key, a column, a word (until 0.1.177 of the memory line it was).
        for text in ("the api returns 500", "add pagination to the api", "an api for the reports",
                     "rate limits in the api", "la api devuelve 500", "update api.js", "apiary notes",
                     "read `api` first"):
            self.assertFalse(cue("api", text), text)

    def test_cues_people_write_and_words_that_are_not_cues(self):
        names = {"api", "billing", "docs"}
        for name, text in (("api", "do it like we did in the api"), ("api", "como hicimos en el api"),
                           ("api", "use the conventions of api"), ("api", "in the api directory there is a helper"),
                           ("api", "en el directorio api hay un helper"),
                           ("api", "copy the retry helper from the api service"),
                           ("billing", "igual que en la carpeta de billing"),
                           ("billing", "el proyecto de billing ya lo resuelve"),
                           ("billing", "mirá cómo lo hace billing"),
                           ("api", "look at ~/api for the pattern"), ("api", "as in api's repo")):
            self.assertEqual(control.named_projects(names, text), [name], text)
            self.assertTrue(control.has_cue(name, text), text)
        for name, text in (("api", "fix the timeout in api calls"), ("billing", "errors from billing data are wrong"),
                           ("billing", "en billing hay un error de redondeo"),
                           ("api", "the `api` key in config is missing"), ("billing", 'rename the "billing" column'),
                           ("billing", "the billing app crashes on login"), ("docs", "the docs folder is stale")):
            self.assertFalse(control.has_cue(name, text), text)

    def test_a_name_at_the_end_of_a_phrase_is_a_cue_only_when_it_refers_to_the_project(self):
        # Phrase-final plain uses: the name used as a word, after a preposition.
        for name, text in (("billing", "this endpoint is only used for billing."),
                           ("billing", "necesito un reporte para billing"), ("billing", "es un tema de billing."),
                           ("billing", "fix the rounding error in billing"), ("api", "add retries for api."),
                           ("docs", "update the table of docs"), ("docs", "move it into docs"),
                           ("api", "there is a bug in api, I think"), ("billing", "the invoice goes out from billing"),
                           ("docs", "what is the format of docs?"), ("api", "errors come from the api service"),
                           ("billing", "in the billing module the totals are wrong"), ("docs", "write it up for docs"),
                           ("api", "how api does it is unclear"), ("billing", "that is the job of billing")):
            self.assertFalse(control.has_cue(name, text), text)
        # References written the same way, which stay cues.
        for name, text in (("billing", "the same as billing does"),
                           ("api", "see how we handle retries in the api repo"), ("billing", "like in billing"),
                           ("api", "tal como en api"), ("billing", "copiá el helper desde billing"),
                           ("api", "check ../api/handlers.py"), ("billing", "the way billing's project does it"),
                           ("api", "borrow the linter config from our api")):
            self.assertTrue(control.has_cue(name, text), text)

    def test_a_multiword_name_takes_its_cues_too(self):
        self.assertTrue(control.has_cue("heat-v2", "as we did in heat v2"))
        self.assertTrue(control.has_cue("heat-v2", "look at ~/heat-v2/app"))
        self.assertFalse(control.has_cue("heat-v2", "the heat v2 login"))


class CommonnessTest(HookCase):
    def setUp(self):
        super().setUp()
        # Ten pieces of other projects, four of which use the word "billing": a common word in this store.
        for i in range(10):
            words = "billing invoices" if i < 4 else "deploy steps"
            piece(f"other-{i}", f"Other thing {i}", f"when doing {words} number {i}", [f"proj{i % 3}"],
                  f"## #s\n**Do:** {words} carefully.\n")
        piece("bill-1", "Close the month", "closing the month", ["billing"])
        piece("heat-1", "Tune the pump", "tuning the pump", ["heat-v2"])
        piece("api-1", "Version the endpoints", "versioning the endpoints", ["api"])

    def test_commonness_comes_from_the_store_vocabulary(self):
        pieces = store.all_pieces()
        self.assertEqual(control.name_commonness("billing", pieces)["why"], "common")
        self.assertEqual(control.name_commonness("heat-v2", pieces)["why"], "distinctive")
        self.assertEqual(control.name_commonness("api", pieces)["why"], "short")
        # The project's own pieces do not make its name common.
        self.assertEqual(control.name_commonness("proj1", pieces)["why"], "distinctive")

    def test_select_needs_a_cue_only_for_an_ambiguous_name(self):
        pieces = store.all_pieces()
        _pool, why = control.select(pieces, None, "the billing totals look wrong", project="alpha")
        self.assertEqual((why["named"], why["ambiguous"]), ([], ["billing"]))
        _pool, why = control.select(pieces, None, "do it like we did in billing", project="alpha")
        self.assertEqual((why["named"], why["named_how"]), (["billing"], {"billing": "cue"}))
        pool, why = control.select(pieces, None, "the heat v2 pump is noisy", project="alpha")
        self.assertEqual((why["named"], why["named_how"]), (["heat-v2"], {"heat-v2": "distinctive"}))
        self.assertIn("heat-1", [p.id for p in pool])
        pool, why = control.select(pieces, None, "the api returns 500", project="alpha")
        self.assertEqual((why["named"], why["ambiguous"]), ([], ["api"]))
        self.assertNotIn("api-1", [p.id for p in pool])


class TinyStoreTest(HookCase):
    def test_on_a_small_store_a_longer_name_is_distinctive_and_a_short_one_still_needs_a_cue(self):
        # Two other pages: nothing is common in so small a store, so "billing" is named by the word (as before the
        # cue rule); a name of three letters or fewer needs a cue whatever the store.
        piece("other-1", "Close the month", "closing the billing month", ["ledger"])
        piece("bill-1", "Send the invoices", "sending the invoices", ["billing"])
        piece("api-1", "Version the endpoints", "versioning the endpoints", ["api"])
        pieces = store.all_pieces()
        self.assertEqual(control.name_commonness("billing", pieces)["why"], "distinctive")
        _pool, why = control.select(pieces, None, "the billing totals look wrong", project="alpha")
        self.assertEqual(why["named_how"], {"billing": "distinctive"})
        _pool, why = control.select(pieces, None, "the api returns 500", project="alpha")
        self.assertEqual((why["named"], why["ambiguous"]), ([], ["api"]))


class OfferedTest(HookCase):
    def setUp(self):
        super().setUp()
        piece("ship-release", "Ship a release with the checklist", "shipping a release of the app", ["alpha"], BODY)
        piece("api-version", "Version the endpoints", "versioning the endpoints of the service", ["api"], BODY)
        piece("api-auth", "Rotate the tokens", "rotating the service tokens", ["api"], BODY)
        self.ev = {"session_id": "n1", "cwd": str(self.alpha)}

    def ask(self, prompt, model):
        out = self.hook("prompt", {**self.ev, "prompt": prompt, "model": model})
        return out["hookSpecificOutput"]["additionalContext"] if out else ""

    def test_a_frontier_model_is_offered_one_line_and_the_pieces_stay_out(self):
        told = self.ask("the api versioning of the endpoints is off", "claude-opus-5-5")
        offer = [ln for ln in told.splitlines() if "may also mean the project" in ln]
        self.assertEqual(len(offer), 1)
        self.assertIn("`api`", offer[0])
        self.assertIn("2 ways of working", offer[0])
        self.assertNotIn("api-version", told)                     # its pieces are not listed or loaded
        r = events("route")[-1]
        self.assertEqual((r["named_projects"], r["named_how"], r["offered_projects"]), ([], {"api": "offered"},
                                                                                         ["api"]))
        self.assertNotIn("api-version", r["offered"] + r["chosen"])

    def test_an_apply_model_gets_nothing_and_the_mention_is_rejected(self):
        told = self.ask("the api versioning of the endpoints is off", "claude-haiku-5-5")
        self.assertNotIn("may also mean", told)
        r = events("route")[-1]
        self.assertEqual((r["named_how"], r["offered_projects"], r["chosen"]), ({"api": "rejected"}, [], []))

    def test_with_a_cue_the_project_is_named_as_before(self):
        self.ask("version the endpoints like we did in api", "claude-haiku-5-5")
        r = events("route")[-1]
        self.assertEqual((r["named_projects"], r["named_how"]), (["api"], {"api": "cue"}))
        self.assertEqual(r["chosen"], ["api-version"])

    def test_in_a_public_repository_nothing_is_offered_or_named(self):
        (self.alpha / ".athos.toml").write_text('public = true\n')
        told = self.ask("the api versioning of the endpoints is off", "claude-opus-5-5")
        self.assertNotIn("api", told.replace("athos", ""))
        r = events("route")[-1]
        self.assertNotIn("named_how", r)
        self.assertEqual(r["offered_projects"], [])
        self.assertEqual(r["named_how_count"], {"rejected": 1})

    def test_opening_a_piece_of_the_offered_project_is_not_an_unnamed_load(self):
        from athos import audit
        self.ask("the api versioning of the endpoints is off", "claude-opus-5-5")
        self.hook("tool", {**self.ev, "tool_name": "Bash", "tool_input": {"command": "athos show api-version"}})
        out = audit.run(session="n1")
        (rule,) = [r for s in out["sessions"] for r in s["rules"] if r["rule"] == "other_project_load"]
        self.assertEqual(rule["found"], [])
