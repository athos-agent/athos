"""`athos save --from-audio`: a dictated way of working, transcribed and drafted by Meta's models. No network: the
Meta Model API is faked."""

import contextlib
import io
import json
import os
import urllib.error
import wave
from pathlib import Path
from unittest import mock

from athos import cli, store
from athos.adapters.meta import voice
from tests.helpers import TempHome

TRANSCRIPT = ("When I get a quote from a source, I check it in three steps. First I compare it word for word with my "
              "recording. Second I call the source back and read it aloud. Third, if it accuses someone, I ask them "
              "for a reply. Last year we ran a misquoted line and printed a correction.")

DRAFT = """```markdown
---
title: Check a quote before publishing
when: a story quotes a source and is about to be published
---
## #compare-with-recording
**When:** with the quote written in the draft.
**Do:** compare it word for word with the recording or the notes, never from memory.
**Because:** last year a misquoted line ran and needed a correction.
**Links:** [[#read-it-back]]

## #read-it-back
**When:** the quote matches the recording.
**Do:** call the source back and read the quote aloud.
**Because:** not said
**Links:** [[#right-of-reply]]

## #right-of-reply
**When:** the quote accuses someone.
**Do:** ask the person accused for a reply before publishing.
**Because:** not said
**Links:**
```"""


def write_wav(path: Path, rate: int = 16000, channels: int = 1) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * (channels * rate // 10))
    return path


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_meta(transcript=TRANSCRIPT, draft=DRAFT):
    """A fake Meta Model API: /asr/transcribe answers with the transcript, /chat/completions with the draft."""
    sent = []

    def urlopen(req, timeout=None):
        sent.append(req)
        if req.full_url.endswith("/asr/transcribe"):
            return Resp(json.dumps({"sessionId": "s1", "transcript": transcript, "audioDurationMs": 100,
                                    "turns": []}).encode())
        return Resp(json.dumps({"model": "muse-spark-1.3", "choices": [{"message": {"content": draft}}],
                                "usage": {}}).encode())
    return urlopen, sent


class VoiceTest(TempHome):
    def setUp(self):
        super().setUp()
        self._key = os.environ.get("MODEL_API_KEY")
        os.environ["MODEL_API_KEY"] = "k-test"
        self.wav = write_wav(Path(self.home) / "how-i-check.wav")

    def tearDown(self):
        if self._key is None:
            os.environ.pop("MODEL_API_KEY", None)
        else:
            os.environ["MODEL_API_KEY"] = self._key
        super().tearDown()

    def test_transcribe_sends_the_wav_as_multipart_with_the_model_and_language(self):
        urlopen, sent = fake_meta()
        self.assertEqual(voice.transcribe(self.wav, "es", urlopen=urlopen), TRANSCRIPT)
        req = sent[0]
        self.assertEqual(req.full_url, "https://api.meta.ai/v1/asr/transcribe")
        self.assertEqual(req.get_header("Authorization"), "Bearer k-test")
        self.assertIn("multipart/form-data; boundary=", req.get_header("Content-type"))
        self.assertIn(b'"model": "muse-voice-transcribe-1.0"', req.data)
        self.assertIn(b'"languageBias": ["Spanish"]', req.data)
        self.assertIn(b'name="audio"; filename="audio.wav"', req.data)
        self.assertIn(self.wav.read_bytes(), req.data)

    def test_transcript_from_turns_when_the_whole_text_is_missing(self):
        def urlopen(req, timeout=None):
            return Resp(json.dumps({"turns": [{"transcript": "one."}, {"transcript": "two."}]}).encode())
        self.assertEqual(voice.transcribe(self.wav, urlopen=urlopen), "one. two.")

    def test_an_empty_transcript_or_an_http_error_is_a_clear_message(self):
        with self.assertRaisesRegex(voice.VoiceError, "empty"):
            voice.transcribe(self.wav, urlopen=fake_meta(transcript="")[0])

        def refuse(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b"not a supported WAV file"))
        with self.assertRaisesRegex(voice.VoiceError, "HTTP 400.*not a supported WAV"):
            voice.transcribe(self.wav, urlopen=refuse)

    def test_no_key_says_where_to_put_it(self):
        os.environ.pop("MODEL_API_KEY")
        with mock.patch.object(voice.meta.Path, "home", return_value=Path(self.home) / "nobody"):
            with self.assertRaisesRegex(voice.VoiceError, "MODEL_API_KEY"):
                voice.transcribe(self.wav, urlopen=fake_meta()[0])

    def test_other_formats_are_converted_with_an_installed_converter_never_installed(self):
        m4a = Path(self.home) / "memo.m4a"
        m4a.write_bytes(b"not a wav")
        ran = []

        def run(cmd, **kw):
            ran.append(cmd)
            write_wav(Path(cmd[-1]))
            return mock.Mock(returncode=0, stderr="")
        with mock.patch.object(voice.shutil, "which", lambda name: "/usr/bin/afconvert" if name == "afconvert" else None):
            urlopen, sent = fake_meta()
            voice.transcribe(m4a, urlopen=urlopen, run=run)
        self.assertEqual(ran[0][:3], ["afconvert", "-f", "WAVE"])
        self.assertIn(str(m4a), ran[0])
        # A stereo 44.1 kHz WAV is converted too; a 16 kHz mono one goes as it is.
        self.assertFalse(voice._ready_wav(write_wav(Path(self.home) / "cd.wav", rate=44100, channels=2)))
        self.assertTrue(voice._ready_wav(self.wav))
        with mock.patch.object(voice.shutil, "which", return_value=None):
            with self.assertRaisesRegex(voice.VoiceError, "afconvert.*ffmpeg"):
                voice.transcribe(m4a, urlopen=urlopen)

    def test_draft_asks_muse_spark_with_the_format_and_cleans_the_answer(self):
        calls = []

        def chat(model, messages, tools=True):
            calls.append((model, messages, tools))
            return {"message": {"content": DRAFT}}
        piece = voice.draft(TRANSCRIPT, "en", chat=chat)
        model, messages, tools = calls[0]
        self.assertEqual((model, tools), ("muse-spark-1.3", False))
        self.assertIn("## #<statement_id>", messages[0]["content"])
        self.assertIn("Write it in English.", messages[0]["content"])
        self.assertEqual(messages[1]["content"], TRANSCRIPT)
        self.assertTrue(piece.startswith("---\nid: check-a-quote-before-publishing\ntitle: "))
        self.assertNotIn("```", piece)
        self.assertIn("**Links:** [[check-a-quote-before-publishing#read-it-back]]", piece)

    def test_a_dictated_piece_never_overwrites_an_existing_one(self):
        store.create("Check a quote before publishing", "older", "## #a\n**Do:** x\n")
        answer = DRAFT.replace("title:", "id: check-a-quote-before-publishing\nnote: hi\ntitle:")
        piece = voice.clean_draft(answer)
        self.assertIn("id: check-a-quote-before-publishing-2\n", piece)
        self.assertNotIn("note:", piece)

    def test_a_draft_without_title_or_steps_is_refused(self):
        with self.assertRaisesRegex(voice.VoiceError, "title"):
            voice.clean_draft("---\nwhen: x\n---\n## #a\n**Do:** y\n")
        with self.assertRaisesRegex(voice.VoiceError, "format"):
            voice.clean_draft("I could not understand the recording.")

    def run_cli(self, *argv, tty=False, answer="y"):
        out, err = io.StringIO(), io.StringIO()
        urlopen, _ = fake_meta()
        with mock.patch("urllib.request.urlopen", urlopen), \
             mock.patch.object(cli.sys.stdin, "isatty", return_value=tty), \
             mock.patch("builtins.input", return_value=answer), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["save", "--from-audio", str(self.wav), "--lang", "en", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_cli_without_a_terminal_prints_the_draft_and_the_command_and_saves_nothing(self):
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("Draft, not saved yet", out)
        self.assertIn("save <<'EOF'\n---\nid: check-a-quote-before-publishing", out)
        self.assertEqual(store.all_pieces(), [])

    def test_cli_asks_and_saves_on_yes_or_keeps_nothing_on_no(self):
        code, out, _ = self.run_cli(tty=True, answer="n")
        self.assertIn("not saved.", out)
        self.assertEqual(store.all_pieces(), [])
        code, out, _ = self.run_cli(tty=True, answer="y")
        self.assertEqual(code, 0)
        self.assertIn("saved check-a-quote-before-publishing", out)
        piece = store.get("check-a-quote-before-publishing")
        self.assertEqual(piece.title, "Check a quote before publishing")
        self.assertIn("## #right-of-reply", piece.body)

    def test_cli_yes_saves_without_asking(self):
        with mock.patch("builtins.input", side_effect=AssertionError("asked")):
            code, out, _ = self.run_cli("--yes")
        self.assertEqual(code, 0)
        self.assertIsNotNone(store.get("check-a-quote-before-publishing"))

    def test_cli_a_missing_file_fails_clearly(self):
        self.wav.unlink()
        code, _, err = self.run_cli("--yes")
        self.assertEqual(code, 1)
        self.assertIn("not saved: no audio file", err)
