from athos import load, session, store
from tests.helpers import TempHome


def seed():
    store.create("Cut a release of a Python package", "preparing a release: version bump, changelog, tag",
                 "1. Bump version in pyproject.\n2. Update CHANGELOG.\n3. Tag and push.")
    store.create("Fix a flaky test", "a test fails only sometimes in CI", "Run it 20 times; look for shared state.")
    store.create("Rotate an API key", "a credential leaked or expires", "Revoke first, then issue, then deploy.")


class LoadTest(TempHome):
    def test_index_lists_every_enabled_piece_briefly(self):
        seed()
        text = load.on_session_start({"session_id": "s1", "model": "claude-opus-5-5"})
        self.assertIn("`fix-a-flaky-test`", text)
        self.assertNotIn("shared state", text)                       # bodies are not in the index
        self.assertEqual(session.load("s1")["model"], "claude-opus-5-5")

    def test_index_is_empty_without_pieces(self):
        self.assertEqual(load.on_session_start({"session_id": "s1"}), "")

    def test_only_the_matching_piece_is_injected(self):
        seed()
        text = load.on_prompt({"session_id": "s1", "prompt": "the CI test is flaky again, it fails sometimes"})
        self.assertIn("Run it 20 times", text)
        self.assertNotIn("CHANGELOG", text)
        self.assertNotIn("Revoke first", text)
        self.assertEqual(session.load("s1")["loaded"], ["fix-a-flaky-test"])

    def test_unrelated_request_injects_nothing(self):
        seed()
        self.assertEqual(load.on_prompt({"session_id": "s1", "prompt": "write a haiku about autumn"}), "")
        self.assertNotIn("loaded", session.load("s1"))

    def test_spanish_request_matches(self):
        store.create("Preparar un release", "preparar un release: subir versión, changelog y tag", "Pasos.")
        self.assertIn("Preparar un release", load.on_prompt({"session_id": "s1",
                                                             "prompt": "hay que preparar el release nuevo"}))

    def test_injection_respects_the_cap(self):
        for i in range(5):
            store.create(f"Deploy service {i}", "deploy the service to production", "x" * 6000)
        found = load.relevant("deploy the service to production", store.all_pieces())
        self.assertEqual(len(found), 1)


class LoadRegressionTest(TempHome):
    def test_one_piece_matches_on_a_word_stem(self):
        # The first real session: one piece, a request sharing only "release" with it, which was not injected.
        store.create("Cut a versioned release of a small Python package", "asked to bump a version, update the "
                     "changelog, commit and tag", "Change both version places.")
        text = load.on_prompt({"session_id": "s1", "prompt": "Release 0.3.0 with a new option"})
        self.assertIn("Change both version places.", text)

    def test_mark_loaded_records_and_touches(self):
        p = store.create("A", "aaa", "b")
        load.mark_loaded("s1", [p.id])
        self.assertEqual(session.load("s1")["loaded"], ["a"])

    def test_a_shared_prefix_alone_does_not_load(self):
        # 2026-10-29: "revisá … con mi checklist" loaded a piece about CI checks, and "la carga de checklist" one whose
        # "when" quoted «Cargando tus casos»: words that only start alike.
        store.create("Check CI of the PRs, including stacked ones", "asked to review the CI checks of a PR",
                     "gh pr checks.")
        store.create("Audit the register of the texts", "a label sounds colloquial («Cargando tus casos»)", "x")
        for prompt in ("Revisá el contrato con mi checklist", "arregla lo de la carga de checklist"):
            self.assertEqual(load.relevant(prompt, store.all_pieces()), [], prompt)

    def test_one_generic_word_does_not_load(self):
        store.create("Plan the outreach in the Discord", "posting in the hackathon Discord", "x")
        store.create("Ship the feature PR", "a feature is ready to merge", "y")
        self.assertEqual(load.relevant("Plan the tiling for the room", store.all_pieces()), [])

    def test_the_best_piece_loads_even_over_the_cap(self):
        store.create("Rehearse the demo and time it", "rehearsing the demo", "z" * (load.INJECT_CAP + 2000))
        self.assertEqual(len(load.relevant("rehearse the demo and time it", store.all_pieces())), 1)

    def test_a_background_task_notice_loads_nothing(self):
        store.create("Change a function output", "change what a SQL function returns", "x")
        notice = "<task-notification>\n<task-id>b1</task-id>\n<summary>output changed</summary>"
        self.assertEqual(load.relevant(notice, store.all_pieces()), [])

    def test_file_names_and_punctuation_split_into_words(self):
        # 2026-10-29: "Revisá contrato-servicios.md, represento al Proveedor." loaded nothing: the file name was one word.
        store.create("Revisar un contrato con tu checklist", "revisar un contrato de servicios o de locación", "x")
        self.assertEqual(len(load.relevant("Revisá contrato-servicios.md, represento al Proveedor.",
                                           store.all_pieces())), 1)


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
