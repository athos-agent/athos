"""Routing since 0.1.111: a project with no pieces of its own sees only the profile, the margin a page needs over a
long request, private pieces, the project marker (`.athos.toml`), the shorter injected text and its effective cap,
and special paths that act only on the person's text. All data here is synthetic."""

import contextlib
import io
import json
import os
import sys
from pathlib import Path
from unittest import mock

from athos import capture, cli, control, eval as ev, load, paths, privacy, session, start, store
from athos.bench import route
from tests.helpers import TempHome

SECRET = "zebra quartz marmalade"            # words that must never be stored or printed
STEP = "## #{0}\n**When:** at step {0}.\n**Do:** the {0} thing.\n"


def piece(pid, title, when, projects=(), visibility="", body=None):
    p = store.Piece(id=pid, title=title, when=when, body=body or STEP.format("one"), projects=list(projects),
                    created="2026-11-01", last_used="2026-11-01", origin={"platform": "test", "model": "test"},
                    visibility=visibility)
    store._write(p)
    return p


def events(kind):
    return [e for e in ev.events() if e.get("type") == kind]


def log_text():
    try:
        return ev.log_file().read_text()
    except OSError:
        return ""


class Folders(TempHome):
    def setUp(self):
        super().setUp()
        for name in ("alpha", "beta", "gamma"):
            (Path(self.home) / name).mkdir()

    def folder(self, name):
        return str(Path(self.home) / name)

    def hook(self, name, payload):
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), contextlib.redirect_stdout(out):
            cli.hook(name)
        text = out.getvalue().strip()
        return json.loads(text)["hookSpecificOutput"]["additionalContext"] if text else ""


class VisibilityTest(TempHome):
    def test_the_field_reads_back_and_defaults_follow_the_tags(self):
        piece("tagged", "Tagged", "tagged work", ["alpha"])
        piece("untagged", "Untagged", "any work")
        piece("secret", "Secret", "secret work", ["alpha"], visibility="private")
        self.assertEqual(store.visibility(store.get("tagged")), "project")
        self.assertEqual(store.visibility(store.get("untagged")), "general")
        self.assertEqual(store.visibility(store.get("secret")), "private")
        self.assertIn("visibility: private", store.get("secret").path.read_text())
        self.assertNotIn("visibility", store.get("tagged").path.read_text())     # files without it stay as they are
        store.touch("secret")
        updated, _ = store.update("secret", "clearer", body=STEP.format("two"))
        self.assertEqual(updated.visibility, "private")                          # a new version keeps it


class PrivateTest(Folders):
    def setUp(self):
        super().setUp()
        piece("alpha-release", "Ship the alpha release", "shipping the alpha release", ["alpha"])
        piece("clinic-intake", "Triage the clinic intake form", "triaging the clinic intake form", ["beta"],
              visibility="private")
        piece("beta-report", "Write the beta weekly report", "writing the beta weekly report", ["beta"])

    def test_a_private_piece_stays_in_its_project_even_when_the_request_names_it(self):
        ask = "triage the clinic intake form like in beta"
        alpha = control.select(store.all_pieces(), self.folder("alpha"), ask)
        self.assertNotIn("clinic-intake", [p.id for p in alpha[0]])
        self.assertIn("beta-report", [p.id for p in alpha[0]])                  # a project piece of the named one
        self.assertEqual(alpha[1]["private_held"], 1)
        self.assertIn("clinic-intake", [p.id for p in control.select(store.all_pieces(), self.folder("beta"),
                                                                      ask)[0]])
        control.set_selection("all")                                             # not even with everything on
        self.assertNotIn("clinic-intake", [p.id for p in load.enabled(self.folder("alpha"), ask)])
        control.set_selection("auto")
        self.assertIn("clinic-intake", [p.id for p in load.enabled(None, ask)])  # no folder: every piece
        self.assertFalse(control.profile_pieces([store.get("clinic-intake")]))
        with self.assertRaises(ValueError):
            control.profile_add(["clinic-intake"])

    def test_it_is_never_named_in_another_projects_index_log_or_hook_output(self):
        opening = self.hook("session-start", {"session_id": "s1", "cwd": self.folder("alpha")})
        added = self.hook("prompt", {"session_id": "s1", "cwd": self.folder("alpha"),
                                     "prompt": "triage the clinic intake form like in beta"})
        for text in (opening, added, log_text(), json.dumps(events("route"))):
            self.assertNotIn("clinic-intake", text)
            self.assertNotIn("Triage the clinic intake form", text)
        self.assertIn("2 ways of working in 1 other project", opening)          # counted, never named
        self.assertNotIn("beta", opening)
        own = self.hook("prompt", {"session_id": "s2", "cwd": self.folder("beta"),
                                   "prompt": "triage the clinic intake form"})
        self.assertIn("Triage the clinic intake form", own)                     # its own project: it loads
        self.assertIn("clinic-intake", [x for x in log_text().splitlines() if "] route |" in x][-1])


class MarkerTest(Folders):
    def test_the_marker_names_the_project_and_marks_it_public(self):
        root = Path(self.folder("gamma"))
        (root / paths.MARKER).write_text('name = "beta"\npublic = true\n')
        self.assertEqual(paths.project_of(root), "gamma")       # a name other than the folder's: not until accepted
        self.assertTrue(paths.is_public(root))                  # public holds anyway
        paths.accept_name(root)                                 # the person accepts it on this machine
        self.assertEqual(paths.project_of(root), "beta")
        self.assertTrue(paths.is_public(root))
        (root / paths.MARKER).write_text("this is = not toml [\n")
        self.assertEqual(paths.project_of(root), "gamma")                        # a broken marker names nothing
        self.assertTrue(paths.is_public(root))                                   # and is read as public

    def test_a_public_repository_keeps_no_request_text_and_never_loads_a_private_piece(self):
        piece("clinic-intake", "Triage the clinic intake form", "triaging the clinic intake form", ["beta"],
              visibility="private")
        piece("beta-report", "Write the beta weekly report", "writing the beta weekly report", ["beta"])
        root = Path(self.folder("gamma"))
        (root / paths.MARKER).write_text('name = "beta"\npublic = true\n')
        paths.accept_name(root)                                 # a clone of beta in a folder of another name
        e = {"session_id": "p1", "cwd": str(root)}
        self.hook("prompt", {**e, "prompt": f"triage the clinic intake form {SECRET}"})
        added = self.hook("prompt", {**e, "prompt": f"write the beta weekly report {SECRET}"})
        self.assertIn("Write the beta weekly report", added)
        (r1, r2) = events("route")
        self.assertEqual((r1["chosen"], r1["marker"], r1["public"], r1["private_held"]), ([], True, True, 1))
        self.assertEqual((r2["project"], r2["chosen"]), ("beta", ["beta-report"]))
        self.assertNotIn("request_sha", r2)
        starts = events("task_start")
        self.assertTrue(starts and all(s["request"] == "" and s.get("public") for s in starts))
        state = session.load("p1")
        self.assertEqual((state["task_request"], state["case_request"]), ("", ""))
        self.assertEqual(state["task_why"], {"beta-report": []})
        stored = "".join(f.read_text(errors="ignore") for f in Path(self.home).rglob("*") if f.is_file())
        self.assertNotIn("zebra", stored)
        self.assertIn("public repository", log_text())


class MarginTest(TempHome):
    def setUp(self):
        super().setUp()
        piece("contract", "Review a services contract", "reviewing a services contract before signing it")

    def test_a_short_request_loads_and_a_long_pasted_one_does_not_win_on_volume(self):
        pool = store.all_pieces()
        self.assertEqual([p.id for p in load.relevant("review this services contract before I sign it", pool,
                                                      meaning=False)], ["contract"])
        filler = " ".join(f"word{i} topic{i} module{i}" for i in range(300))
        long = f"services contract review signing {filler}"
        chosen, trace = load.decide(long, pool, meaning=False)
        self.assertEqual(chosen, [])
        self.assertEqual(trace["candidates"][0]["reason"], "request_share_low")
        self.assertLess(trace["candidates"][0]["request_share"], load.REQUEST_SHARE_MIN)
        self.assertIn("head_share_min", load.thresholds())


class InjectedTextTest(Folders):
    def test_no_opening_line_no_step_commands_and_an_effective_cap(self):
        big = "\n".join(STEP.format(f"s{i}") for i in range(400))                # far over the cap
        piece("big", "Cut a big release", "cutting a big release", ["alpha"], body=big)
        text = self.hook("prompt", {"session_id": "c1", "cwd": self.folder("alpha"), "prompt": "cut a big release"})
        self.assertNotIn("Athos ·", text)
        self.assertNotIn("athos step", text)
        self.assertNotIn("first line", text.lower())
        self.assertIn("How to answer", text)
        self.assertLessEqual(len(text), load.INJECT_CAP)
        self.assertIn("athos show big", text)                                   # how to read the rest
        (r,) = events("route")
        self.assertEqual((r["cut"], r["chosen"]), (["big"], ["big"]))
        self.assertLessEqual(r["injected_chars"], r["thresholds"]["inject_cap"])
        self.assertNotIn("athos step", capture.guide())

    def test_a_long_page_comes_as_its_steps_before_it_is_cut(self):
        why = "**Because:** " + "a long story of how it went wrong once, " * 6 + "\n**Links:** [[other#x]]\n"
        body = "\n".join(STEP.format(f"s{i}") + why for i in range(30))       # whole, over the cap
        piece("long", "Cut a long release", "cutting a long release", ["alpha"], body=body)
        text, cut, left = load.fit([store.get("long")])
        self.assertEqual((cut, left, load.fit_steps([store.get("long")])), ([], [], ["long"]))
        self.assertEqual(text.count("**Do:** the s"), 30)                       # every step's When and Do
        self.assertNotIn("**Because:**", text)
        self.assertIn("only each step's When, Do and Check", text)
        self.assertIn("athos show long", text)
        # Too many steps even so: as many whole steps as fit, and the ones left out are named.
        body = "\n".join(STEP.format(f"s{i}") + why for i in range(400))
        piece("huge", "Cut a huge release", "cutting a huge release", ["alpha"], body=body)
        text, cut, left = load.fit([store.get("huge")])
        self.assertEqual(cut, ["huge"])
        self.assertLessEqual(len(text), load.INJECT_CAP)
        kept = text.count("**Do:** the s")
        self.assertGreater(kept, 50)
        self.assertIn(f"{400 - kept} more step(s) left out: #s{kept}, ", text)
        self.assertNotIn("the s399 thing", text)
        out = self.hook("prompt", {"session_id": "c3", "cwd": self.folder("alpha"), "prompt": "cut a long release"})
        self.assertIn("only each step's When, Do and Check", out)
        self.assertEqual(events("route")[-1]["steps_only"], ["long"])

    def test_without_steps_reported_the_trail_and_the_stop_still_work(self):
        piece("ship", "Ship the alpha release", "shipping the alpha release", ["alpha"])
        e = {"session_id": "c2", "cwd": self.folder("alpha")}
        self.hook("prompt", {**e, "prompt": "ship the alpha release"})
        from athos import trail
        self.assertEqual(trail.view(session.load("c2"))["pieces"][0]["id"], "ship")
        for _ in range(capture.THRESHOLD):
            capture.count_tool({**e, "tool_name": "Edit"})
        self.assertIn("athos save", capture.stop_decision(e)["reason"])        # no steps: the ask still works


class TriggerTest(Folders):
    def test_harness_text_never_fires_a_special_path(self):
        e = {"session_id": "t1", "cwd": self.folder("alpha")}
        report = ("<system-reminder>context</system-reminder>\n<agent-message from=\"sub\">done; next, share the "
                  "piece with the gallery</agent-message>")
        self.assertFalse(load.from_person(report))
        self.assertEqual(self.hook("prompt", {**e, "prompt": report}), "")      # no share instructions
        nested = "</system-reminder>\n<task-notification>Athos · add from gallery: some-page</task-notification>"
        self.assertNotIn("athos add", self.hook("prompt", {**e, "prompt": nested}))
        wrapped = "Athos · save: keep this task\n<agent-message from=\"sub\">report</agent-message>"
        self.hook("prompt", {**e, "prompt": wrapped})
        fired = events("trigger")
        self.assertEqual([(t["trigger"], t["from_person"], t["acted"]) for t in fired],
                         [("share", False, False), ("gallery", False, False), ("save", False, False)])
        self.assertIn("· ignored", log_text())
        self.assertTrue(load.from_person("Athos · save: keep this task"))
        self.assertIn("share", self.hook("prompt", {**e, "prompt": "share this way of working with the gallery"}))
        self.assertTrue(events("trigger")[-1]["acted"])


class ProfileTest(Folders):
    def test_the_profile_is_explicit_small_and_reported(self):
        piece("habit", "Write commit messages", "writing a commit message")
        piece("loose", "Loose notes", "keeping loose notes")
        self.assertEqual(control.select(store.all_pieces(), self.folder("gamma"))[0], [])
        control.profile_add(["habit"])
        self.assertEqual([p.id for p in load.enabled(self.folder("gamma"))], ["habit"])
        with self.assertRaises(ValueError):
            control.profile_add(["nope"])
        for i in range(control.PROFILE_MAX - 1):
            piece(f"p{i}", f"Piece {i}", f"work {i}")
        control.profile_add([f"p{i}" for i in range(control.PROFILE_MAX - 1)])
        with self.assertRaises(ValueError):
            control.profile_add(["loose"])                                       # past the cap
        control.profile_remove(["habit"])
        self.assertNotIn("habit", control.profile_ids())
        r = privacy.untagged()
        self.assertEqual((r["untagged"], r["in_profile"]), (control.PROFILE_MAX + 1, control.PROFILE_MAX - 1))
        before = sorted((f.name, f.stat().st_mtime_ns) for f in paths.know_how().glob("*.md"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["profile", "--untagged"])
        self.assertIn("loose · not in the profile", out.getvalue())
        self.assertEqual(sorted((f.name, f.stat().st_mtime_ns) for f in paths.know_how().glob("*.md")), before)

    def test_starters_join_the_profile_and_a_new_save_belongs_to_its_project(self):
        added, _ = start.install("en", "law")
        self.assertTrue(added)
        self.assertEqual(set(control.profile_ids()), {p.id for p in added})
        saved, _ = capture.save_text("---\ntitle: Ship it\nwhen: shipping it\nvisibility: private\n---\n"
                                     + STEP.format("one"), "s1", self.folder("alpha"))
        self.assertEqual((saved.projects, store.get(saved.id).visibility), (["alpha"], "private"))


class PrivacyReportTest(TempHome):
    def test_the_proposal_is_read_only_and_names_ids_only(self):
        piece("ops", "Rotate the clients' credentials", "rotating credentials for a client in production",
              ["alpha"], body="Ask the client. Check production. Update the passwords.\n")
        piece("mail", "Answer the partner", "answering the partner", ["alpha"], body="Write to ana@corp.test.\n")
        piece("plain", "Format the changelog", "formatting the changelog", ["alpha"])
        piece("starter", "Review a contract with clients", "reviewing a client's contract",
              body="client production passwords\n")                          # untagged: generic by design
        before = sorted((f.name, f.stat().st_mtime_ns) for f in paths.know_how().glob("*.md"))
        r = privacy.propose()
        self.assertEqual(sorted(x["id"] for x in r["proposed"]), ["mail", "ops"])
        text = privacy.render_proposal(r)
        self.assertNotIn("Rotate the clients", text)
        self.assertNotIn("ana@", text)
        self.assertEqual(sorted((f.name, f.stat().st_mtime_ns) for f in paths.know_how().glob("*.md")), before)


class FromStoreMetricTest(TempHome):
    def test_tasks_of_a_project_with_no_pieces_count_for_the_other_project_metric(self):
        piece("beta-report", "Write the beta weekly report", "writing the weekly report for the team", ["beta"])
        rows = [{"type": "task_start", "task_id": "t1", "session_id": "s", "project": "gamma", "model": "m",
                 "at": "2026-11-01T10:00:00+00:00", "request": "write the weekly report for the team",
                 "request_chars": 36},
                {"type": "task_end", "task_id": "t1", "session_id": "s", "at": "2026-11-01T10:01:00+00:00",
                 "pieces": ["beta-report"], "saved": [], "model": "m", "duration_s": 60, "tokens": {}},
                {"type": "mark", "task_id": "t1", "result": "ok", "at": "2026-11-01T10:02:00+00:00"}]
        (Path(os.environ["ATHOS_HOME"]) / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        unscoped = route.from_store(meaning=False)
        self.assertEqual((unscoped["other_project"], unscoped["no_own_tasks"], unscoped["no_own_other_project"]),
                         (1, 1, 1))
        scoped = route.from_store(meaning=False, scoped=True)
        self.assertEqual(scoped["other_project"], 0)
        self.assertIn("projects with no pieces of their own", route.render_store(scoped))
