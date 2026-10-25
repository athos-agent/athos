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
