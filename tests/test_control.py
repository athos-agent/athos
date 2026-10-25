from athos import control, load, store
from tests.helpers import TempHome


class ControlTest(TempHome):
    def setUp(self):
        super().setUp()
        store.create("Release athos", "release athos", "a", projects=["athos"])
        store.create("Release site", "release the site", "b", projects=["site"])
        store.create("Write commit messages", "writing a commit message", "c")

    def ids(self):
        return sorted(p.id for p in load.enabled())

    def test_default_is_all(self):
        self.assertEqual(control.get(), {"mode": "all"})
        self.assertEqual(len(self.ids()), 3)

    def test_project_keeps_its_pieces_and_untagged_ones(self):
        control.set_selection("project", ["athos"])
        self.assertEqual(self.ids(), ["release-athos", "write-commit-messages"])

    def test_pieces_selection(self):
        control.set_selection("pieces", ["release-site"])
        self.assertEqual(self.ids(), ["release-site"])
        self.assertIn("Release site", load.on_prompt({"session_id": "s", "prompt": "release the site"}))
        self.assertEqual(load.on_prompt({"session_id": "s", "prompt": "release athos"}), "")

    def test_unknown_piece_is_refused(self):
        with self.assertRaises(ValueError):
            control.set_selection("pieces", ["nope"])
        self.assertEqual(control.get(), {"mode": "all"})

    def test_none_silences_athos(self):
        control.set_selection("none")
        self.assertEqual(load.on_session_start({"session_id": "s"}), "")

    def test_choice_persists(self):
        control.set_selection("project", ["site"])
        self.assertEqual(control.describe(), "project site")
