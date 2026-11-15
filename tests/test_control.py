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
        control.profile_add([GENERAL_PAGE])                                # what applies in every project

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

    def test_a_folder_no_piece_belongs_to_sees_only_the_profile(self):
        self.assertEqual(self.loaded(self.folder("elsewhere")), [GENERAL_PAGE])
        self.assertEqual(control.select(store.all_pieces(), self.folder("elsewhere"))[1]["reason"],
                         "auto:no-own-pieces")
        # Naming a project from there still lets its pages through, and `athos load all` brings everything back.
        self.assertEqual(self.loaded(self.folder("elsewhere"), "release the site"), [SITE_PAGE, GENERAL_PAGE])
        self.choose("all")
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

    def test_the_auto_mode_is_described_in_spanish(self):
        self.assertIn("las de este proyecto", control.describe({"mode": "auto"}, lang="es"))
        self.assertIn("this project's pieces", control.describe({"mode": "auto"}))

    def test_the_choice_is_saved_and_described(self):
        saved = self.choose("project", "site")
        self.assertEqual(saved, control.get())
        self.assertEqual(control.describe(), f"project {saved['project']}")  # read back from disk
        self.assertEqual(control.describe({"mode": "pieces", "pieces": ["a", "b"]}), "pieces a, b")
        self.assertEqual(control.describe({"mode": "all"}), "all")

    def test_the_session_index_only_counts_other_projects(self):
        athos = self.folder("athos")
        text = load.on_session_start({"session_id": "s", "cwd": athos})
        self.assertIn("`release-athos`", text)
        self.assertNotIn("`release-site`", text)                       # its page doesn't mix in
        self.assertIn("- 1 way of working in 1 other project", text)       # counted, never named
        self.assertNotIn("Release site", text)
        self.assertNotIn("site (", text)

    def test_harness_messages_are_not_requests(self):
        self.assertEqual(load.relevant("<agent-message from=\"x\"> release athos", load.enabled()), [])


class NamedProjectsTest(TempHome):
    """Which projects a request names: the longest name wins over one it contains, and a short name counts only as
    a word of its own."""

    def test_names(self):
        named = control.named_projects
        self.assertEqual(named(["heat", "heat-v2"], "fix the heat-v2 login"), ["heat-v2"])
        self.assertEqual(named(["heat"], "fix the heat-v2 login"), [])
        self.assertEqual(named(["heat"], "the heat pump, as in heat: again"), ["heat"])
        self.assertEqual(named(["api"], "update api.js and api-docs"), [])
        self.assertEqual(named(["api", "billing"], "billing api"), ["api", "billing"])
        self.assertEqual(named(["my-app"], "like in my app please"), ["my-app"])
        self.assertEqual(named(["heat-v2", "heat-v2-mobile"], "heat v2 mobile crash"), ["heat-v2-mobile"])
        self.assertTrue(control._named("billing", "the billing report"))
        self.assertFalse(control._named("heat", "heat-v2"))

    def test_defined_once(self):
        import inspect
        self.assertEqual(inspect.getsource(control).count("def _named("), 1)

    def test_the_scope_uses_them(self):
        for pid, project in (("h1", "heat"), ("h2", "heat-v2"), ("a1", "alpha")):
            store._write(store.Piece(id=pid, title=f"{project} thing", when=f"{project} work", body="b",
                                     projects=[project], created="2026-11-01", last_used="2026-11-01",
                                     origin={"platform": "t", "model": "t"}))
        pool, why = control.select(store.all_pieces(), None, "the heat-v2 login", project="alpha")
        self.assertEqual(why["named"], ["heat-v2"])
