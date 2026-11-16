"""The model of a session's first request. Claude Code's headless SessionStart and every UserPromptSubmit carry no
`model`, and on the first prompt the transcript file does not exist yet. The first trace of the model that answers is
the transcript's `api-request` row (`params.model`), written before any reply: at the first tool hook of a turn with
tools, and at Stop of a turn without one (where no `assistant` row exists yet). Assistant rows carry `advisorModel`
(another model: an advisor, never the one answering), and a subagent's requests live in its own file, with only
`toolUseResult.resolvedModel` left in the main one. All transcripts here are synthetic, in that shape."""

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

from athos import audit, autolearn, eval as ev, session, tiers
from tests.helpers import TempHome

ATHOS = str(Path(__file__).resolve().parents[1] / "bin" / "athos")
PIECE = """---
title: Ship a release
when: ship a release of the app
---
## #tag
**When:** the changelog is ready.
**Do:** tag the release, then `git tag -l` shows it.
"""


def stamp(offset_s=0.0):
    return ev._iso(ev.now() + dt.timedelta(seconds=offset_s))


def api_request(model, offset_s=0.0, source="sdk", agent=False):
    row = {"type": "api-request", "timestamp": stamp(offset_s), "querySource": source,
           "params": {"model": model, "max_tokens": 10}}
    if agent:
        row["agentId"] = "a1"
    return row


def shape(advisor="claude-opus-5-5", offset_s=0.0):
    return {"type": "api-request-shape", "timestamp": stamp(offset_s), "shape": {"tools": [{"model": advisor}]}}


def identity(model, offset_s=0.0):
    return {"type": "attachment", "timestamp": stamp(offset_s), "isSidechain": False,
            "attachment": {"type": "model", "identity": {"modelId": model}}}


def reply(model, offset_s=0.0, advisor="claude-opus-5-5"):
    return {"type": "assistant", "timestamp": stamp(offset_s), "isSidechain": False, "requestedModel": model,
            "advisorModel": advisor,
            "message": {"id": f"m{time.time_ns()}", "model": model, "usage": {"input_tokens": 3, "output_tokens": 2}}}


def subagent_result(model, offset_s=0.0):
    return {"type": "user", "timestamp": stamp(offset_s), "isSidechain": False,
            "toolUseResult": {"resolvedModel": model}, "message": {"content": [{"type": "tool_result"}]}}


class Transcript:
    """A transcript that does not exist until the first row is written, as in Claude Code."""

    def __init__(self, path):
        self.path = Path(path)

    def add(self, *rows):
        with self.path.open("a") as out:
            out.write("".join(json.dumps(r) + "\n" for r in rows))


class FirstRequestCase(TempHome):
    def setUp(self):
        super().setUp()
        self.claude = Path(os.environ["CLAUDE_CONFIG_DIR"])      # TempHome's own
        self.claude.mkdir(exist_ok=True)
        self.work = Path(self.home) / "app"
        self.work.mkdir()
        subprocess.run(["git", "init", "-q", str(self.work)], check=True)
        self.athos("save", stdin=PIECE, cwd=str(self.work), env={"CLAUDECODE": ""})
        self.t = Transcript(Path(self.home) / "s.jsonl")
        self.ev = {"session_id": "s1", "cwd": str(self.work), "transcript_path": str(self.t.path)}

    def default_model(self, model):
        (self.claude / "settings.json").write_text(json.dumps({"model": model, "theme": "dark"}))

    def athos(self, *args, stdin="", cwd=None, env=None):
        full = {**os.environ, "CLAUDE_CODE_ENTRYPOINT": "sdk-cli", **(env or {})}
        return subprocess.run([sys.executable, ATHOS, *args], input=stdin, capture_output=True, text=True,
                              cwd=cwd or self.home, env=full)

    def hook(self, name, extra=None):
        r = self.athos("hook", name, stdin=json.dumps({**self.ev, **(extra or {})}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("athos hook", r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def tool(self, command="git status"):
        call = {"tool_name": "Bash", "tool_input": {"command": command}, "tool_use_id": f"t{time.time_ns()}"}
        self.hook("tool-start", call)
        return self.hook("tool", {**call, "tool_response": {"stdout": "", "exit_code": 0}})

    def models(self, stage=None):
        return [m for m in ev.events() if m["type"] == "model" and (stage is None or m.get("stage") == stage)]


class ReproduceTest(FirstRequestCase):
    """What the live test showed: on a headless session Athos never learned the model of a single-prompt session, and
    decided the first request of every session on `unknown`."""

    def test_a_single_prompt_session_settles_the_model_from_the_request_row_at_stop(self):
        self.hook("session-start", {"source": "startup"})
        self.assertFalse(self.t.path.exists())
        self.hook("prompt", {"prompt": "ship a release of the app"})
        # The turn ran without tools: at Stop the transcript has the request row and no reply yet.
        self.t.add(identity("claude-opus-5-5"), shape(), api_request("claude-opus-5-5", 0.01))
        time.sleep(0.05)
        self.hook("stop", {"stop_hook_active": False})
        (end,) = [e for e in ev.events() if e["type"] == "task_end"]
        self.assertEqual(end["model"], "claude-opus-5-5")
        self.assertEqual(session.load("s1")["model"], "claude-opus-5-5")

    def test_the_first_tool_hook_corrects_an_unknown_model(self):
        self.hook("session-start", {"source": "startup"})
        self.hook("prompt", {"prompt": "ship a release of the app"})
        self.t.add(identity("claude-haiku-5-5"), shape(), api_request("claude-haiku-5-5", 0.01))
        self.tool()
        state = session.load("s1")
        self.assertEqual((state["model"], state["model_source"]), ("claude-haiku-5-5", "transcript_request"))
        fixed = [m for m in self.models() if m.get("stage") in ("tool_start", "tool")]
        self.assertEqual(len(fixed), 1)
        self.assertEqual((fixed[0]["model"], fixed[0]["tier"], fixed[0]["observed"], fixed[0]["corrects"]),
                         ("claude-haiku-5-5", "apply", True, "unknown"))


class TranscriptSourcesTest(TempHome):
    def tail(self, *rows):
        t = Transcript(Path(self.home) / f"t{time.time_ns()}.jsonl")
        t.add(*rows)
        return session.models_in_tail(str(t.path))

    def resolve(self, *rows):
        t = Transcript(Path(self.home) / f"t{time.time_ns()}.jsonl")
        t.add(*rows)
        return ev.resolve_model({"transcript_path": str(t.path)}, {})[:2]

    def test_the_request_row_is_read_when_no_reply_exists(self):
        self.assertEqual(self.resolve(api_request("claude-opus-5-5")), ("claude-opus-5-5", "transcript_request"))
        self.assertEqual(self.resolve(identity("claude-opus-5-5")), ("claude-opus-5-5", "transcript_request"))

    def test_never_the_advisor(self):
        self.assertEqual(self.resolve(shape("claude-opus-5-5", -3), api_request("claude-haiku-5-5", -2),
                                      reply("claude-haiku-5-5", -1, advisor="claude-opus-5-5")),
                         ("claude-haiku-5-5", "transcript_reply"))
        self.assertEqual(self.resolve(shape("claude-opus-5-5")), ("unknown", "unknown"))

    def test_never_a_subagent(self):
        rows = (api_request("claude-haiku-5-5", -3), reply("claude-haiku-5-5", -2),
                api_request("claude-sonnet-5-5", -1, source="agent:builtin:general-purpose"),
                api_request("claude-sonnet-5-5", -1, agent=True), subagent_result("claude-sonnet-5-5", -0.5))
        self.assertEqual(self.resolve(*rows), ("claude-haiku-5-5", "transcript_reply"))
        self.assertEqual(self.tail(*rows)["request"], "claude-haiku-5-5")

    def test_a_request_of_unknown_origin_is_not_taken(self):
        # A request row whose source is neither the headless nor the interactive main thread (a title, a compaction
        # or a source a future version adds) may be another model's.
        self.assertEqual(self.resolve(api_request("claude-haiku-5-5", source="compact")), ("unknown", "unknown"))
        self.assertEqual(self.resolve(api_request("claude-haiku-5-5", source="repl_main_thread")),
                         ("claude-haiku-5-5", "transcript_request"))

    def test_a_switch_after_the_last_request_still_wins(self):
        from tests.test_models import switch
        self.assertEqual(self.resolve(api_request("claude-haiku-5-5", -5), reply("claude-haiku-5-5", -4),
                                      *switch("Opus 5.5", -1)), ("claude-opus-5-5", "transcript_switch"))
        self.assertEqual(self.resolve(*switch("Opus 5.5", -9), api_request("claude-opus-5-5", -1)),
                         ("claude-opus-5-5", "transcript_request"))


class ProvisionalTest(FirstRequestCase):
    """When nothing has been observed yet, the person's configured default model is a provisional guess: it chooses
    the delivery and the guide, never a save."""

    def test_the_configured_default_is_a_guess_with_its_own_source(self):
        self.default_model("opus")
        self.hook("session-start", {"source": "startup"})
        self.hook("prompt", {"prompt": "ship a release of the app"})
        (prompt,) = self.models("prompt")
        self.assertEqual((prompt["model"], prompt["source"], prompt["observed"], prompt["tier"]),
                         ("opus", "settings", False, "frontier"))
        (route,) = [r for r in ev.events() if r["type"] == "route"]
        self.assertEqual((route["tier"], route["delivery"], route["model_source"], route["model_observed"]),
                         ("frontier", "index", "settings", False))

    def test_project_settings_beat_the_users(self):
        self.default_model("opus")
        (self.work / ".claude").mkdir()
        (self.work / ".claude" / "settings.json").write_text(json.dumps({"model": "haiku"}))
        self.assertEqual(session.configured_model(str(self.work))[:2], ("haiku", "settings"))
        (self.work / ".claude" / "settings.local.json").write_text(json.dumps({"model": "claude-fable-5-2"}))
        self.assertEqual(session.configured_model(str(self.work))[:2], ("claude-fable-5-2", "settings"))
        with mock.patch.dict(os.environ, {"ANTHROPIC_MODEL": "sonnet"}):
            self.assertEqual(session.configured_model(str(self.work))[:2], ("sonnet", "env"))

    def test_the_launch_flag(self):
        self.assertEqual(session.model_flag(["claude", "-p", "hi", "--model", "haiku"]), "haiku")
        self.assertEqual(session.model_flag(["claude", "--model=claude-opus-5-5[1m]", "-p"]), "claude-opus-5-5[1m]")
        self.assertIsNone(session.model_flag(["claude", "-p", "hi"]))
        self.assertIsNone(session.model_flag(["claude", "--model", "not a model; rm"]))

    def test_aliases_have_a_tier(self):
        for alias, tier in (("opus", "frontier"), ("fable", "frontier"), ("opus[1m]", "frontier"),
                            ("haiku", "apply"), ("sonnet", "apply"), ("opusplan", "apply"), ("default", "apply")):
            self.assertEqual(tiers.tier_of(alias), tier, alias)

    def test_no_save_on_a_guess_and_a_save_once_observed(self):
        self.default_model("opus")
        self.hook("session-start", {"source": "startup"})
        self.hook("prompt", {"prompt": "ship a release of the app"})
        refused = autolearn.refuse_model_save("s1")
        self.assertIsNotNone(refused)
        self.assertIn("guess", refused)
        learn = [e for e in ev.events() if e["type"] == "learn"][-1]
        self.assertEqual(learn["reason"], "model_guessed")
        self.t.add(api_request("claude-opus-5-5", 0.01))
        self.tool()
        self.assertIsNone(autolearn.refuse_model_save("s1"))

    def test_a_save_command_reads_the_transcript_itself(self):
        self.default_model("opus")
        self.hook("session-start", {"source": "startup"})
        self.hook("prompt", {"prompt": "ship a release of the app"})
        self.t.add(api_request("claude-opus-5-5", 0.01))
        r = self.athos("save", "--auto", stdin=PIECE.replace("Ship a release", "Tag a release"), cwd=str(self.work),
                       env={"CLAUDE_CODE_SESSION_ID": "s1", "CLAUDECODE": "1"})
        self.assertNotIn("guess", r.stdout + r.stderr)          # refused, if at all, for its evidence, not its model
        self.assertTrue(session.observed(session.load("s1")))

    def test_unknown_stays_apply_and_never_saves(self):
        self.hook("session-start", {"source": "startup"})
        self.hook("prompt", {"prompt": "ship a release of the app"})
        (prompt,) = self.models("prompt")
        self.assertEqual((prompt["model"], prompt["source"], prompt["tier"]), ("unknown", "unknown", "apply"))
        (route,) = [r for r in ev.events() if r["type"] == "route"]
        self.assertNotEqual(route["delivery"], "index")
        self.assertIsNotNone(autolearn.refuse_model_save("s1"))


class LateGuideTest(FirstRequestCase):
    def guide_text(self, out):
        return ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext") or ""

    def test_a_frontier_session_guessed_apply_gets_the_guide_at_the_first_tool_hook_once(self):
        self.default_model("haiku")
        out = self.hook("session-start", {"source": "startup"})
        self.assertNotIn("save --auto", self.guide_text(out))           # an apply guess: no guide
        self.hook("prompt", {"prompt": "ship a release of the app"})
        self.t.add(api_request("claude-opus-5-5", 0.01))
        first = self.tool()
        self.assertEqual(first["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("save --auto", self.guide_text(first))
        self.assertIsNone(self.tool())                                    # once
        self.assertEqual(session.load("s1")["guide"], "auto")
        out = self.hook("prompt", {"prompt": "and the notes for it"})
        self.assertNotIn("save --auto", self.guide_text(out))

    def test_an_apply_session_guessed_frontier_saves_nothing_and_is_not_asked(self):
        self.default_model("opus")
        out = self.hook("session-start", {"source": "startup"})
        self.assertIn("save --auto", self.guide_text(out))               # the guess chose the guide
        self.hook("prompt", {"prompt": "ship a release of the app"})
        self.t.add(api_request("claude-haiku-5-5", 0.01))
        told = self.guide_text(self.tool())
        self.assertIn("claude-haiku-5-5", told)
        self.assertNotIn("save --auto", told)
        self.assertIn("do not save", told)
        self.assertIsNone(self.tool())                                    # said once
        self.assertIsNotNone(autolearn.refuse_model_save("s1"))
        for i in range(5):                                                # work that would qualify on frontier
            self.tool(f"git commit -m step{i}")
        self.assertIsNone(self.hook("stop", {"stop_hook_active": False}))
        self.assertEqual(session.load("s1")["model"], "claude-haiku-5-5")
        (end,) = [e for e in ev.events() if e["type"] == "task_end"]
        self.assertEqual((end["model"], end["model_at_start"]), ("claude-haiku-5-5", "opus"))


class AuditTest(TempHome):
    T0 = "2026-11-15T10:00:00.000+00:00"

    def check(self, rows):
        return next(r for r in audit.check("s", rows, pieces=[], transcripts=False)["rules"]
                    if r["rule"] == "model_inconsistent")

    def task(self, tid, recorded, source, observed, fixed=None, answered=None):
        base = {"session_id": "s", "task_id": tid, "at": self.T0}
        rows = [{**base, "type": "task_start", "model": recorded},
                {**base, "type": "model", "stage": "prompt", "model": recorded, "source": source,
                 "observed": observed}]
        if fixed:
            rows.append({**base, "type": "model", "stage": "tool", "model": fixed, "source": "transcript_request",
                         "observed": True, "corrects": recorded})
        if answered:
            rows += [{**base, "type": "task_end", "model": answered[-1]},
                     {**base, "type": "model", "stage": "end", "model": answered[-1], "answered": answered,
                      "source": "replies", "observed": True}]
        return rows

    def test_a_corrected_guess_is_not_flagged_and_guesses_are_counted(self):
        rule = self.check(self.task("t1", "opus", "settings", False, "claude-opus-5-5", ["claude-opus-5-5"])
                          + self.task("t2", "unknown", "unknown", False, "claude-opus-5-5", ["claude-opus-5-5"])
                          + self.task("t3", "claude-opus-5-5", "transcript_reply", True, None, ["claude-opus-5-5"]))
        self.assertEqual((rule["status"], rule["count"]), ("clean", 0))
        self.assertEqual(rule["decided_on_guess"], 2)

    def test_a_guess_that_chose_the_wrong_tier_is_counted(self):
        rule = self.check(self.task("t1", "opus", "settings", False, "claude-haiku-5-5", ["claude-haiku-5-5"]))
        self.assertEqual(rule["status"], "clean")
        self.assertEqual((rule["decided_on_guess"], rule["guess_wrong_tier"]), (1, 1))

    def test_an_observed_record_that_differs_from_the_answer_is_flagged(self):
        rule = self.check(self.task("t1", "claude-opus-5-5", "session", True, None, ["claude-haiku-5-5"]))
        self.assertEqual((rule["status"], rule["count"]), ("flagged", 1))

    def test_a_guess_never_corrected_that_differs_from_the_answer_is_flagged(self):
        rule = self.check(self.task("t1", "opus", "settings", False, None, ["claude-haiku-5-5"]))
        self.assertEqual((rule["status"], rule["count"]), ("flagged", 1))
        self.assertTrue(rule["found"][0]["guessed"])
