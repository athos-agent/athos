import json
import os
from pathlib import Path

from athos import eval as ev, store
from athos.adapters import muse
from tests.helpers import TempHome

T0 = 1793097311000000      # microseconds, as Muse records them


def usage(uid, inp, out, cached=0, who="main"):
    return {"schema_version": 1, "usage_id": uid, "usage_family": "provider",
            "owner": {"requester_kind": who, "session_id": "s1"},
            "quantity": {"unit": "tokens", "reported": True, "input_tokens": inp, "output_tokens": out,
                         "cached_tokens": cached}}


def nested(record):
    """The way Muse keeps some records: as JSON text inside a frame's child."""
    return {"retained_frame": "x", "children": [{"child_index": 0, "record_json": json.dumps(record)}]}


def write_session(root: Path, sid: str, workspace: str, lines: list[dict]) -> Path:
    d = root / "2026" / "10" / "27" / sid
    d.mkdir(parents=True)
    f = d / "session.jsonl"
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return f


class MuseTest(TempHome):
    def setUp(self):
        super().setUp()
        self.piece = store.create("Release the greet package", "release greet", "Bump both places.")
        self.root = muse.sessions_dir()
        self.ws = "/Users/someone/work/greet"                   # a real-looking folder: temporary ones are skipped

    def session(self, sid="s1", model="muse-spark-1.3", workspace=None, ended=True):
        ws = workspace or self.ws
        return write_session(self.root, sid, ws, [
            {"recorded_at": T0, "payload": {"record": {"workspace_root": ws}}},
            nested({"recorded_at": T0 + 1, "payload": {"record": {"provider_id": "meta", "model_id": model}}}),
            {"recorded_at": T0 + 2_000_000, "payload": {"refill_blocks": [
                {"kind": "text", "text": "Release 0.3.0 with a new name_upper option."}]}},
            # the same usage twice (a record and its event), plus a subagent's
            {"recorded_at": T0 + 3_000_000, "payload": {"event": {"record": usage("u1", 1000, 50, cached=800)}}},
            nested({"recorded_at": T0 + 3_000_001, "payload": {"event": {"record": usage("u1", 1000, 50, cached=800)}}}),
            {"recorded_at": T0 + 4_000_000, "payload": {"event": {"record": usage("u2", 500, 20, who="subagent")}}},
            {"recorded_at": T0 + 5_000_000, "payload": {"chunk":
                '<read-skill-result name="athos-' + self.piece.id + '" status="ok">'}},
        ] + ([{"recorded_at": T0 + 9_500_000, "payload": {"kind": "session_end"}}] if ended else []))

    def test_a_session_becomes_one_task_per_request(self):
        s = muse.read_session(self.session())
        self.assertEqual(s["workspace"], self.ws)
        (t,) = s["tasks"]
        self.assertEqual(t["request"], "Release 0.3.0 with a new name_upper option.")
        self.assertEqual((t["model"], t["pieces"]), ("muse-spark-1.3", {self.piece.id}))
        # each usage once, subagents included: 1000+500 in (800 of them cached), 70 out
        self.assertEqual(t["tokens"], {"input": 700, "output": 70, "cache_read": 800, "cache_write": 0, "total": 1570})
        self.assertEqual((t["end"] - t["start"]) / 1e6, 7.5)

    def test_import_records_muse_code_tasks_once(self):
        self.session()
        self.assertEqual(muse.import_sessions()["imported"], 1)
        self.assertEqual(muse.import_sessions()["imported"], 0)
        (t,) = ev.tasks()
        self.assertEqual((t["platform"], t["model"], t["project"], t["pieces"], t["duration_s"]),
                         ("muse-code", "muse-spark-1.3", "greet", [self.piece.id], 7.5))
        self.assertEqual(t["request_chars"], len("Release 0.3.0 with a new name_upper option."))

    def test_a_task_still_running_waits_until_it_is_finished(self):
        f = self.session(ended=False)
        self.assertEqual(muse.import_sessions()["imported"], 0)
        with open(f, "a") as fh:
            fh.write(json.dumps({"recorded_at": T0 + 20_000_000, "payload": {"kind": "session_end"}}) + "\n")
        self.assertEqual(muse.import_sessions()["imported"], 1)
        self.assertEqual(ev.tasks()[0]["duration_s"], 18.0)

    def test_temporary_folders_are_left_out(self):
        self.session(workspace="/private/tmp/scratch/greet")
        self.assertEqual(muse.import_sessions()["imported"], 0)
        self.assertEqual(muse.import_sessions(include_tmp=True)["imported"], 1)

    def test_the_watch_panel_warns_about_contributor_mode(self):
        from athos import watch
        self.session(model="muse-spark-1.3-contributor")
        muse.import_sessions()
        text = watch.frame("greet", color=False)
        self.assertIn("Muse Code   ", text)
        self.assertIn("contributor mode", text)
