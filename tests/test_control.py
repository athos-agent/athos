from pathlib import Path

from athos import control, load, store
from tests.helpers import TempHome

ATHOS_PAGE, SITE_PAGE, GENERAL_PAGE = "release-athos", "release-site", "write-commit-messages"


class ControlTest(TempHome):
    """Loading modes, seen through what `load` ends up offering."""

    def setUp(self):
        super().setUp()
        # Two project-tagged pages and one general page with no project.
        for title, when, body, projects in (
            ("Release athos", "release athos", "a", ["athos"]),
            ("Release site", "release the site", "b", ["site"]),
            ("Write commit messages", "writing a commit message", "c", None),
        ):
            store.create(title, when, body, projects=projects)

    def folder(self, name: str) -> str:
        path = Path(self.home) / name
        path.mkdir(exist_ok=True)
        return str(path)

    def choose(self, mode: str, *values: str) -> dict:
        return control.set_selection(mode, list(values))

    def loaded(self, cwd: str | None = None, prompt: str = "") -> list[str]:
        return sorted(piece.id for piece in load.enabled(cwd, prompt))

    def test_default_is_auto_and_without_a_folder_every_piece_loads(self):
        self.assertEqual(control.get(), {"mode": "auto"})
        self.assertEqual(len(self.loaded()), 3)                          # Claude Desktop's chat has no folder

    def test_auto_keeps_each_project_apart(self):
        athos = self.folder("athos")
        self.assertEqual(self.loaded(athos), [ATHOS_PAGE, GENERAL_PAGE])
        # Naming the other project in the request lets its page through.
        self.assertEqual(self.loaded(athos, "how do we release the site?"), [ATHOS_PAGE, SITE_PAGE, GENERAL_PAGE])
        self.assertNotIn("Release site", load.on_prompt({"session_id": "s", "cwd": athos,
                                                          "prompt": "release a new version"}))

    def test_a_folder_no_piece_belongs_to_sees_every_piece(self):
        self.assertEqual(len(self.loaded(self.folder("elsewhere"))), 3)

    def test_project_mode_keeps_that_project_and_the_general_pages(self):
        self.choose("project", "athos")
        self.assertEqual(self.loaded(), [ATHOS_PAGE, GENERAL_PAGE])

    def test_pieces_mode_offers_only_the_listed_pages(self):
        control.set_selection("pieces", [SITE_PAGE])
        self.assertEqual(self.loaded(), [SITE_PAGE])
        offered = load.on_prompt({"session_id": "s", "prompt": "release the site"})
        self.assertIn("Release site", offered)
        withheld = load.on_prompt({"session_id": "s", "prompt": "release athos"})
        self.assertNotIn("Release athos", withheld)

    def test_an_unknown_or_empty_piece_list_is_refused_and_nothing_is_saved(self):
        for bad in (["nope"], []):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                control.set_selection("pieces", bad)
        self.assertEqual(control.get(), {"mode": "auto"})

    def test_an_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            control.set_selection("everything")

    def test_none_mode_makes_session_start_silent(self):
        self.choose("none")
        self.assertEqual(load.on_session_start({"session_id": "quiet"}), "")
        self.assertEqual(self.loaded(), [])

    def test_the_choice_is_saved_and_described(self):
        saved = self.choose("project", "site")
        self.assertEqual(saved, control.get())
        self.assertEqual(control.describe(), f"project {saved['project']}")  # read back from disk
        self.assertEqual(control.describe({"mode": "pieces", "pieces": ["a", "b"]}), "pieces a, b")
        self.assertEqual(control.describe({"mode": "all"}), "all")

    def test_the_session_index_lists_other_projects_in_one_line_each(self):
        athos = self.folder("athos")
        text = load.on_session_start({"session_id": "s", "cwd": athos})
        self.assertIn("`release-athos`", text)
        self.assertNotIn("`release-site`", text)                       # its page doesn't mix in
        self.assertIn("- site (1 way of working): e.g. «Release site»", text)
        (Path(self.home) / "projects").mkdir()
        (Path(self.home) / "projects" / "site.md").write_text("# site\nThe marketing site: releases and copy.\n")
        self.assertIn("- site (1 way of working): The marketing site: releases and copy.",
                      load.on_session_start({"session_id": "s", "cwd": athos}))

    def test_harness_messages_are_not_requests(self):
        self.assertEqual(load.relevant("<agent-message from=\"x\"> release athos", load.enabled()), [])
