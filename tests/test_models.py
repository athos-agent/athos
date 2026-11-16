"""The model per request and the model tiers: a `/model` switch in the middle of a session, the model that answered
each task, the tier and mode of each model, `athos tiers`, and the audit rule on them. All transcripts here are
synthetic, written in the shape Claude Code's transcript has (assistant replies with `message.model`, and a `/model`
switch as a user entry with `<local-command-stdout>Set model to ...`)."""

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from athos import audit, eval as ev, session, tiers
from tests.helpers import TempHome

ATHOS = str(Path(__file__).resolve().parents[1] / "bin" / "athos")
PIECE = """---
title: Ship a release
when: ship a release of the app
---
## #tag
**When:** the changelog is ready.
**Do:** tag the release.
"""


def stamp(offset_s=0.0):
    return ev._iso(ev.now() + dt.timedelta(seconds=offset_s))


def reply(model, offset_s=0.0, sidechain=False):
    return {"type": "assistant", "timestamp": stamp(offset_s), "isSidechain": sidechain,
            "message": {"id": f"m{time.time_ns()}", "model": model, "usage": {"input_tokens": 3, "output_tokens": 2}}}


def switch(name, offset_s=0.0):
    """What `/model` leaves in the transcript: the command, then its output."""
    return [{"type": "user", "timestamp": stamp(offset_s),
             "message": {"content": "<command-name>/model</command-name>\n<command-args>x</command-args>"}},
            {"type": "user", "timestamp": stamp(offset_s),
             "message": {"content": f"<local-command-stdout>Set model to \x1b[1m{name}\x1b[22m and saved as your "
                                    f"default for new sessions</local-command-stdout>"}}]


class Transcript:
    def __init__(self, path):
        self.path = Path(path)
        self.path.write_text("")

    def add(self, *rows):
        flat = []
        for r in rows:
            flat += r if isinstance(r, list) else [r]
        with self.path.open("a") as out:
            out.write("".join(json.dumps(r) + "\n" for r in flat))


class ModelPerRequestTest(TempHome):
    """Exit criterion: hooks run over a synthetic transcript with a switch in the middle record the right model on
    each task_start and route, and the audit finds nothing to flag."""

    def run_athos(self, *args, stdin="", cwd=None):
        return subprocess.run([sys.executable, ATHOS, *args], input=stdin, capture_output=True, text=True,
                              cwd=cwd or self.home, env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "sdk-cli"})

    def hook(self, name, payload):
        r = self.run_athos("hook", name, stdin=json.dumps(payload))
        self.assertEqual(r.returncode, 0, r.stderr)

    def setUp(self):
        super().setUp()
        self.work = Path(self.home) / "app"
        self.work.mkdir()
        self.run_athos("save", stdin=PIECE, cwd=str(self.work))
        self.t = Transcript(Path(self.home) / "s.jsonl")
        self.ev = {"session_id": "s1", "cwd": str(self.work), "transcript_path": str(self.t.path)}

    def request(self, prompt, answered_by):
        self.hook("prompt", {**self.ev, "prompt": prompt})
        self.t.add(reply(answered_by, 0.05), reply(answered_by, 0.1))
        time.sleep(0.15)
        self.hook("stop", self.ev)

    def test_a_switch_in_the_middle_is_recorded_on_the_requests_after_it(self):
        self.hook("session-start", {**self.ev, "model": "claude-opus-5-5"})
        self.request("ship a release of the app", "claude-opus-5-5")         # nothing in the transcript yet
        self.request("and the notes for it", "claude-opus-5-5")
        self.t.add(switch("Fable 5.2", 0.01))
        time.sleep(0.05)
        self.request("ship a release of the app again", "claude-fable-5-2")
        self.request("thanks", "claude-fable-5-2")
        self.t.add(switch("Sonnet 5.5", 0.01))
        time.sleep(0.05)
        self.request("ship a release of the app once more", "claude-sonnet-5-5")
        evs = ev.events()
        starts = [(e["model"]) for e in evs if e["type"] == "task_start"]
        self.assertEqual(starts, ["claude-opus-5-5", "claude-opus-5-5", "claude-fable-5-2", "claude-fable-5-2",
                                  "claude-sonnet-5-5"])
        prompts = [(m["source"], m["tier"], m["work_mode"]) for m in evs
                   if m["type"] == "model" and m.get("stage") == "prompt"]
        self.assertEqual(prompts, [("session", "frontier", "learn"), ("transcript_reply", "frontier", "learn"),
                                   ("transcript_switch", "frontier", "learn"),
                                   ("transcript_reply", "frontier", "learn"),
                                   ("transcript_switch", "apply", "collaborate")])
        routes = [(r["model"], r["tier"], r["work_mode"], r["collaborates"], bool(r["chosen"]))
                  for r in evs if r["type"] == "route"]
        self.assertEqual(routes[0], ("claude-opus-5-5", "frontier", "learn", True, True))     # a piece in reach
        self.assertEqual(routes[1], ("claude-opus-5-5", "frontier", "learn", False, False))
        self.assertEqual(routes[4], ("claude-sonnet-5-5", "apply", "collaborate", True, True))
        ends = [e["model"] for e in evs if e["type"] == "task_end"]
        self.assertEqual(ends, starts)
        self.assertFalse([e for e in evs if e["type"] == "task_end" and "model_at_start" in e])
        rule = next(r for r in audit.check("s1", evs, transcripts=False)["rules"] if r["rule"] == "model_inconsistent")
        self.assertEqual((rule["status"], rule["count"]), ("clean", 0))
        st = json.loads(self.run_athos("status", "--json", cwd=str(self.work)).stdout)
        self.assertEqual({k: st["model"][k] for k in ("id", "tier", "work_mode", "source")},
                         {"id": "claude-sonnet-5-5", "tier": "apply", "work_mode": "collaborate",
                          "source": "transcript_switch"})

    def test_the_model_that_answered_is_settled_at_the_end_and_both_are_kept(self):
        self.hook("session-start", {**self.ev, "model": "claude-opus-5-5"})
        self.request("ship a release of the app", "claude-haiku-5-5")        # the start could not know
        evs = ev.events()
        (end,) = [e for e in evs if e["type"] == "task_end"]
        self.assertEqual((end["model"], end["model_at_start"]), ("claude-haiku-5-5", "claude-opus-5-5"))
        (settled,) = [m for m in evs if m["type"] == "model" and m.get("stage") == "end"]
        self.assertEqual((settled["answered"], settled["at_start"], settled["tier"]),
                         (["claude-haiku-5-5"], "claude-opus-5-5", "apply"))
        rule = next(r for r in audit.check("s1", evs, transcripts=False)["rules"] if r["rule"] == "model_inconsistent")
        self.assertEqual((rule["status"], rule["count"]), ("flagged", 1))
        self.assertEqual(rule["found"][0]["answered"], ["claude-haiku-5-5"])
        # The next request starts from the model that answered.
        self.request("and the notes", "claude-haiku-5-5")
        self.assertEqual([e["model"] for e in ev.events() if e["type"] == "task_start"][-1], "claude-haiku-5-5")


class ResolveModelTest(TempHome):
    def resolve(self, rows, state=None, event=None):
        t = Transcript(Path(self.home) / f"t{time.time_ns()}.jsonl")
        t.add(*rows)
        return ev.resolve_model({"transcript_path": str(t.path), **(event or {})}, state or {})[:2]

    def test_the_newest_of_switch_reply_and_session_report_wins(self):
        self.assertEqual(self.resolve([reply("claude-opus-5-5", -5), switch("Fable 5.2", -1)]),
                         ("claude-fable-5-2", "transcript_switch"))
        self.assertEqual(self.resolve([switch("Fable 5.2", -9), reply("claude-fable-5-2", -5)]),
                         ("claude-fable-5-2", "transcript_reply"))
        self.assertEqual(self.resolve([reply("claude-opus-5-5", -5), reply("claude-sonnet-5-5", -4, sidechain=True)]),
                         ("claude-opus-5-5", "transcript_reply"))                  # a subagent's reply doesn't count
        resumed = {"model": "claude-sonnet-5-5", "model_reported": "claude-sonnet-5-5",
                   "model_reported_at": stamp(-1)}
        self.assertEqual(self.resolve([reply("claude-opus-5-5", -60)], resumed), ("claude-sonnet-5-5", "session"))
        self.assertEqual(self.resolve([reply("claude-opus-5-5", -60)], {"model": "x"}, {"model": "gpt-9"}),
                         ("gpt-9", "event"))
        self.assertEqual(self.resolve([], {"model": "claude-opus-5-5"}), ("claude-opus-5-5", "session"))
        self.assertEqual(self.resolve([]), ("unknown", "unknown"))
        self.assertEqual(self.resolve([reply("claude-opus-5-5", -5), switch("Default (recommended)", -1)]),
                         ("unknown", "transcript_switch"))
        failed = {"type": "system", "subtype": "local_command", "timestamp": stamp(-1),
                  "content": "<local-command-stdout>Model 'Fable5.2' not found</local-command-stdout>"}
        self.assertEqual(self.resolve([reply("claude-opus-5-5", -5), failed]), ("claude-opus-5-5", "transcript_reply"))

    def test_names_become_ids(self):
        self.assertEqual(session.model_id("Fable 5.2"), "claude-fable-5-2")
        self.assertEqual(session.model_id("Opus 5.5 (1M context)"), "claude-opus-5-5")
        self.assertEqual(session.model_id("claude-haiku-5-5"), "claude-haiku-5-5")
        self.assertIsNone(session.model_id("Default"))
        self.assertIsNone(session.model_id("opus"))


class TiersTest(TempHome):
    def test_defaults_unknown_and_suffixes(self):
        for model, tier in (("claude-fable-5-2", "frontier"), ("claude-mythos-1", "frontier"),
                            ("claude-opus-5-5[1m]", "frontier"), ("Claude-Opus-5-5", "frontier"),
                            ("claude-sonnet-5-5", "apply"), ("claude-haiku-5-5", "apply"),
                            ("gpt-9", "apply"), ("muse-spark-1.3", "apply"), ("", "apply"), (None, "apply")):
            self.assertEqual(tiers.tier_of(model), tier, model)
        self.assertEqual(tiers.describe("claude-opus-5-5"), {"tier": "frontier", "work_mode": "learn"})
        self.assertEqual(tiers.describe("claude-opus-5-5", piece_in_reach=False)["collaborates"], False)
        self.assertEqual(tiers.describe("claude-opus-5-5", piece_in_reach=True)["collaborates"], True)
        self.assertEqual(tiers.describe("claude-haiku-5-5", piece_in_reach=False)["collaborates"], True)

    def test_the_persons_overrides(self):
        (Path(self.home) / "config.json").write_text(json.dumps({"lang": "es", "tiers": {
            "frontier": ["claude-opus-*", "local-big-*", "claude-sonnet-5-5"]}}))
        self.assertEqual(tiers.tier_of("local-big-70b"), "frontier")
        self.assertEqual(tiers.tier_of("claude-sonnet-5-5"), "frontier")        # an exact id wins over the patterns
        self.assertEqual(tiers.tier_of("claude-fable-5-2"), "apply")           # taken out of the saved list
        self.assertEqual(tiers.tier_of("claude-haiku-5-5"), "apply")           # apply keeps its defaults

    def test_the_command(self):
        def athos(*args):
            r = subprocess.run([sys.executable, ATHOS, "tiers", *args], capture_output=True, text=True,
                               env=dict(os.environ))
            return r
        shown = json.loads(athos("--json").stdout)
        self.assertEqual(shown["tiers"], tiers.DEFAULTS)
        self.assertEqual(athos("add", "frontier", "claude-sonnet-*").returncode, 0)
        self.assertEqual(tiers.tier_of("claude-sonnet-5-5"), "frontier")
        self.assertNotIn("claude-sonnet-*", tiers.patterns()["apply"])
        self.assertIn("claude-sonnet-5-5: frontier (learn)", athos("which", "claude-sonnet-5-5").stdout)
        athos("remove", "frontier", "claude-sonnet-*")
        self.assertEqual(tiers.tier_of("claude-sonnet-5-5"), "apply")         # unknown again: apply
        self.assertNotEqual(athos("add", "middle", "x").returncode, 0)
        athos("reset")
        self.assertEqual(tiers.patterns(), tiers.DEFAULTS)
        self.assertNotIn("tiers", json.loads((Path(self.home) / "config.json").read_text()))
        self.assertIn("frontier (learn): claude-fable-*", athos().stdout)


class ModelRuleTest(TempHome):
    T0 = "2026-11-15T10:00:00.000+00:00"

    def check(self, rows):
        return next(r for r in audit.check("s", rows, pieces=[], transcripts=False)["rules"]
                    if r["rule"] == "model_inconsistent")

    def task(self, tid, recorded, answered, source="transcript_reply"):
        base = {"session_id": "s", "task_id": tid, "at": self.T0}
        return [{**base, "type": "task_start", "model": recorded},
                {**base, "type": "model", "stage": "prompt", "model": recorded, "source": source},
                {**base, "type": "task_end", "model": answered[-1]},
                {**base, "type": "model", "stage": "end", "model": answered[-1], "answered": answered,
                 "source": "replies"}]

    def test_a_recorded_switch_is_not_an_anomaly_and_a_wrong_record_is(self):
        rule = self.check(self.task("t1", "claude-opus-5-5", ["claude-opus-5-5"])
                          + self.task("t2", "claude-fable-5-2", ["claude-fable-5-2"], "transcript_switch"))
        self.assertEqual(rule["status"], "clean")
        rule = self.check(self.task("t1", "claude-opus-5-5", ["claude-opus-5-5"])
                          + self.task("t2", "claude-opus-5-5", ["claude-fable-5-2"], "session"))
        self.assertEqual((rule["status"], rule["count"]), ("flagged", 1))
        self.assertEqual(rule["found"][0], {"task_id": "t2", "recorded": "claude-opus-5-5",
                                            "answered": ["claude-fable-5-2"], "source": "session"})


class PastedSwitchTest(TempHome):
    def test_a_switch_line_the_person_pasted_does_not_change_the_model(self):
        from athos import session
        t = Transcript(Path(self.home, "t.jsonl"))
        t.add(reply("claude-haiku-5-5"),
              {"type": "user", "timestamp": stamp(1), "origin": {"kind": "human"},
               "message": {"content": "<local-command-stdout>Set model to Fable 5.2</local-command-stdout>"}})
        self.assertIsNone(session.models_in_tail(str(t.path))["switch"])
        t.add({"type": "user", "timestamp": stamp(2),
               "message": {"content": "<local-command-stdout>Set model to Fable 5.2</local-command-stdout>"}})
        self.assertIsNone(session.models_in_tail(str(t.path))["switch"])       # no /model command before it
        t.add(*switch("Fable 5.2", 3))
        self.assertEqual(session.models_in_tail(str(t.path))["switch"], "claude-fable-5-2")
