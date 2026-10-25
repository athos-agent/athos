import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from athos import capture, eval as ev, session, store
from athos.adapters import codex
from tests.helpers import TempHome


def token_line(ts, inp, cached, out):
    return json.dumps({"timestamp": ts, "type": "event_msg", "payload": {"type": "token_count", "info": {
        "total_token_usage": {"input_tokens": inp, "cached_input_tokens": cached, "cache_write_input_tokens": 0,
                              "output_tokens": out, "reasoning_output_tokens": 0, "total_tokens": inp + out}}}})


ROLLOUT = "\n".join([
    json.dumps({"timestamp": "2026-10-25T21:51:27.000Z", "type": "session_meta", "payload": {"id": "x"}}),
    token_line("2026-10-25T21:51:30.000Z", 1000, 800, 10),          # before the task: an earlier turn
    token_line("2026-10-25T21:51:40.000Z", 3000, 2000, 50),
    token_line("2026-10-25T21:51:50.000Z", 5000, 3500, 90),         # the last report inside the task
    token_line("2026-10-25T21:52:30.000Z", 9000, 7000, 200),        # after the task
]) + "\n"


class CodexTokensTest(TempHome):
    def test_tokens_are_the_difference_of_cumulative_counts(self):
        f = Path(self.home) / "rollout.jsonl"
        f.write_text(ROLLOUT)
        t = codex.tokens_between(str(f), "2026-10-25T21:51:35+00:00", "2026-10-25T21:52:00+00:00")
        self.assertEqual(t, {"input": 4000 - 2700, "output": 80, "cache_read": 2700, "cache_write": 0,
                             "total": 4080})

    def test_compressed_rollouts_are_read(self):
        from compression import zstd
        f = Path(self.home) / "rollout.jsonl.zst"
        with zstd.open(f, "wt") as fh:
            fh.write(ROLLOUT)
        t = codex.tokens_between(str(Path(self.home) / "rollout.jsonl"), "2026-10-25T21:51:35+00:00",
                                 "2026-10-25T21:52:00+00:00")
        self.assertEqual(t["total"], 4080)

    def test_unreadable_is_none(self):
        self.assertIsNone(codex.tokens_between(None, "", ""))
        self.assertIsNone(codex.tokens_between("/nonexistent.jsonl", "", ""))


class CodexSkillsTest(TempHome):
    def test_each_piece_becomes_a_skill_without_losing_anything(self):
        p = store.create("Cut a release", "release a new version: bump, changelog, tag",
                         "Tag message `greet X.Y.Z`.", projects=["greet"])
        store.update(p.id, "added a step", body="Tag message `greet X.Y.Z`.\nCommit `release X.Y.Z`.")
        with tempfile.TemporaryDirectory() as d:
            n, removed = codex.export_skills(Path(d))
            text = (Path(d) / f"athos-{p.id}" / "SKILL.md").read_text()
        self.assertEqual((n, removed), (1, 0))
        self.assertTrue(text.startswith(f"---\nname: athos-{p.id}\ndescription: "))
        self.assertIn("Use when: release a new version", text)
        for kept in ("Commit `release X.Y.Z`.", "projects: [greet]", "version: 2", "added a step"):
            self.assertIn(kept, text)

    def test_skills_of_deleted_pieces_are_removed_and_others_left_alone(self):
        p = store.create("Gone", "gone soon", "x")
        with tempfile.TemporaryDirectory() as d:
            codex.export_skills(Path(d))
            (Path(d) / "someone-else").mkdir()
            (Path(d) / "someone-else" / "SKILL.md").write_text("---\nname: someone-else\n---\n")
            p.path.unlink()
            self.assertEqual(codex.export_skills(Path(d)), (0, 1))
            self.assertTrue((Path(d) / "someone-else" / "SKILL.md").is_file())


class CodexInstallTest(TempHome):
    def test_install_keeps_other_hooks_backs_up_and_is_idempotent(self):
        f = Path(self.home) / "codex" / "hooks.json"
        f.parent.mkdir()
        other = {"type": "command", "command": "echo mine"}
        f.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [other]}]}}))
        _, backup = codex.install(Path("/plugin"), f)
        codex.install(Path("/plugin"), f)
        data = json.loads(f.read_text())
        self.assertIsNotNone(backup)
        self.assertIn(other, data["hooks"]["Stop"][0]["hooks"])
        for event in codex.EVENTS:
            ours = [h for g in data["hooks"][event] for h in g["hooks"] if codex._is_ours(h)]
            self.assertEqual(len(ours), 1, event)
        self.assertTrue(os.access(codex.shim_path(), os.X_OK))
        codex.uninstall(f)
        self.assertEqual(json.loads(f.read_text()), {"hooks": {"Stop": [{"hooks": [other]}]}})


class CodexPlatformTest(TempHome):
    def test_tasks_and_pieces_record_codex_and_its_model(self):
        session.update("c1", platform="codex")
        ev.task_start({"session_id": "c1", "prompt": "release", "model": "gpt-6.1-sol"}, platform="codex")
        piece, _ = capture.save_text("---\ntitle: T\nwhen: tt ww\n---\nbody", "c1")
        with mock.patch.object(ev, "now", return_value=ev.now()):
            ev.task_end({"session_id": "c1"})
        self.assertEqual(piece.origin, {"platform": "codex", "model": "gpt-6.1-sol"})
        m = ev.report()["models"][0]
        self.assertEqual((m["platform"], m["model"]), ("codex", "gpt-6.1-sol"))
