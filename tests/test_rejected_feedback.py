"""A candidate the verifier rejected comes back to a frontier model as something to fix: its reasons, in the output of
`athos show` the agent runs in the piece's own project and as a short marker on the index line, never to the person,
another project, a public repository's foreign piece or an apply model. The automatic save makes a new version of it;
a piece that keeps failing is set aside for the person; a reuse while the verdict is a fail never counts towards
promotion. Synthetic pieces and projects only."""

import json
import os

from athos import autolearn, eval as ev, grade, load, session, store, verify
from tests.helpers import TempHome
from tests.test_autolearn import BODY, PIECE, _HookedTask

AGENT = {"CLAUDECODE": "1"}
REASONS = {"evidence_passed": (True, "the unit tests passed"),
           "piece_matches_work": (False, "it states a duration nothing in the output shows"),
           "checks_runnable": (True, "the Check runs here"),
           "no_private_data": (True, "nothing private"),
           "reusable": (False, "it narrates this task instead of a way of working")}


def _candidate(project="demo", body=BODY, title="Change the parser safely"):
    return store.create(title, "changing the parser of this project", body, projects=[project], status="candidate",
                        learned_by="claude-opus-5-5", confidence="0.3", risk="normal", visibility="project")


def _verdict(piece, outcome="fail"):
    reasons = {c: (True, "fine") for c in verify.CRITERIA} if outcome == "pass" else REASONS
    verdict = {c: {"pass": ok, "why": why} for c, (ok, why) in reasons.items()}
    return verify._record(store.get(piece.id), None, "claude-fable-5", verdict, outcome, "", {"task_id": "t0"},
                          named=None, prompt=None)


class RejectionTest(TempHome):
    def test_the_latest_failing_verdict_of_the_current_text_is_a_rejection(self):
        p = _candidate()
        self.assertIsNone(grade.rejection(p))
        _verdict(p)
        found = grade.rejection(store.get(p.id))
        self.assertEqual(sorted(found["failed"]), ["piece_matches_work", "reusable"])
        self.assertIn("duration", found["why"]["piece_matches_work"])
        self.assertEqual((found["attempts"], found["set_aside"]), (1, False))

    def test_not_for_a_pass_a_changed_text_or_a_persons_piece(self):
        p = _candidate()
        _verdict(p)
        _verdict(p, "pass")
        self.assertIsNone(grade.rejection(store.get(p.id)))
        q = _candidate(title="Another")
        _verdict(q)
        store.update(q.id, "a fix", body=BODY + "\n## #more\n**When:** later.\n**Do:** more.\n")
        self.assertIsNone(grade.rejection(store.get(q.id)))           # the verdict was about the old text
        mine = store.create("Mine", "my thing", BODY, projects=["demo"])
        ev.audit({"type": "verify", "piece": mine.id, "outcome": "fail", "body_sha": grade.body_sha(mine)})
        self.assertIsNone(grade.rejection(store.get(mine.id)))

    def test_the_feedback_text_names_the_reasons_and_the_one_save_path(self):
        p = _candidate()
        _verdict(p)
        text = grade.feedback_text(store.get(p.id), "athos")
        self.assertIn("was not accepted", text)
        self.assertIn("piece_matches_work: it states a duration", text)
        self.assertIn("reusable: it narrates this task", text)
        self.assertNotIn("evidence_passed", text)
        self.assertIn("athos save --auto", text)
        self.assertIn(f"id: {p.id}", text)
        self.assertIn("Don't mention", text)


class ShowTest(_HookedTask):
    """`athos show` run by the agent: the reasons follow the piece only for a frontier session in the piece's own
    project."""

    def setUp(self):
        super().setUp()
        self.piece = _candidate()
        _verdict(self.piece)

    def show(self, cwd=None, sid="f1"):
        return self.cli.run_athos("show", self.piece.id, cwd=cwd or self.work,
                                  env={**AGENT, "CLAUDE_CODE_SESSION_ID": sid})

    def test_the_agent_in_its_own_project_on_a_frontier_model_gets_the_reasons(self):
        self.task(stop=False)
        done = self.show()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Change the parser safely", done.stdout)
        self.assertIn("was not accepted", done.stdout)
        self.assertIn("it states a duration", done.stdout)
        self.assertLess(done.stdout.index("Change the parser safely"), done.stdout.index("was not accepted"))

    def test_the_person_at_their_own_terminal_does_not(self):
        self.task(stop=False)
        # In the project's own folder, while the session is live, but no agent's shell runs it.
        done = self.cli.run_athos("show", self.piece.id, cwd=self.work)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("was not accepted", done.stdout)

    def test_not_in_another_project(self):
        other = os.path.join(self.home, "work", "other")
        os.makedirs(other)
        self.task(stop=False)
        session.save("o1", {"task_id": "to", "model": "claude-opus-5-5", "project": "other"})
        done = self.show(cwd=other, sid="o1")
        self.assertNotIn("was not accepted", done.stdout)
        self.assertNotIn("duration", done.stdout)

    def test_not_in_a_public_repository_for_a_piece_of_another_project(self):
        pub = os.path.join(self.home, "work", "pub")
        os.makedirs(pub)
        with open(os.path.join(pub, ".athos.toml"), "w") as f:
            f.write("public = true\n")
        session.save("p1", {"task_id": "tp", "model": "claude-opus-5-5", "project": "pub", "public": True})
        done = self.show(cwd=pub, sid="p1")
        self.assertNotIn("was not accepted", done.stdout + done.stderr)
        self.assertNotIn("duration", done.stdout + done.stderr)

    def test_not_to_an_apply_model(self):
        self.task(model="claude-haiku-5-5", stop=False)
        done = self.show()
        self.assertNotIn("was not accepted", done.stdout)


class IndexMarkerTest(TempHome):
    def test_the_frontier_index_line_carries_one_short_marker(self):
        p = _candidate()
        _verdict(p)
        work = os.path.join(self.home, "work", "demo")
        os.makedirs(work)
        session.save("s1", {"task_id": "t1", "model": "claude-opus-5-5", "project": "demo"})
        notes = load.index_notes([store.get(p.id)], {}, [store.get(p.id)], "s1", work)
        self.assertIn("not accepted by the verifier", notes[p.id])
        self.assertNotIn("duration", notes[p.id])                     # the reasons come with `athos show` only

    def test_no_marker_from_another_project(self):
        p = _candidate()
        _verdict(p)
        other = os.path.join(self.home, "work", "other")
        os.makedirs(other)
        session.save("s1", {"task_id": "t1", "model": "claude-opus-5-5", "project": "other"})
        notes = load.index_notes([store.get(p.id)], {}, [store.get(p.id)], "s1", other)
        self.assertNotIn("not accepted", notes.get(p.id, ""))


class ImproveTest(_HookedTask):
    """The one path: the automatic save with the candidate's own `id:` makes its next version."""

    def improved(self, pid, note="drop the narration"):
        return PIECE.replace("---\ntitle:", f"---\nid: {pid}\nnote: {note}\ntitle:", 1).replace(
            "**Do:** run the unit tests.", "**Do:** run the unit tests before bumping the version.")

    def test_save_auto_makes_a_new_version_of_a_learned_candidate_and_starts_the_verifier(self):
        p = _candidate()
        _verdict(p)
        self.task(stop=False)
        done = self.cli.run_athos("save", "--auto", stdin=self.improved(p.id), cwd=self.work,
                                  env={**AGENT, "CLAUDE_CODE_SESSION_ID": "f1"})
        self.assertEqual(done.returncode, 0, done.stderr)
        now = store.get(p.id)
        self.assertEqual((now.status, now.version), ("candidate", p.version + 1))
        self.assertIn("drop the narration", store.render(now))         # the history line is kept
        self.assertTrue(verify._bundle_of(now))                        # a new bundle for the new text
        self.assertIsNone(grade.rejection(now))                        # the old verdict was about the old text
        [saved] = [e for e in ev.events() if e.get("type") == "learn" and e.get("decision") == "saved"]
        self.assertTrue(saved.get("improved"))

    def test_a_persons_piece_is_never_touched(self):
        mine = store.create("Mine", "changing the parser of this project", BODY, projects=["demo"])
        self.task(stop=False)
        done = self.cli.run_athos("save", "--auto", stdin=self.improved(mine.id), cwd=self.work,
                                  env={**AGENT, "CLAUDE_CODE_SESSION_ID": "f1"})
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(store.get(mine.id).version, mine.version)

    def test_a_verified_piece_returns_to_candidate(self):
        p = _candidate()
        store.set_status(p.id, "verified", "test")
        self.task(stop=False)
        done = self.cli.run_athos("save", "--auto", stdin=self.improved(p.id), cwd=self.work,
                                  env={**AGENT, "CLAUDE_CODE_SESSION_ID": "f1"})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(store.get(p.id).status, "candidate")


class BoundTest(_HookedTask):
    """A piece that keeps failing is not rewritten forever."""

    def fail_versions(self, n):
        p = _candidate()
        for k in range(n):
            if k:
                store.update(p.id, f"attempt {k + 1}", body=BODY + f"\n<!-- attempt {k + 1} -->\n")
            _verdict(store.get(p.id))
        return store.get(p.id)

    def test_after_the_limit_it_is_set_aside_for_the_person(self):
        p = self.fail_versions(grade.MAX_FAILED_VERSIONS)
        found = grade.rejection(p)
        self.assertEqual((found["attempts"], found["set_aside"]), (grade.MAX_FAILED_VERSIONS, True))
        self.assertEqual(grade.feedback_text(p), "")                  # nothing more is asked of the model
        self.assertIn(p.id, grade.reviews())
        self.assertIn("rejected", grade.reviews()[p.id]["why"])
        aside = [e for e in ev.events() if e.get("type") == "grade" and str(e.get("basis", "")).startswith("set_aside")]
        self.assertEqual(len(aside), 1)
        report = ev.report()
        [row] = [r for r in report["pieces"] if r["piece"] == p.id]
        self.assertTrue(any("set aside" in flag for flag in row["review"]))
        self.assertIn(p.id, report["review"])

    def test_the_audit_names_it(self):
        from athos import audit
        p = self.fail_versions(grade.MAX_FAILED_VERSIONS)
        self.task(stop=True)
        out = audit.run(cwd=self.work)
        [rule] = [r for s in out["sessions"] for r in s["rules"] if r["rule"] == "candidate_set_aside"]
        self.assertEqual(rule["status"], "flagged")
        self.assertIn(p.id, json.dumps(rule["found"]))

    def test_below_the_limit_it_is_still_asked(self):
        p = self.fail_versions(grade.MAX_FAILED_VERSIONS - 1)
        self.assertFalse(grade.rejection(p)["set_aside"])
        self.assertTrue(grade.feedback_text(p))

    def test_a_pass_starts_the_count_again(self):
        p = self.fail_versions(grade.MAX_FAILED_VERSIONS - 1)
        _verdict(p, "pass")
        store.update(p.id, "later", body=BODY + "\n<!-- later -->\n")
        _verdict(store.get(p.id))
        self.assertEqual(grade.rejection(store.get(p.id))["attempts"], 1)

    def test_the_automatic_save_is_refused_once_set_aside(self):
        p = self.fail_versions(grade.MAX_FAILED_VERSIONS)
        self.task(stop=False)
        text = PIECE.replace("---\ntitle:", f"---\nid: {p.id}\nnote: once more\ntitle:", 1).replace(
            "run the unit tests.", "run the unit tests again.")
        done = self.cli.run_athos("save", "--auto", stdin=text, cwd=self.work,
                                  env={**AGENT, "CLAUDE_CODE_SESSION_ID": "f1"})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("set aside", done.stderr)
        self.assertEqual(store.get(p.id).version, p.version)


class ReuseWhileFailingTest(TempHome):
    def test_a_reuse_of_a_rejected_text_never_counts_towards_promotion(self):
        p = _candidate()
        _verdict(p)
        for n in range(grade.FRONTIER_REUSES):
            sid = f"r{n}"
            session.save(sid, {"task_id": f"rt{n}", "model": "claude-opus-5-5", "model_source": "transcript",
                               "task_loaded": [p.id]})
            from athos import evidence
            evidence.add(f"rt{n}", {"type": "commit", "strength": "strong", "polarity": "positive", "sha": "abc"})
            [reuse] = grade.finish_task(sid, f"rt{n}", session.load(sid))
            self.assertEqual((reuse["outcome"], reuse["verdict"]), ("clean", "fail"))
        # The same text verified again, and it passes: the reuses made while it stood rejected still do not count.
        _verdict(store.get(p.id), "pass")
        self.assertEqual(store.get(p.id).status, "candidate")
        self.assertEqual(grade.standing(store.get(p.id))["frontier_clean"], 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
