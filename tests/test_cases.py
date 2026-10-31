import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from athos import capture, cases, cli, eval as ev, load, replay, session, store
from tests.helpers import TempHome

PIECE = ("---\ntitle: Review a contract\nwhen: reviewing a lease contract against my checklist\n---\n"
         "## #parties\n**When:** first\n**Do:** check the parties\n**Because:** always\n")
REQUEST = "Review this lease contract against my checklist, clause by clause. " + "x" * 300


def claude_transcript(path, answers):
    """A transcript like Claude Code's: a user line, then assistant lines with text and tool-use blocks."""
    with open(path, "w") as fh:
        fh.write(json.dumps({"type": "user", "message": {"role": "user", "content": "review it"}}) + "\n")
        for a in answers:
            fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Read", "input": {}}]}}) + "\n")
            fh.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": a}]}}) + "\n")


class Fake:
    """A model: answers every request with `answer`, and judges with `verdict` (a JSON string)."""

    def __init__(self, answer="the new answer", verdict='{"pass": true, "reason": "keeps the 30 days"}'):
        self.answer, self.verdict, self.calls = answer, verdict, []

    def __call__(self, model, system, user):
        self.calls.append((model, system, user))
        return self.verdict if "Reply with only a JSON object" in user else self.answer


class WithPiece(TempHome):
    def setUp(self):
        super().setUp()
        self.piece, _ = capture.save_text(PIECE, "setup")

    def task(self, sid, prompt=REQUEST, answer="Clause 3 is fine.", transcript=None):
        ev.task_start({"session_id": sid, "prompt": prompt, "cwd": self.home})
        load.on_prompt({"session_id": sid, "prompt": prompt})
        event = {"session_id": sid, "transcript_path": transcript}
        if answer is not None:
            event["last_assistant_message"] = answer
        rec = ev.task_end(event)
        cases.on_task_end(event, rec)
        return rec["task_id"]


class CasesTest(WithPiece):
    def test_a_marked_task_that_loaded_a_piece_is_kept_whole(self):
        tid = self.task("s1")
        self.assertEqual(cases.all_cases(), [])                     # nothing is kept until the person marks it
        ev.mark("g", session_id="s1")
        c = json.loads((Path(self.home) / "cases" / self.piece.id / f"{tid}.json").read_text())
        self.assertEqual((c["request"], c["answer"], c["mark"], c["version"]), (REQUEST, "Clause 3 is fine.", "ok", 1))
        self.assertEqual(ev.tasks()[0]["request"], REQUEST[:120])   # the event log still keeps only the start

    def test_a_task_without_a_piece_is_never_kept(self):
        ev.task_start({"session_id": "s1", "prompt": "what time is it", "cwd": self.home})
        rec = ev.task_end({"session_id": "s1", "last_assistant_message": "noon"})
        cases.on_task_end({"session_id": "s1"}, rec)
        ev.mark("g", session_id="s1")
        self.assertEqual(cases.all_cases(), [])

    def test_the_answer_is_read_from_a_claude_code_transcript(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.jsonl")
            claude_transcript(p, ["Looking.", "Final: clause 3 needs a 30-day notice."])
            self.task("s1", answer=None, transcript=p)
        ev.mark("g", session_id="s1")
        self.assertEqual(cases.all_cases()[0]["answer"], "Final: clause 3 needs a 30-day notice.")
        self.assertIsNone(cases.answer_from_transcript("/nonexistent"))

    def test_the_answer_is_read_from_a_codex_rollout(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.jsonl")
            Path(p).write_text(json.dumps({"type": "response_item", "payload": {
                "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done."}]}}) + "\n")
            self.assertEqual(cases.answer_from_transcript(p), "Done.")

    def test_the_capture_turn_does_not_replace_the_answer_the_person_judged(self):
        tid = self.task("s1")
        rec = ev.task_end({"session_id": "s1", "last_assistant_message": "Saved."})
        cases.on_task_end({"session_id": "s1", "last_assistant_message": "Saved."}, rec)
        ev.mark("g", tid)
        self.assertEqual(cases.all_cases()[0]["answer"], "Clause 3 is fine.")

    def test_an_inferred_correction_keeps_the_words_that_corrected_it(self):
        self.task("s1")
        ev.infer_mark("s1", "no funciona: the notice period is 30 days, not 60")
        c = cases.all_cases()[0]
        self.assertEqual((c["mark"], c["correction"]), ("corrected", "no funciona: the notice period is 30 days, not 60"))
        self.assertEqual(len(cases.tests(self.piece.id)), 1)

    def test_after_an_explicit_mark_c_the_next_request_is_the_correction(self):
        self.task("s1")
        ev.mark("c", session_id="s1")
        self.assertIsNone(cases.all_cases()[0]["correction"])
        self.assertTrue(cases.note_prompt("s1", "Use 30 days for the notice"))
        self.assertFalse(cases.note_prompt("s1", "another request"))     # only the next one
        self.assertEqual(cases.all_cases()[0]["correction"], "Use 30 days for the notice")

    def test_a_mark_from_another_folder_finds_the_task_in_its_session(self):
        tid = self.task("s1")
        ev.mark("g", tid)                                               # no session given (athos watch, another cwd)
        self.assertEqual(cases.all_cases()[0]["task_id"], tid)
        ev.mark("f", tid)                                               # a later mark changes the kept one
        self.assertEqual(cases.all_cases()[0]["mark"], "failed")


class ReplayTest(WithPiece):
    def corrected(self, sid="s1", words="no funciona: notice is 30 days"):
        self.task(sid)
        ev.infer_mark(sid, words)

    def test_tests_replay_each_correction_on_the_current_version_and_record_a_run(self):
        self.corrected()
        fake = Fake()
        r = replay.run_tests(self.piece.id, "tiny:1b", fake)
        self.assertEqual((r["total"], r["passed"], r["version"]), (1, 1, 1))
        system, user = fake.calls[0][1], fake.calls[0][2]
        self.assertIn("check the parties", system)                     # system = the piece
        self.assertTrue(user.startswith("Review this lease"))           # user = the whole request
        self.assertIn("notice is 30 days", fake.calls[1][2])           # the judge sees the correction
        run = [e for e in ev.events() if e["type"] == "test_run"][0]
        self.assertEqual((run["piece"], run["passed"], run["total"]), (self.piece.id, 1, 1))
        self.assertIn("1 of 1 respect", replay.render_tests(r))

    def test_a_judge_without_json_still_gives_a_verdict(self):
        self.corrected()
        r = replay.run_tests(self.piece.id, "m", Fake(verdict="FAIL: still says 60 days"))
        self.assertFalse(r["results"][0]["pass"])
        self.assertIn("60 days", r["results"][0]["reason"])

    def test_a_piece_without_corrections_has_nothing_to_test(self):
        r = replay.run_tests(self.piece.id, "m", Fake())
        self.assertEqual(r["total"], 0)
        self.assertFalse(any(e["type"] == "test_run" for e in ev.events()))
        with self.assertRaises(LookupError):
            replay.run_tests("nope", "m", Fake())

    def test_improving_a_piece_with_corrections_says_how_many_to_re_check(self):
        self.corrected()
        capture.save_text(PIECE.replace("---\ntitle", f"---\nid: {self.piece.id}\nnote: 30 days\ntitle")
                          + "## #notice\n**When:** notice\n**Do:** 30 days\n**Because:** law\n", "s2")
        saved = session.load("s2")["last_saved"]
        self.assertEqual((saved["version"], saved["tests"], saved["recheck"]), (2, 1, "1 past correction to re-check"))

    def test_shadow_compares_good_cases_once_per_model_and_version(self):
        for i in range(3):
            self.task(f"g{i}")
            ev.mark("g", session_id=f"g{i}")
        fake = Fake(verdict='{"score": 92, "equivalent": true, "reason": "same clauses"}')
        rs = replay.run_shadow("muse-spark-1.3", fake, "meta", limit=2)
        self.assertEqual(len(rs), 2)
        self.assertIn("Approved answer:\nClause 3 is fine.", fake.calls[1][2])
        self.assertEqual(len(replay.pending("muse-spark-1.3")), 1)
        self.assertEqual(len(replay.pending("gemma4:12b")), 3)          # another model has all of them still
        e = [x for x in ev.events() if x["type"] == "shadow"][0]
        self.assertEqual((e["score"], e["equivalent"], e["model"]), (92, True, "muse-spark-1.3"))

    def test_a_score_without_a_verdict_decides_by_itself(self):
        self.task("g")
        ev.mark("g", session_id="g")
        rs = replay.run_shadow("m", Fake(verdict='{"score": 40}'))
        self.assertEqual((rs[0]["score"], rs[0]["equivalent"]), (40, False))

    def shadowed(self, n, matched, model="muse-spark-1.3", platform="meta"):
        for i in range(n):
            ev.append({"type": "shadow", "case": f"t{i}", "piece": self.piece.id, "version": 1, "platform": platform,
                       "model": model, "score": 90, "equivalent": i < matched, "at": ev._iso(ev.now())})

    def test_athos_suggests_a_hand_off_once_a_cheaper_model_keeps_matching(self):
        self.shadowed(4, 4)
        self.assertEqual(replay.handoffs(), [])                         # fewer than 5 runs: too early
        self.shadowed(1, 1)
        h = replay.handoffs()[0]
        self.assertEqual((h["label"], h["matched"], h["of"]), ("Muse Spark", 5, 5))
        self.assertEqual(replay.sentence(h), "Your «Review a contract» way of working is solid: Muse Spark matched "
                                             "5 of your last 5 approved tasks. Want to hand it to Muse Spark?")
        text = load.on_prompt({"session_id": "s9", "prompt": "review this lease contract against my checklist"})
        self.assertIn("Tell the person once", text)
        self.assertIn("--backend meta", text)
        again = load.on_prompt({"session_id": "s9", "prompt": "review this lease contract against my checklist"})
        self.assertNotIn("Tell the person once", again)                 # once
        self.assertTrue(replay.handoffs()[0]["told"])

    def test_the_suggestion_is_in_the_persons_language_at_session_start(self):
        from athos import start
        start.save_choice("es", "law")
        self.shadowed(10, 9, model="gemma4:12b", platform="local")
        text = load.on_session_start({"session_id": "s9", "cwd": self.home})
        self.assertIn("coincidió en 9 de tus últimas 10 tareas aprobadas", text)
        self.assertNotIn("--backend meta", text)

    def test_too_many_misses_suggest_nothing(self):
        self.shadowed(10, 8)
        self.assertEqual(replay.handoffs(), [])


class ChatTest(TempHome):
    def test_ollama_can_be_called_without_tools_and_keeps_them_by_default(self):
        from athos import delegate
        sent = []

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"message": {"content": "hi"}}'

        def urlopen(req, timeout=None):
            sent.append(json.loads(req.data))
            return Resp()
        with mock.patch("urllib.request.urlopen", urlopen):
            delegate.chat("m", [])
            delegate.chat("m", [], tools=False)
        self.assertIn("tools", sent[0])
        self.assertNotIn("tools", sent[1])

    def test_meta_can_be_called_without_tools(self):
        from athos.adapters import meta
        from tests.test_meta import fake_api, reply
        urlopen, sent = fake_api(reply("hi"), reply("hi"))
        with mock.patch.dict(os.environ, {"MODEL_API_KEY": "k"}):
            self.assertEqual(meta.chat("m", [], urlopen=urlopen, tools=False)["message"]["content"], "hi")
            meta.chat("m", [], urlopen=urlopen)
        self.assertNotIn("tools", sent[0]["body"])
        self.assertIn("tools", sent[1]["body"])

    def test_the_backend_asks_without_tools(self):
        seen = []
        with mock.patch("athos.delegate.chat", lambda m, msgs, tools=True: seen.append((m, msgs, tools)) or
                        {"message": {"content": " ok "}}):
            platform, model, ask = replay.backend("ollama")
            self.assertEqual(ask(model, "sys", "req"), "ok")
        self.assertEqual((platform, model, seen[0][2]), ("local", "gemma4:12b", False))


class ShadowSettingTest(WithPiece):
    def test_background_shadowing_is_off_until_turned_on_and_runs_detached_and_low(self):
        self.task("g")
        ev.mark("g", session_id="g")
        started = []
        self.assertFalse(replay.maybe_spawn(Path("/x/athos"), popen=lambda *a, **k: started.append((a, k))))
        replay.set_shadow(True)
        self.assertEqual(replay.settings()["backend"], "ollama")         # local unless the person chose Meta
        self.assertTrue(replay.maybe_spawn(Path("/x/athos"), popen=lambda *a, **k: started.append((a, k))))
        argv, kw = started[0][0][0], started[0][1]
        self.assertEqual(argv[argv.index("shadow"):argv.index("shadow") + 4], ["shadow", "--limit", "1", "--quiet"])
        self.assertTrue(kw["start_new_session"])
        if Path("/usr/bin/nice").exists():
            self.assertEqual(argv[:3], ["/usr/bin/nice", "-n", "19"])
        replay.take_lock()                                               # a run already at it: no second one
        self.assertFalse(replay.maybe_spawn(Path("/x/athos"), popen=lambda *a, **k: started.append((a, k))))
        replay.release_lock()
        replay.set_shadow(True, "meta")
        self.assertEqual(replay.settings(), {"on": True, "backend": "meta"})
        replay.set_shadow(False)
        self.assertFalse(replay.maybe_spawn(Path("/x/athos"), popen=lambda *a, **k: started.append((a, k))))

    def test_status_lists_tests_and_hand_offs(self):
        self.task("s1")
        ev.infer_mark("s1", "no funciona: 30 days")
        with mock.patch.object(cli, "_current_session", return_value={"session_id": "s1"}):
            s = cli.status()
        self.assertEqual(s["loads"][0]["tests"], 1)
        self.assertEqual(s["following"][0]["tests"], 1)
        self.assertEqual((s["handoff"], s["shadow"]), ([], False))

    def test_the_cli_runs_tests_with_an_injected_model(self):
        self.task("s1")
        ev.infer_mark("s1", "no funciona: 30 days")
        with mock.patch.object(replay, "backend", return_value=("local", "tiny", Fake())), \
                mock.patch("sys.stdout") as out:
            code = cli.main(["test", self.piece.id])
        self.assertEqual(code, 0)
        self.assertIn("1 of 1", "".join(c.args[0] for c in out.write.call_args_list))

    def test_the_hooks_keep_a_case_and_its_correction(self):
        import io

        def hook(name, payload):
            with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), mock.patch("sys.stdout", io.StringIO()):
                self.assertEqual(cli.hook(name), 0)
        base = {"session_id": "h1", "cwd": self.home}
        hook("prompt", {**base, "prompt": REQUEST})
        hook("stop", {**base, "last_assistant_message": "Notice: 60 days."})
        hook("prompt", {**base, "prompt": "está mal, the notice is 30 days"})
        c = cases.all_cases(self.piece.id)[0]
        self.assertEqual((c["request"], c["answer"], c["mark"], c["correction"]),
                         (REQUEST, "Notice: 60 days.", "corrected", "está mal, the notice is 30 days"))
