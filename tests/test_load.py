from athos import load, session, store
from tests.helpers import TempHome

RELEASE_STEPS = "1. Bump version in pyproject.\n2. Update CHANGELOG.\n3. Tag and push."
FLAKY_STEPS = "Run it 20 times; look for shared state."
KEY_STEPS = "Revoke first, then issue, then deploy."


def three_pages() -> None:
    """A small store: releasing, a flaky test, a leaked key."""
    store.create("Cut a release of a Python package", "preparing a release: version bump, changelog, tag",
                 RELEASE_STEPS)
    store.create("Fix a flaky test", "a test fails only sometimes in CI", FLAKY_STEPS)
    store.create("Rotate an API key", "a credential leaked or expires", KEY_STEPS)


def ask(prompt: str, sid: str = "s1") -> str:
    return load.on_prompt({"session_id": sid, "prompt": prompt})


def picked(prompt: str) -> list[str]:
    return [piece.id for piece in load.relevant(prompt, store.all_pieces())]


class SessionStartAndPrompt(TempHome):
    def test_the_catalogue_names_each_page_but_not_its_body(self):
        three_pages()
        catalogue = load.on_session_start({"session_id": "s1", "model": "claude-opus-5-5"})
        self.assertIn("`fix-a-flaky-test`", catalogue)
        self.assertNotIn("shared state", catalogue)
        self.assertEqual(session.load("s1")["model"], "claude-opus-5-5")

    def test_a_model_given_as_an_object_is_recorded_by_id(self):
        load.on_session_start({"session_id": "s2", "model": {"id": "muse-spark", "display_name": "Muse Spark"}})
        self.assertEqual(session.load("s2")["model"], "muse-spark")

    def test_an_empty_store_says_nothing_at_session_start(self):
        self.assertEqual(load.on_session_start({"session_id": "s1"}), "")

    def test_a_request_gets_only_the_page_that_fits(self):
        three_pages()
        added = ask("the CI test is flaky again, it fails sometimes")
        self.assertIn(FLAKY_STEPS[:16], added)
        for other in ("CHANGELOG", KEY_STEPS[:12]):
            self.assertNotIn(other, added)
        self.assertEqual(session.load("s1")["loaded"], ["fix-a-flaky-test"])

    def test_an_unrelated_request_adds_nothing_and_records_nothing(self):
        three_pages()
        self.assertEqual(ask("write a haiku about autumn"), "")
        self.assertNotIn("loaded", session.load("s1"))

    def test_a_request_in_spanish_finds_a_spanish_page(self):
        store.create("Preparar un release", "preparar un release: subir versión, changelog y tag", "Pasos.")
        self.assertIn("Preparar un release", ask("hay que preparar el release nuevo"))

    def test_a_second_large_page_does_not_fit_the_budget(self):
        for n in range(5):
            store.create(f"Deploy service {n}", "deploy the service to production", "x" * 6000)
        self.assertEqual(len(picked("deploy the service to production")), 1)

    def test_the_catalogue_stops_at_its_cap_and_says_how_many_are_left(self):
        for n in range(80):
            store.create(f"Page number {n} with a fairly long title", "when something long enough happens " * 3, "x")
        catalogue = load.index_text(store.all_pieces())
        self.assertLessEqual(len(catalogue), load.INDEX_CAP + 60)
        self.assertRegex(catalogue, r"- … and \d+ more \(`athos list`\)$")


class RoutingRegressions(TempHome):
    def test_a_word_stem_is_enough_for_a_lone_page(self):
        # The first real session: one page, and a request sharing only "release" with it went without it.
        store.create("Cut a versioned release of a small Python package", "asked to bump a version, update the "
                     "changelog, commit and tag", "Change both version places.")
        self.assertIn("Change both version places.", ask("Release 0.3.0 with a new option"))

    def test_marking_a_page_loaded_records_it_in_the_session(self):
        page = store.create("A", "aaa", "b")
        load.mark_loaded("s1", [page.id])
        load.mark_loaded("s1", [])                                         # nothing to add: no change
        self.assertEqual(session.load("s1")["loaded"], ["a"])

    def test_words_that_only_start_alike_do_not_load(self):
        # 2026-10-29: "revisá … con mi checklist" brought a page about CI checks, and "la carga de checklist" one whose
        # "when" quoted «Cargando tus casos».
        store.create("Check CI of the PRs, including stacked ones", "asked to review the CI checks of a PR",
                     "gh pr checks.")
        store.create("Audit the register of the texts", "a label sounds colloquial («Cargando tus casos»)", "x")
        for prompt in ("Revisá el contrato con mi checklist", "arregla lo de la carga de checklist"):
            with self.subTest(prompt=prompt):
                self.assertEqual(picked(prompt), [])

    def test_a_single_common_word_does_not_load(self):
        store.create("Plan the outreach in the Discord", "posting in the hackathon Discord", "x")
        store.create("Ship the feature PR", "a feature is ready to merge", "y")
        self.assertEqual(picked("Plan the tiling for the room"), [])

    def test_the_best_page_comes_whole_even_past_the_budget(self):
        store.create("Rehearse the demo and time it", "rehearsing the demo", "z" * (load.INJECT_CAP + 2000))
        self.assertEqual(len(picked("rehearse the demo and time it")), 1)

    def test_harness_notices_are_not_requests(self):
        store.create("Change a function output", "change what a SQL function returns", "x")
        self.assertEqual(picked("<task-notification>\n<task-id>b1</task-id>\n<summary>output changed</summary>"), [])

    def test_file_names_and_punctuation_break_into_words(self):
        # 2026-10-29: "Revisá contrato-servicios.md, represento al Proveedor." found nothing: the file name was one word.
        store.create("Revisar un contrato con tu checklist", "revisar un contrato de servicios o de locación", "x")
        self.assertEqual(len(picked("Revisá contrato-servicios.md, represento al Proveedor.")), 1)


class Misfires(TempHome):
    def test_a_dismissed_load_does_not_come_back_on_the_same_words(self):
        p = store.create("Read Muse Code session logs", "reading Muse Code's session logs after a run", "Do it.",
                         piece_id="muse-logs")
        q = "how is athos doing in this session? muse session logs look odd"
        self.assertEqual([x.id for x in load.relevant(q, [p])], ["muse-logs"])
        self.assertEqual(load.why(q, p), ["logs", "muse", "session"])
        load.dismiss("muse-logs", load.why(q, p))
        self.assertEqual(load.relevant(q, [p]), [])                        # the same words: not again
        self.assertEqual(load.relevant("read the muse code session logs and the run output", [p])[0].id, "muse-logs")

    def test_the_prompt_hook_remembers_why_each_piece_loaded(self):
        store.create("Read Muse Code session logs", "reading Muse Code's session logs after a run", "Do it.",
                     piece_id="muse-logs")
        load.on_prompt({"session_id": "s1", "prompt": "read the muse session logs"})
        self.assertEqual(session.load("s1")["task_why"], {"muse-logs": ["logs", "muse", "read", "session"]})

    def test_inflected_words_count_as_the_same_word(self):
        store.create("Verify a source before publishing", "a source gives information for a story (a document, a "
                     "quote, a tip) and it must be checked before it is published", "x", piece_id="verify")
        store.create("Review a contract against your checklist", "reviewing a contract or lease", "y",
                     piece_id="contract")
        ids = [p.id for p in load.relevant("We got a tip about the water plant contract. Can we publish it?",
                                           store.all_pieces())]
        self.assertEqual(ids[0], "verify")
        self.assertEqual(load._plain("published"), "publish")
        self.assertEqual(load._plain("publicado"), "public")
        self.assertEqual(load._plain("tip"), "tip")
