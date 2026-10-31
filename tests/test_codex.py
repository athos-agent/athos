"""The Codex adapter: hooks.json, skill export, token counts from rollouts and the import of past sessions."""

import json
import tempfile
from pathlib import Path
from unittest import mock

from athos import capture, eval as ev, paths, session, store
from athos.adapters import codex
from tests.helpers import TempHome

MODEL = "gpt-6.1-sol"
SESSION_FILE = "rollout-2026-10-25T22-00-00-sess-1.jsonl"


def jsonl(records) -> str:
    return "".join(json.dumps(r) + "\n" for r in records)


def usage_event(at, input_tokens, cached, output_tokens, **extra):
    """A `token_count` event carrying running totals, as Codex logs them."""
    totals = {"input_tokens": input_tokens, "cached_input_tokens": cached, "output_tokens": output_tokens,
              "total_tokens": input_tokens + output_tokens, **extra}
    return {"timestamp": at, "type": "event_msg", "payload": {"type": "token_count",
                                                               "info": {"total_token_usage": totals}}}


# One session whose task runs from 21:51:35 to 21:52:00: one report before it, two inside, one after.
USAGE_LOG = jsonl([
    {"timestamp": "2026-10-25T21:51:27.000Z", "type": "session_meta", "payload": {"id": "x"}},
    usage_event("2026-10-25T21:51:30.000Z", 1000, 800, 10, cache_write_input_tokens=0, reasoning_output_tokens=0),
    usage_event("2026-10-25T21:51:40.000Z", 3000, 2000, 50, cache_write_input_tokens=0, reasoning_output_tokens=0),
    usage_event("2026-10-25T21:51:50.000Z", 5000, 3500, 90, cache_write_input_tokens=0, reasoning_output_tokens=0),
    usage_event("2026-10-25T21:52:30.000Z", 9000, 7000, 200, cache_write_input_tokens=0, reasoning_output_tokens=0),
])
TASK_START, TASK_END = "2026-10-25T21:51:35+00:00", "2026-10-25T21:52:00+00:00"


def session_log(cwd, turns, extra_in_first_turn=()):
    """A rollout shaped like Codex 0.164.0 writes them: the session's meta, then for each (request, seconds, skill read)
    a task_started, its turn_context, the user's message, optionally a command reading an Athos skill, a token report
    and task_complete. `extra_in_first_turn` records go right after the first task_started."""
    meta = {"id": "sess-1", "cwd": cwd, "source": "exec"}                  # a session started with `codex exec`
    records = [{"timestamp": "2026-10-25T21:58:00.000Z", "type": "session_meta", "payload": meta}]
    for n, (request, seconds, skill) in enumerate(turns):
        opened, closed = f"2026-10-25T22:0{n}:00.000Z", f"2026-10-25T22:0{n}:{seconds:02d}.000Z"
        turn = f"turn-{n}"
        records.append({"timestamp": opened, "type": "event_msg", "payload": {"type": "task_started", "turn_id": turn}})
        if n == 0:
            records.extend(extra_in_first_turn)
        records.append({"timestamp": opened, "type": "turn_context", "payload": {"turn_id": turn, "model": MODEL}})
        records.append({"timestamp": opened, "type": "response_item", "payload": {
            "type": "message", "role": "user", "content": [{"type": "input_text", "text": request}]}})
        if skill:
            records.append({"timestamp": opened, "type": "response_item", "payload": {
                "type": "custom_tool_call", "input": f"cat .agents/skills/athos-{skill}/SKILL.md"}})
        spent = 1000 * (n + 1)
        records.append(usage_event(closed, spent, 0, 10))
        records.append({"timestamp": closed, "type": "event_msg", "payload": {
            "type": "task_complete", "turn_id": turn, "duration_ms": seconds * 1000}})
    return jsonl(records)


class TokenCountTest(TempHome):
    def test_a_task_costs_the_growth_of_the_running_totals_inside_it(self):
        log = Path(self.home) / "rollout.jsonl"
        log.write_text(USAGE_LOG)
        spent = codex.tokens_between(str(log), TASK_START, TASK_END)
        # Last report inside (5000/3500/90) minus the last one before (1000/800/10); cached input is not new input.
        self.assertEqual(spent, {"input": 1300, "output": 80, "cache_read": 2700, "cache_write": 0, "total": 4080})

    def test_a_zstd_rollout_is_found_from_its_plain_name(self):
        from compression import zstd
        with zstd.open(Path(self.home) / "rollout.jsonl.zst", "wt") as out:
            out.write(USAGE_LOG)
        spent = codex.tokens_between(str(Path(self.home) / "rollout.jsonl"), TASK_START, TASK_END)
        self.assertEqual(spent["total"], 4080)

    def test_no_rollout_means_no_count(self):
        for missing in (None, "/nonexistent.jsonl"):
            with self.subTest(rollout=missing):
                self.assertIsNone(codex.tokens_between(missing, "", ""))


class SkillExportTest(TempHome):
    def test_a_skill_carries_the_whole_piece(self):
        tag, commit = "Tag message `greet X.Y.Z`.", "Commit `release X.Y.Z`."
        piece = store.create("Cut a release", "release a new version: bump, changelog, tag", tag, projects=["greet"])
        store.update(piece.id, "added a step", body=f"{tag}\n{commit}")
        with tempfile.TemporaryDirectory() as out:
            result = codex.export_skills(Path(out))
            skill = (Path(out) / f"athos-{piece.id}" / "SKILL.md").read_text()
        self.assertEqual(result, (1, 0))
        self.assertTrue(skill.startswith(f"---\nname: athos-{piece.id}\ndescription: "))
        self.assertIn("Use when: release a new version", skill)
        for detail in (commit, "projects: [greet]", "version: 2", "added a step"):
            self.assertIn(detail, skill)

    def test_export_prunes_its_own_stale_skills_only(self):
        piece = store.create("Gone", "gone soon", "x")
        with tempfile.TemporaryDirectory() as out:
            codex.export_skills(Path(out))
            foreign = Path(out) / "someone-else" / "SKILL.md"
            foreign.parent.mkdir()
            foreign.write_text("---\nname: someone-else\n---\n")
            piece.path.unlink()
            self.assertEqual(codex.export_skills(Path(out)), (0, 1))
            self.assertTrue(foreign.is_file())


class HooksFileTest(TempHome):
    def test_install_twice_then_uninstall_leaves_only_what_was_there(self):
        hooks = Path(self.home) / "codex" / "hooks.json"
        hooks.parent.mkdir()
        mine = {"type": "command", "command": "echo mine"}
        original = {"hooks": {"Stop": [{"hooks": [mine]}]}}
        hooks.write_text(json.dumps(original))

        _, backup = codex.install(Path("/plugin"), hooks)
        self.assertEqual(json.loads(backup.read_text()), original)          # the file as it was before Athos
        codex.install(Path("/plugin"), hooks)
        installed = json.loads(hooks.read_text())
        self.assertIn(mine, installed["hooks"]["Stop"][0]["hooks"])
        ours_per_event = {name: sum(codex._is_ours(h) for group in installed["hooks"][name] for h in group["hooks"])
                          for name in codex.EVENTS}
        self.assertEqual(ours_per_event, dict.fromkeys(codex.EVENTS, 1))      # exactly one each, even after two installs
        self.assertTrue(codex.shim_path().stat().st_mode & 0o100, "the launcher must be executable")

        codex.uninstall(hooks)
        self.assertEqual(json.loads(hooks.read_text()), original)


class PlatformRecordTest(TempHome):
    def test_codex_sessions_are_credited_to_codex_and_its_model(self):
        sid = "c1"
        session.update(sid, platform="codex")
        ev.task_start({"session_id": sid, "prompt": "release", "model": MODEL}, platform="codex")
        note = "\n".join(["---", "title: T", "when: tt ww", "---", "body"])
        piece, _ = capture.save_text(note, sid)
        frozen = ev.now()
        with mock.patch.object(ev, "now", return_value=frozen):            # the task ends at the instant it closes
            ev.task_end({"session_id": sid})
        self.assertEqual(piece.origin, {"platform": "codex", "model": MODEL})
        row = ev.report()["models"][0]
        self.assertEqual((row["platform"], row["model"]), ("codex", MODEL))


class SessionImportTest(TempHome):
    def sessions(self, cwd, turns, extra_in_first_turn=()):
        """Write one session under a fake `~/.codex/sessions` and return that root."""
        root = Path(self.home) / "sessions"
        day = root / "2026" / "10" / "25"
        day.mkdir(parents=True, exist_ok=True)
        (day / SESSION_FILE).write_text(session_log(cwd, turns, extra_in_first_turn))
        return root

    def imported(self, root, **options) -> int:
        """Run the import and return how many turns it added."""
        return codex.import_sessions(root, **options)["imported"]

    def test_every_turn_is_recorded_with_model_time_tokens_and_pieces(self):
        store.create("Cut a release", "release a new version", "x", piece_id="cut-a-release")
        root = self.sessions("/work/greet", [("Release 0.3.0", 21, "cut-a-release"), ("now the docs", 9, None)])
        self.assertEqual(self.imported(root), 2)
        first, second = sorted(ev.tasks(), key=lambda t: t["started"])
        self.assertEqual([(t["platform"], t["model"], t["duration_s"]) for t in (first, second)],
                         [("codex", MODEL, 21.0), ("codex", MODEL, 9.0)])
        self.assertEqual((first["pieces"], second["pieces"]), (["cut-a-release"], []))
        self.assertEqual(first["request"], "Release 0.3.0")
        self.assertIsNotNone(first["tokens"])

    def test_a_second_import_adds_nothing(self):
        root = self.sessions("/work/greet", [("a", 5, None)])
        self.assertEqual([self.imported(root), self.imported(root)], [1, 0])
        self.assertEqual([t["request"] for t in ev.tasks()], ["a"])

    def test_import_since_holds_back_older_sessions(self):
        root = self.sessions("/work/greet", [("a", 5, None)])
        marker = paths.home() / "import-since"
        marker.write_text("2099-01-01T00:00:00Z\n")
        held_back = self.imported(root)
        marker.unlink()
        self.assertEqual((held_back, self.imported(root)), (0, 1))

    def test_sessions_in_temporary_folders_need_include_tmp(self):
        root = self.sessions("/private/tmp/sandbox/greet", [("a", 5, None)])
        self.assertEqual([self.imported(root), self.imported(root, include_tmp=True)], [0, 1])

    def test_sessions_already_seen_by_the_hooks_are_skipped(self):
        ev.task_start({"session_id": "sess-1", "prompt": "a", "model": MODEL}, platform="codex")
        root = self.sessions("/work/greet", [("a", 5, None)])
        self.assertFalse(self.imported(root))

    def test_the_skill_list_codex_shows_every_turn_does_not_count_as_reading(self):
        # Seen in a real session on 2026-10-28: Codex names every available skill, path included, in a developer
        # message and in world_state each turn; counting those credited one task with every skill.
        store.create("Review a contract", "contracts", "x", piece_id="review-a-contract")
        store.create("Build an argument", "briefs", "x", piece_id="build-an-argument")
        listing = " ".join(f".agents/skills/athos-{i}/SKILL.md" for i in ("review-a-contract", "build-an-argument"))
        at = "2026-10-25T22:00:00.000Z"
        shown = [{"timestamp": at, "type": "response_item", "payload": {
                     "type": "message", "role": "developer", "content": [{"type": "input_text", "text": listing}]}},
                 {"timestamp": at, "type": "world_state", "payload": {"skills": listing}}]
        root = self.sessions("/work/firm", [("Review this lease", 12, "review-a-contract")], shown)
        self.imported(root)
        self.assertEqual(ev.tasks()[0]["pieces"], ["review-a-contract"])
