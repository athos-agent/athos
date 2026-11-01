"""A way of working dictated aloud: `athos save --from-audio FILE [--lang es|en] [--yes]`.

The person records how they do a task, in their own words. Meta's Muse Voice Transcribe (`muse-voice-transcribe-1.0`,
Meta Model API's file endpoint `POST /v1/asr/transcribe`) turns the recording into text, and Muse Spark
(`muse-spark-1.3`) writes that text as a draft piece in Athos's format: a title, a `when`, and one `## #statement` per
step with When/Do/Because/Links. The draft is shown first; it is stored with the normal save path only after the
person says yes (or with `--yes`).

The endpoint takes WAV, mono, 16-bit PCM at 16 or 24 kHz (up to 10 minutes, 32 MB). Any other recording (m4a, mp3,
aiff, a stereo or 44.1 kHz WAV) is converted first with a converter already on the machine: macOS's `afconvert`, or
`ffmpeg`. Nothing is installed. The recording and its transcript go to Meta only because the person asked for it by
running the command; the key is `MODEL_API_KEY`, read as the rest of the Meta adapter reads it, and never printed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

from athos import capture, paths, store
from athos.adapters import meta

TRANSCRIBE_MODEL = "muse-voice-transcribe-1.0"
DRAFT_MODEL = meta.DEFAULT_MODEL
RATES = (16000, 24000)
MAX_BYTES = 32 * 1024 * 1024
LANGUAGE = {"es": "Spanish", "en": "English"}


class VoiceError(Exception):
    """Something the person can fix: no key, an unreadable recording, no converter, an empty transcript."""


def _ready_wav(path: Path) -> bool:
    """True when the file is already what the endpoint takes: WAV, mono, 16-bit, 16 or 24 kHz."""
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() in RATES
    except (wave.Error, EOFError, OSError):
        return False


def converter() -> list[str] | None:
    """The command that writes a 16 kHz mono 16-bit WAV with a converter already installed, `{src}`/`{dst}` to fill."""
    if shutil.which("afconvert"):
        return ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", "{src}", "{dst}"]
    if shutil.which("ffmpeg"):
        return ["ffmpeg", "-loglevel", "error", "-y", "-i", "{src}", "-ac", "1", "-ar", "16000",
                "-sample_fmt", "s16", "{dst}"]
    return None


def as_wav(path: Path, workdir: Path, run=subprocess.run) -> Path:
    """The recording as the endpoint takes it: the file itself when it already fits, else a converted copy."""
    if not path.is_file():
        raise VoiceError(f"no audio file at {path}")
    if _ready_wav(path):
        return path
    cmd = converter()
    if cmd is None:
        raise VoiceError("this recording has to become a 16 kHz mono WAV first, and neither afconvert (macOS) nor "
                         "ffmpeg is installed. Convert it with any audio tool and run the command again on the .wav.")
    dst = workdir / "audio.wav"
    done = run([str(path) if a == "{src}" else str(dst) if a == "{dst}" else a for a in cmd],
               capture_output=True, text=True)
    if done.returncode != 0 or not _ready_wav(dst):
        raise VoiceError(f"could not convert {path.name} to WAV with {cmd[0]}: "
                         f"{(done.stderr or '').strip()[:300] or 'unknown error'}")
    return dst


def _multipart(fields: list[tuple[str, str, str | None, bytes]]) -> tuple[bytes, str]:
    """A multipart/form-data body: (name, content type, file name or None, bytes) for each part."""
    boundary = uuid.uuid4().hex
    out = b""
    for name, ctype, filename, data in fields:
        disp = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        out += f"--{boundary}\r\nContent-Disposition: {disp}\r\nContent-Type: {ctype}\r\n\r\n".encode() + data + b"\r\n"
    return out + f"--{boundary}--\r\n".encode(), boundary


def _key() -> str:
    key = meta.api_key()
    if not key:
        raise VoiceError(f"no Meta Model API key: set MODEL_API_KEY, or put a MODEL_API_KEY=... line in "
                         f"{paths.home() / '.env'}")
    return key


def transcribe(audio: Path, lang: str | None = None, urlopen=None, timeout: float = 300,
               run=subprocess.run) -> str:
    """The recording's text, from Muse Voice Transcribe. `lang` (es/en) is a hint; without it the model detects it."""
    key = _key()
    with tempfile.TemporaryDirectory(prefix="athos-voice-") as tmp:
        wav = as_wav(Path(audio).expanduser(), Path(tmp), run=run)
        data = wav.read_bytes()
    if len(data) > MAX_BYTES:
        raise VoiceError("the recording is too long for one request (32 MB, about 10 minutes): split it or "
                         "dictate a shorter version.")
    settings = {"model": TRANSCRIBE_MODEL, "audioEncoding": "WAV", "mode": "ENDPOINTING"}
    if lang in LANGUAGE:
        settings["languageBias"] = [LANGUAGE[lang]]
    body, boundary = _multipart([("request", "application/json", None, json.dumps(settings).encode()),
                                 ("audio", "audio/wav", "audio.wav", data)])
    req = urllib.request.Request(meta.BASE + "/asr/transcribe", data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json"})
    try:
        with (urlopen or urllib.request.urlopen)(req, timeout=timeout) as resp:
            reply = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise VoiceError(f"Meta's transcription refused the recording (HTTP {e.code}): "
                         f"{e.read()[:300].decode(errors='replace')}") from None
    except urllib.error.URLError as e:
        raise VoiceError(f"could not reach Meta Model API: {e.reason}") from None
    text = (reply.get("transcript") or " ".join(t.get("transcript", "") for t in reply.get("turns") or [])).strip()
    if not text:
        raise VoiceError("the transcript came back empty: is there speech in the recording?")
    return text


DRAFT_PROMPT = """The person dictated, aloud, how they do a task. Their words, transcribed, are below. Write them as one
way of working in Athos's format, ready to store. Answer with the piece only, starting with the line `---`: no
heredoc, no `athos save` line, no code fences, no comments before or after it.

The format (leave out `id:` and `note:`: this is a new piece):

{format}

Rules: keep to what the person said; do not add steps, reasons or tools they did not mention, and leave **Because:**
as the reason they gave (or "not said" when they gave none). Keep their exact names, numbers and phrases. Fix the
transcription's slips (a repeated word, a filler) without changing the meaning. Statement ids are short kebab-case
words (`## #compare-with-recording`). Links go to the statement that comes next in this piece (`[[#next-id]]`); the
last one has none. {language}"""


def draft_messages(transcript: str, lang: str | None = None) -> list[dict]:
    fmt = capture.FORMAT.format(cmd="athos").split("\n", 1)[1].rsplit("\nEOF", 1)
    language = (f"Write it in {LANGUAGE[lang]}." if lang in LANGUAGE
                else "Write it in the language the person spoke.")
    return [{"role": "system", "content": DRAFT_PROMPT.format(format=fmt[0] + fmt[1], language=language)},
            {"role": "user", "content": transcript}]


def clean_draft(text: str) -> str:
    """The piece out of the model's answer: from its first `---` on, without code fences or a stray heredoc."""
    text = re.sub(r"^```[a-z]*\s*$", "", text.strip(), flags=re.MULTILINE).strip()
    start = text.find("---")
    if start < 0:
        raise VoiceError("Muse Spark did not answer with a piece in Athos's format; run the command again.")
    text = re.sub(r"\n?EOF\s*$", "", text[start:]).strip()
    meta_fields, body = store.parse_frontmatter(text)
    absent = [k for k in ("title", "when") if not meta_fields.get(k, "").strip()] + ([] if body.strip() else ["body"])
    if absent:
        raise VoiceError(f"the draft lacks {', '.join(absent)}; run the command again.")
    # A dictated piece is always new: its id is a free one from its title (an `id:` from the model could name and
    # overwrite another piece), and the links within it (`[[#step]]`) name that page.
    pid = store._free_id(store.slugify(meta_fields["title"]))
    head, sep, rest = text[3:].partition("\n---")
    head = "\n".join(line for line in head.split("\n") if line.strip() and not line.startswith(("id:", "note:")))
    rest = re.sub(r"\[\[#([a-z0-9][a-z0-9_-]*)\]\]", rf"[[{pid}#\1]]", rest)
    return f"---\nid: {pid}\n{head.strip()}{sep}{rest}\n"


def draft(transcript: str, lang: str | None = None, chat=None) -> str:
    """The transcript written as a draft piece by Muse Spark, through the adapter's chat call with no tools."""
    _key()
    if chat is None:
        reply = meta.chat(DRAFT_MODEL, draft_messages(transcript, lang), tools=False, urlopen=urllib.request.urlopen)
    else:
        reply = chat(DRAFT_MODEL, draft_messages(transcript, lang), tools=False)
    return clean_draft(reply["message"]["content"])
