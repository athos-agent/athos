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


def rollout(cwd, turns):
    """A Codex session file like the real ones: meta, then per turn a user message, task_started, turn_context,
    tool calls, cumulative token counts and task_complete."""
    lines = [{"timestamp": "2026-10-25T21:58:00.000Z", "type": "session_meta",
              "payload": {"id": "sess-1", "cwd": cwd, "source": "exec"}}]
    total = 0
    for i, (prompt, secs, read) in enumerate(turns):
        t0 = f"2026-10-25T22:0{i}:00.000Z"
        t1 = f"2026-10-25T22:0{i}:{secs:02d}.000Z"
        # As in Codex 0.164.0: the turn starts, then its context, then the user's request.
        lines += [{"timestamp": t0, "type": "event_msg", "payload": {"type": "task_started", "turn_id": f"turn-{i}"}},
                  {"timestamp": t0, "type": "turn_context", "payload": {"turn_id": f"turn-{i}", "model": "gpt-6.1-sol"}},
                  {"timestamp": t0, "type": "response_item",
                   "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]}}]
        if read:
            lines.append({"timestamp": t0, "type": "response_item", "payload": {
                "type": "custom_tool_call", "input": f"cat .agents/skills/athos-{read}/SKILL.md"}})
        total += 1000
        lines.append({"timestamp": t1, "type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": total, "cached_input_tokens": 0, "output_tokens": 10,
                                  "total_tokens": total + 10}}}})
        lines.append({"timestamp": t1, "type": "event_msg",
                      "payload": {"type": "task_complete", "turn_id": f"turn-{i}", "duration_ms": secs * 1000}})
    return "\n".join(json.dumps(x) for x in lines) + "\n"


class CodexImportTest(TempHome):
    def write(self, cwd, turns):
        d = Path(self.home) / "sessions" / "2026" / "10" / "25"
        d.mkdir(parents=True, exist_ok=True)
        (d / "rollout-2026-10-25T22-00-00-sess-1.jsonl").write_text(rollout(cwd, turns))
        return Path(self.home) / "sessions"

    def test_each_turn_becomes_a_codex_task_with_model_duration_tokens_and_pieces(self):
        store.create("Cut a release", "release a new version", "x")
        root = self.write("/work/greet", [("Release 0.3.0", 21, "cut-a-release"), ("now the docs", 9, None)])
        out = codex.import_sessions(root)
        self.assertEqual(out["imported"], 2)
        ts = sorted(ev.tasks(), key=lambda t: t["started"])
        self.assertEqual([(t["platform"], t["model"], t["duration_s"]) for t in ts],
                         [("codex", "gpt-6.1-sol", 21.0), ("codex", "gpt-6.1-sol", 9.0)])
        self.assertEqual(ts[0]["pieces"], ["cut-a-release"])
        self.assertEqual(ts[1]["pieces"], [])
        self.assertEqual(ts[0]["request"], "Release 0.3.0")
        self.assertIsNotNone(ts[0]["tokens"])

    def test_import_is_idempotent(self):
        root = self.write("/work/greet", [("a", 5, None)])
        codex.import_sessions(root)
        self.assertEqual(codex.import_sessions(root)["imported"], 0)
        self.assertEqual(len(ev.tasks()), 1)

    def test_sessions_before_the_stores_import_since_are_left_out(self):
        from athos import paths
        root = self.write("/work/greet", [("a", 5, None)])
        (paths.home() / "import-since").write_text("2099-01-01T00:00:00Z\n")
        self.assertEqual(codex.import_sessions(root)["imported"], 0)
        (paths.home() / "import-since").unlink()
        self.assertEqual(codex.import_sessions(root)["imported"], 1)

    def test_test_runs_in_temporary_folders_are_left_out_unless_asked(self):
        root = self.write("/private/tmp/sandbox/greet", [("a", 5, None)])
        self.assertEqual(codex.import_sessions(root)["imported"], 0)
        self.assertEqual(codex.import_sessions(root, include_tmp=True)["imported"], 1)

    def test_sessions_the_hooks_recorded_are_not_imported_twice(self):
        ev.task_start({"session_id": "sess-1", "prompt": "a", "model": "gpt-6.1-sol"}, platform="codex")
        root = self.write("/work/greet", [("a", 5, None)])
        self.assertEqual(codex.import_sessions(root)["imported"], 0)


class SkillCatalogTest(TempHome):
    def test_the_skill_catalog_codex_injects_is_not_a_use(self):
        # Found live (2026-10-28): Codex lists every skill with its path in a developer message and in world_state
        # on each turn, so a task that read one skill was credited with all of them.
        store.create("Review a contract", "contracts", "x", piece_id="review-a-contract")
        store.create("Build an argument", "briefs", "x", piece_id="build-an-argument")
        text = rollout("/work/firm", [("Review this lease", 12, "review-a-contract")])
        catalog = " ".join(f".agents/skills/athos-{i}/SKILL.md" for i in ("review-a-contract", "build-an-argument"))
        extra = [{"timestamp": "2026-10-25T22:00:00.000Z", "type": "response_item",
                  "payload": {"type": "message", "role": "developer", "content": [{"type": "input_text",
                                                                                   "text": catalog}]}},
                 {"timestamp": "2026-10-25T22:00:00.000Z", "type": "world_state", "payload": {"skills": catalog}}]
        lines = text.splitlines()
        lines[3:3] = [json.dumps(x) for x in extra]                  # inside the turn, after task_started
        d = Path(self.home) / "sessions" / "2026" / "10" / "25"
        d.mkdir(parents=True, exist_ok=True)
        (d / "rollout-2026-10-25T22-00-00-sess-1.jsonl").write_text("\n".join(lines) + "\n")
        codex.import_sessions(Path(self.home) / "sessions")
        self.assertEqual(ev.tasks()[0]["pieces"], ["review-a-contract"])
