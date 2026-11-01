import os

from athos import capture, session, store
from tests.helpers import TempHome

FLAKY_PIECE = "\n".join((
    "---",
    "title: Run the flaky test until it fails",
    "when: a test fails only sometimes in CI",
    "---",
    "1. Run it 20 times with `-x`.",
    "2. Look for shared state between tests.",
    "",
))


def edits(sid: str, n: int) -> None:
    """`n` file edits in session `sid`, as the PostToolUse hook reports them."""
    for _ in range(n):
        capture.count_tool({"session_id": sid, "tool_name": "Edit"})


def shell(sid: str, command: str) -> None:
    capture.count_tool({"session_id": sid, "tool_name": "Bash", "tool_input": {"command": command}})


def ask(sid: str, **event):
    """What the Stop hook answers for session `sid`."""
    return capture.stop_decision({"session_id": sid, **event})


class SavingTest(TempHome):
    def test_a_new_piece_keeps_its_origin_and_project(self):
        session.update("s1", model="claude-opus-5-5")
        piece, diff = capture.save_text(FLAKY_PIECE, "s1", cwd=self.home)
        self.assertIsNone(diff)
        stored = store.get(piece.id)
        self.assertEqual(
            (stored.when, stored.origin, stored.projects),
            ("a test fails only sometimes in CI", {"platform": "claude-code", "model": "claude-opus-5-5"},
             [os.path.basename(self.home)]))
        self.assertIn("Run it 20 times", stored.body)

    def test_a_piece_missing_when_or_body_is_refused(self):
        for incomplete in ("---\ntitle: x\n---\nbody", "---\ntitle: x\nwhen: y\n---\n"):
            with self.subTest(text=incomplete), self.assertRaises(ValueError):
                capture.save_text(incomplete, "s1")

    def test_improving_a_piece_needs_something_to_change(self):
        piece, _ = capture.save_text(FLAKY_PIECE, "s1")
        with self.assertRaises(ValueError):
            capture.save_text(f"---\nid: {piece.id}\n---\n", "s1")
        better, diff = capture.save_text(f"---\nid: {piece.id}\nnote: tighter\n---\nRun it 50 times.", "s1")
        self.assertEqual((better.id, better.version), (piece.id, 2))
        self.assertTrue(diff)

    def test_saving_starts_the_tally_over(self):
        edits("s1", 7)
        capture.save_text(FLAKY_PIECE, "s1")
        self.assertEqual(session.load("s1")["tools_since_capture"], 0)


class StopHookTest(TempHome):
    def test_it_waits_for_enough_work(self):
        edits("s1", capture.THRESHOLD - 1)
        self.assertIsNone(ask("s1"))
        edits("s1", 1)
        answer = ask("s1")
        self.assertEqual(answer["decision"], "block")
        self.assertIn("save <<'EOF'", answer["reason"])

    def test_it_asks_once_and_never_inside_its_own_stop(self):
        edits("s1", capture.THRESHOLD)
        self.assertIsNotNone(ask("s1"))
        self.assertIsNone(ask("s1"))                                     # the tally started over
        edits("s1", capture.THRESHOLD)
        self.assertIsNone(ask("s1", stop_hook_active=True))

    def test_the_environment_can_switch_it_off(self):
        edits("s1", capture.THRESHOLD)
        os.environ["ATHOS_CAPTURE"] = "off"
        try:
            self.assertFalse(capture.enabled())
            self.assertIsNone(ask("s1"))
        finally:
            os.environ.pop("ATHOS_CAPTURE")

    def test_it_points_at_the_pieces_already_loaded(self):
        session.update("s1", loaded=["fix-flaky-test"], tools_since_capture=capture.THRESHOLD, work_since_capture=1,
                       edits_since_capture=1)
        self.assertIn("fix-flaky-test", ask("s1")["reason"])


class TallyTest(TempHome):
    def test_a_subagents_calls_are_not_the_persons_work(self):
        # Found live: a background research agent's tool calls kept asking for captures on turns with no work.
        for _ in range(10):
            capture.count_tool({"session_id": "s1", "agent_id": "a1", "tool_name": "WebFetch"})
        self.assertIsNone(ask("s1"))

    def test_athos_commands_are_not_counted(self):
        for command in ("/x/bin/athos save <<'EOF'", "athos mark g", "python3 /p/bin/athos report"):
            shell("s1", command)
        self.assertEqual(session.load("s1").get("tools_since_capture", 0), 0)
        shell("s1", "git status")
        self.assertEqual(session.load("s1")["tools_since_capture"], 1)

    def test_each_request_has_its_own_tally(self):
        from athos import eval as ev
        edits("s1", capture.THRESHOLD - 1)
        ev.task_start({"session_id": "s1", "prompt": "next request"})
        edits("s1", 1)
        self.assertIsNone(ask("s1"))


class QuietCaptureTest(TempHome):
    def test_with_the_guide_given_the_stop_line_is_short(self):
        from athos import load
        store.create("Ship", "shipping", "1. ship")
        opening = load.on_session_start({"session_id": "s2", "cwd": self.home})
        self.assertIn("Saving know-how (Athos)", opening)
        edits("s2", capture.THRESHOLD)
        line = ask("s2")["reason"]
        self.assertLess(len(line), 140)
        self.assertIn("athos save", line)

    def test_without_the_guide_the_stop_line_carries_the_format(self):
        edits("s3", capture.THRESHOLD)
        self.assertIn("save <<'EOF'", ask("s3")["reason"])

    def test_the_session_learns_where_the_saved_piece_is_ready(self):
        piece, _ = capture.save_text(FLAKY_PIECE, "s4")
        expected = {"id": piece.id, "title": piece.title, "version": 1, "platforms": ["Claude Code"]}
        self.assertEqual(session.load("s4")["last_saved"], expected)

    def test_an_existing_codex_export_is_refreshed_on_save(self):
        from athos.adapters import codex
        skills = codex.skills_dir()
        self.assertTrue(str(skills).startswith(self.home))
        (skills / "athos-old").mkdir(parents=True)
        piece, _ = capture.save_text(FLAKY_PIECE, "s5")
        self.assertTrue((skills / f"athos-{piece.id}" / "SKILL.md").exists())
        self.assertEqual(session.load("s5")["last_saved"]["platforms"], ["Claude Code", "Codex", "Muse Code"])


class RealWorkTest(TempHome):
    """The Stop hook asks only after a turn that changed something; a turn of reads and checks ends quietly."""

    def _bash(self, cmd):
        capture.count_tool({"session_id": "s9", "tool_name": "Bash", "tool_input": {"command": cmd}})

    def test_reads_and_checks_alone_never_ask(self):
        # Found live: "¿por qué veo este texto?" answered with a grep and `claude plugin list`-style checks still asked.
        for cmd in ("ls ~/.athos", "grep -n x a.py | head -3", "git status --short && git log --oneline -3",
                    "gh pr view 28 --json state", "sed -n 1,20p a.py", "which -a athos", "cat a 2>&1 | tail -2"):
            self._bash(cmd)
        capture.count_tool({"session_id": "s9", "tool_name": "Read", "tool_input": {"file_path": "/x"}})
        self.assertIsNone(capture.stop_decision({"session_id": "s9"}))

    def test_one_change_among_the_calls_asks(self):
        self._bash("ls")
        self._bash("git status")
        capture.count_tool({"session_id": "s9", "tool_name": "Edit", "tool_input": {"file_path": "/x"}})
        self.assertIsNotNone(capture.stop_decision({"session_id": "s9"}))

    def test_what_counts_as_a_change(self):
        for cmd in ("git commit -s -m x", "gh pr merge 28 --squash", "sed -i '' s/a/b/ f", "python3 t.py",
                    "echo x > f.txt", "ls && rm f", "gh api -X PUT repos/o/r/branches/main/protection"):
            self.assertFalse(capture._read_only_shell(cmd), cmd)
        for cmd in ("git log --oneline origin/main..wiki", "ls > /dev/null", "grep x f 2>&1", "FOO=1 git diff"):
            self.assertTrue(capture._read_only_shell(cmd), cmd)


class SpanishTest(TempHome):
    def test_the_stop_line_follows_the_persons_language(self):
        from athos import load, start
        store.create("Ship", "shipping", "1. ship")
        load.on_session_start({"session_id": "s5", "cwd": self.home})
        capture.count_tool({"session_id": "s5", "tool_name": "Edit"})
        for _ in range(capture.THRESHOLD):
            capture.count_tool({"session_id": "s5", "tool_name": "Edit"})
        start.save_choice("es", "law")
        reason = capture.stop_decision({"session_id": "s5"})["reason"]
        self.assertIn("¿algo de esta tarea vale la pena guardar?", reason)
        self.assertIn("athos save", reason)


class ChecklistTest(TempHome):
    """A task that follows a checklist is worth keeping even when it only reads and answers (a lawyer's review)."""

    def test_a_checklist_in_the_request_asks_without_file_changes(self):
        capture.note_request({"session_id": "s1", "prompt": "Revisá este contrato con mi checklist"})
        capture.count_tool({"session_id": "s1", "tool_name": "Read", "tool_input": {"file_path": "/c.md"}})
        out = capture.stop_decision({"session_id": "s1"})
        self.assertIn("checklist", out["reason"])
        self.assertIsNone(capture.stop_decision({"session_id": "s1"}))           # once

    def test_a_pasted_list_or_an_opened_checklist_file_counts(self):
        self.assertTrue(capture.mentions_checklist("Check:\n- deposit\n- notice period\n- jurisdiction"))
        self.assertTrue(capture.mentions_checklist("seguí el protocolo de la clínica"))
        self.assertFalse(capture.mentions_checklist("check the CI of #951"))
        capture.count_tool({"session_id": "s2", "tool_name": "Read",
                            "tool_input": {"file_path": "/x/checklist-lease.md"}})
        self.assertIsNotNone(capture.stop_decision({"session_id": "s2"}))

    def test_a_checklist_a_loaded_piece_already_led_does_not_ask(self):
        capture.note_request({"session_id": "s3", "prompt": "review the lease against my checklist"})
        session.update("s3", task_loaded=["review-a-contract"])
        self.assertIsNone(capture.stop_decision({"session_id": "s3"}))

    def test_the_persons_own_list_on_top_of_a_loaded_piece_asks(self):
        # A lawyer's first review: the generic starter loads, and they paste their own checklist.
        capture.note_request({"session_id": "s4", "prompt": "Revisá el contrato con mi checklist:\n- depósito\n"
                                                                "- preaviso\n- reparaciones"})
        session.update("s4", task_loaded=["revisar-un-contrato-con-tu-checklist"])
        self.assertIsNotNone(capture.stop_decision({"session_id": "s4"}))

    def test_the_persons_checklist_file_on_top_of_a_loaded_piece_asks(self):
        capture.note_request({"session_id": "s5", "prompt": "Revisá el contrato con mi checklist"})
        session.update("s5", task_loaded=["revisar-un-contrato-con-tu-checklist"])
        capture.count_tool({"session_id": "s5", "tool_name": "Read", "tool_input": {"file_path": "/e/mi-checklist.md"}})
        self.assertIsNotNone(capture.stop_decision({"session_id": "s5"}))

    def test_a_checklist_file_named_in_the_request_is_the_persons_own(self):
        # The lawyer demo: the agent may not open the file as its own call, but the request names it.
        capture.note_request({"session_id": "s6", "prompt": "Revisá contrato.md con mi checklist (mi-checklist.md)."})
        session.update("s6", task_loaded=["revisar-un-contrato-con-tu-checklist"])
        self.assertIsNotNone(capture.stop_decision({"session_id": "s6"}))

    def test_commands_alone_ask_only_after_several_and_reads_never(self):
        for _ in range(capture.WORK_MIN - 1):
            capture.count_tool({"session_id": "w", "tool_name": "Bash", "tool_input": {"command": "pytest -q"}})
        for _ in range(5):
            capture.count_tool({"session_id": "w", "tool_name": "Bash", "tool_input": {"command": "git status"}})
        self.assertIsNone(capture.stop_decision({"session_id": "w"}))         # 4 commands and reads: quiet
        capture.count_tool({"session_id": "w", "tool_name": "Bash", "tool_input": {"command": "pytest -q"}})
        self.assertIsNotNone(capture.stop_decision({"session_id": "w"}))

    def test_a_word_in_a_command_is_not_the_persons_checklist(self):
        for _ in range(2):
            capture.count_tool({"session_id": "c", "tool_name": "Bash", "tool_input": {"command": "grep -rn checklist ."}})
        self.assertFalse(session.load("c").get("checklist"))
        capture.count_tool({"session_id": "c", "tool_name": "Read", "tool_input": {"file_path": "/w/mi-checklist.md"}})
        self.assertTrue(session.load("c").get("checklist_typed"))

    def test_never_asks_in_a_request_that_already_saved(self):
        for _ in range(capture.THRESHOLD):
            capture.count_tool({"session_id": "v", "tool_name": "Edit"})
        capture.count_tool({"session_id": "v", "tool_name": "Bash", "tool_input": {"command": "athos save <<'EOF'"}})
        self.assertIsNone(capture.stop_decision({"session_id": "v"}))

    def test_an_interactive_session_gets_an_offer_not_a_question(self):
        session.update("o", task_id="t1")
        for _ in range(capture.THRESHOLD):
            capture.count_tool({"session_id": "o", "tool_name": "Edit"})
        self.assertIsNone(capture.stop_decision({"session_id": "o"}, offer=True))
        self.assertEqual(session.load("o")["offer"], {"task_id": "t1", "reason": "work"})
        capture.note_request({"session_id": "o", "prompt": "next"})               # a new request clears it
        self.assertIsNone(session.load("o")["offer"])

