from pathlib import Path

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

    def test_default_is_auto_and_without_a_folder_every_piece_loads(self):
        self.assertEqual(control.get(), {"mode": "auto"})
        self.assertEqual(len(self.ids()), 3)                            # Claude Desktop's chat has no folder

    def test_auto_keeps_each_project_apart(self):
        athos = Path(self.home) / "athos"
        athos.mkdir()
        here = sorted(p.id for p in load.enabled(str(athos)))
        self.assertEqual(here, ["release-athos", "write-commit-messages"])
        # Another project's pieces come only when the request names that project.
        named = sorted(p.id for p in load.enabled(str(athos), "how do we release the site?"))
        self.assertEqual(named, ["release-athos", "release-site", "write-commit-messages"])
        self.assertNotIn("Release site", load.on_prompt({"session_id": "s", "cwd": str(athos),
                                                          "prompt": "release a new version"}))

    def test_a_folder_no_piece_belongs_to_sees_every_piece(self):
        other = Path(self.home) / "elsewhere"
        other.mkdir()
        self.assertEqual(len(load.enabled(str(other))), 3)

    def test_project_keeps_its_pieces_and_untagged_ones(self):
        control.set_selection("project", ["athos"])
        self.assertEqual(self.ids(), ["release-athos", "write-commit-messages"])

    def test_pieces_selection(self):
        control.set_selection("pieces", ["release-site"])
        self.assertEqual(self.ids(), ["release-site"])
        self.assertIn("Release site", load.on_prompt({"session_id": "s", "prompt": "release the site"}))
        self.assertNotIn("Release athos", load.on_prompt({"session_id": "s", "prompt": "release athos"}))

    def test_unknown_piece_is_refused(self):
        with self.assertRaises(ValueError):
            control.set_selection("pieces", ["nope"])
        self.assertEqual(control.get(), {"mode": "auto"})

    def test_none_silences_athos(self):
        control.set_selection("none")
        self.assertEqual(load.on_session_start({"session_id": "s"}), "")

    def test_choice_persists(self):
        control.set_selection("project", ["site"])
        self.assertEqual(control.describe(), "project site")

    def test_the_session_index_lists_other_projects_in_one_line_each(self):
        athos = Path(self.home) / "athos"
        athos.mkdir()
        text = load.on_session_start({"session_id": "s", "cwd": str(athos)})
        self.assertIn("`release-athos`", text)
        self.assertNotIn("`release-site`", text)                       # its page doesn't mix in
        self.assertIn("- site (1 way of working): e.g. «Release site»", text)
        (Path(self.home) / "projects").mkdir()
        (Path(self.home) / "projects" / "site.md").write_text("# site\nThe marketing site: releases and copy.\n")
        self.assertIn("- site (1 way of working): The marketing site: releases and copy.",
                      load.on_session_start({"session_id": "s", "cwd": str(athos)}))

    def test_harness_messages_are_not_requests(self):
        self.assertEqual(load.relevant("<agent-message from=\"x\"> release athos", load.enabled()), [])
