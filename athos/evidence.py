"""Evidence for autonomous learning: what the hooks saw happen during a task, gathered without asking anyone.

Each task keeps a list of items in `<home>/evidence/<task_id>.jsonl` (one JSON object per line, append-only), and the
output of each verification command it ran in `<home>/evidence/<task_id>/out-<n>.txt` (the last OUTPUT_CAP
characters), for the independent verifier to read. Nothing leaves the machine.

Kinds of item:

    verify       a verification command ran (`label`: the runner, `kind`: test, build, lint, typecheck or check),
                 `ok` true or false, `check_of` the piece statement whose **Check:** it is, when it is one
    commit       `git commit` succeeded (`sha`, the short hash, when git could say)
    revert       a command that throws work away succeeded (`git revert`, `git reset --hard`, `git checkout -- …`,
                 `git restore`)
    person_edit  the edit detector gave a change to the person (athos/edits.py): a correction of what the agent wrote
    reaction     the person's next words judged the task (`eval.infer_mark`): ok or corrected
    model_claim  the model's own statement about its work (an `evidence:` line it wrote when saving)

Each item is **strong** (an exit status the hook observed, or an artifact: a commit, a file the person changed) or
**weak** (words: the model's claim, or a reaction read from the person's words by a heuristic), and `positive`,
`negative` or `neutral` for the work. A verification command counts as strong only when its own exit status is the
one the hook saw: alone, or in a chain joined by `&&` (and `;` before it), never piped (`pytest | tail` reports
`tail`'s status) nor followed by `||`. A failure counts as strong only when the command is the last of its chain and
only setup (`cd`, `export`, `source`) runs before it, so a failure of something else is not taken for it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from athos import paths, session

OUTPUT_CAP = 4000          # characters of a verification command's output kept for the verifier
ITEMS_CAP = 60             # items per task; later ones are dropped
OUTPUTS_CAP = 20           # output files per task
KEEP_TASKS = 300           # evidence of older tasks is removed

# Words that only prefix the real command.
_PREFIX = re.compile(r"^(?:(?:[A-Za-z_][A-Za-z0-9_]*=\S*|time|nice(?:\s+-n\s*-?\d+)?|timeout\s+\S+|env|command|"
                     r"npx|bunx|uv\s+run|poetry\s+run|pipenv\s+run|pdm\s+run|hatch\s+run|bundle\s+exec|"
                     r"xvfb-run)\s+)+")
_PY = r"python[0-9.]*\s+-m\s+"
_JS = r"(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?"
# (kind, label group or fixed label, pattern) — matched at the start of a segment, after the prefixes above.
VERIFY = [
    ("test", re.compile(rf"^(?:{_PY})?(pytest|py\.test|unittest|nose2?|tox|nox)\b")),
    ("test", re.compile(r"^(jest|vitest|mocha|ava|rspec|phpunit|ctest|trial|nosetests|playwright\s+test|cypress\s+run)\b")),
    ("test", re.compile(rf"^{_JS}(test(?::[\w:.-]+)?)\b")),
    ("test", re.compile(r"^(go|cargo|deno|swift|mix|dotnet|bazel|zig)\s+test\b")),
    ("test", re.compile(r"^(?:mvn|\./mvnw)\b.*\b(test|verify)\b")),
    ("test", re.compile(r"^(?:gradle|\./gradlew)\b.*\b(test|check)\b")),
    ("test", re.compile(r"^make\s+(test|tests|check)\b")),
    ("typecheck", re.compile(r"^(mypy|pyright|pyre)\b")),
    ("typecheck", re.compile(r"^(tsc)\b.*--noEmit\b")),
    ("typecheck", re.compile(rf"^{_JS}(typecheck|type-check|tsc|check-types)\b")),
    ("typecheck", re.compile(r"^(cargo\s+check|go\s+vet)\b")),
    ("lint", re.compile(r"^(flake8|pylint|eslint|stylelint|shellcheck|rubocop|golangci-lint|hadolint|markdownlint|"
                        r"biome\s+(?:check|lint)|ruff\s+check|ruff\s+format\s+.*--check|black\s+.*--check|"
                        r"isort\s+.*--check|prettier\s+.*--check|gofmt\s+-l)\b")),
    ("lint", re.compile(rf"^{_JS}(lint(?::[\w:.-]+)?)\b")),
    ("lint", re.compile(r"^(cargo\s+clippy)\b")),
    ("build", re.compile(rf"^{_JS}(build(?::[\w:.-]+)?)\b")),
    ("build", re.compile(r"^(cargo|go|swift|dotnet|zig)\s+build\b")),
    ("build", re.compile(r"^make\s+(build|all)\s*$")),
    ("build", re.compile(r"^(?:mvn|\./mvnw)\b.*\b(package|compile|install)\b")),
    ("build", re.compile(r"^(?:gradle|\./gradlew)\b.*\b(build|assemble)\b")),
    ("build", re.compile(r"^(tsc)\b(?!.*--noEmit)")),
]
_SETUP = re.compile(r"^(cd|pushd|popd|export|source|\.|set|unset|ulimit|true)\b")
_COMMIT = re.compile(r"^git\s+(?:-C\s+\S+\s+)?commit\b(?!.*--dry-run)")
_REVERT = re.compile(r"^git\s+(?:-C\s+\S+\s+)?(?:revert\b|reset\s+.*--hard\b|checkout\s+(?:\S+\s+)?--\s|checkout\s+\.\s*$|"
                     r"restore\b(?!.*--staged\s*$))")
_SECRET = re.compile(r"(?i)\b(?:[a-z0-9_]*(?:token|secret|password|passwd|api[_-]?key|auth)[a-z0-9_]*)=\S+"
                     r"|\b[A-Za-z0-9+/_-]{32,}\b")


# ------------------------------------------------------------------------------------------------ reading commands
def segments(cmd: str) -> list[tuple[str, str]]:
    """A shell command cut into its simple commands, each with the separator that follows it (`&&`, `||`, `|`, `;`,
    `&`, or "" for the last), quotes respected. Redirections such as `2>&1` stay inside their command."""
    out, buf, i, quote = [], [], 0, ""
    text = str(cmd or "")
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            elif ch == "\\" and quote == '"' and i + 1 < len(text):
                buf.append(text[i + 1])
                i += 1
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif text.startswith(("&&", "||"), i):
            out.append(("".join(buf).strip(), text[i:i + 2]))
            buf, i = [], i + 2
            continue
        elif ch in ";\n":
            out.append(("".join(buf).strip(), ";"))
            buf = []
        elif ch == "|":
            out.append(("".join(buf).strip(), "|"))
            buf = []
        elif ch == "&" and not (buf and buf[-1] in "<>") and not text.startswith("&>", i):
            out.append(("".join(buf).strip(), "&"))
            buf = []
        else:
            buf.append(ch)
        i += 1
    out.append(("".join(buf).strip(), ""))
    return [(seg, sep) for seg, sep in out if seg]


def _bare(segment: str) -> str:
    """A simple command without its env assignments, wrappers and redirections, whitespace folded."""
    text = re.sub(r"\s+\d*[<>]+&?\s*\S+", " ", " " + segment).strip()
    text = " ".join(text.split())
    return _PREFIX.sub("", text)


def kind_of(segment: str) -> tuple[str, str] | None:
    """(kind, label) when a simple command is a verification command (a test runner, a build, a linter, a type
    checker), else None. Subshells and `sh -c` strings are not read."""
    bare = _bare(segment)
    if not bare or bare.startswith(("(", "{", "$(")) or re.match(r"^(?:ba|z)?sh\s+-c\b", bare):
        return None
    for kind, rx in VERIFY:
        found = rx.match(bare)
        if found:
            label = (found.group(1) if found.groups() and found.group(1) else bare.split()[0])
            return kind, " ".join(label.split())[:40]
    return None


def _norm(cmd: str) -> str:
    return " ".join(_bare(cmd).split())


def checks_of(piece) -> list[tuple[str, str]]:
    """(statement id, command) for each **Check:** of a piece that names a command in backticks."""
    from athos import wiki
    out = []
    for st in wiki.statements(piece):
        for found in re.findall(r"`([^`\n]+)`", st.check or ""):
            if found.strip():
                out.append((st.id, found.strip()))
    return out


def _check_match(segment: str, checks: list[tuple[str, str, str]]) -> str | None:
    """The `piece#statement` whose Check this simple command runs: the same command, or one that begins with it."""
    mine = _norm(segment)
    for pid, sid, cmd in checks:
        theirs = _norm(cmd)
        if theirs and (mine == theirs or mine.startswith(theirs + " ")):
            return f"{pid}#{sid}"
    return None


def classify(cmd: str, checks: list[tuple[str, str, str]] | None = None) -> list[dict]:
    """Every verification step of a shell command: each with its kind, label, the Check it runs (if any), and whether
    the command's exit status belongs to it on success (`owns_success`) and on failure (`owns_failure`)."""
    parts = segments(cmd)
    out = []
    for i, (seg, sep) in enumerate(parts):
        check = _check_match(seg, checks or [])
        found = kind_of(seg) or (("check", _bare(seg).split()[0][:40]) if check else None)
        if not found:
            continue
        before = [s for _, s in parts[:i]]
        after = [s for _, s in parts[i:-1]]           # this segment's own separator and the ones after it
        piped = sep == "|" or (i and parts[i - 1][1] == "|") or sep == "&"
        runs_surely = all(s in ("&&", ";") for s in before)
        owns_success = not piped and runs_surely and all(s == "&&" for s in after)
        last = i == len(parts) - 1
        setup_only = all(_SETUP.match(_bare(p)) for p, _ in parts[:i])
        owns_failure = not piped and last and runs_surely and (setup_only or (before and before[-1] == ";"))
        out.append({"kind": found[0], "label": found[1], "check_of": check, "owns_success": owns_success,
                    "owns_failure": bool(owns_failure)})
    return out


def redact(cmd: str) -> str:
    """A command as the evidence keeps it: secrets and long tokens blanked, at most 200 characters."""
    text = _SECRET.sub("<redacted>", " ".join(str(cmd or "").split()))
    return text[:200]


# ------------------------------------------------------------------------------------------------ the store
def root() -> Path:
    return paths.home() / "evidence"


def _safe(task_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", task_id or "_")


def file_of(task_id: str) -> Path:
    return root() / f"{_safe(task_id)}.jsonl"


def add(task_id: str | None, item: dict) -> dict | None:
    """Append one item to a task's evidence. None (nothing written) without a task or past ITEMS_CAP."""
    if not task_id:
        return None
    from athos import eval as ev
    target = file_of(task_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        count = len(target.read_text().splitlines()) if target.exists() else 0
    except OSError:
        count = 0
    if count >= ITEMS_CAP:
        return None
    item = {"at": ev._iso(ev.now()), **item}
    with target.open("a") as out:
        out.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def of_task(task_id: str | None) -> list[dict]:
    """A task's evidence, oldest first."""
    if not task_id:
        return []
    try:
        lines = file_of(task_id).read_text().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def _keep_output(task_id: str, text: str, header: str) -> str | None:
    folder = root() / _safe(task_id)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        n = len(list(folder.glob("out-*.txt")))
        if n >= OUTPUTS_CAP:
            return None
        target = folder / f"out-{n + 1}.txt"
        target.write_text(header + "\n" + (text or "")[-OUTPUT_CAP:] + "\n")
    except OSError:
        return None
    return str(target)


def prune(keep: int = KEEP_TASKS) -> None:
    """Only the newest `keep` tasks' evidence stays."""
    import shutil
    try:
        files = sorted(root().glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
    except OSError:
        return
    for f in files[:-keep] if len(files) > keep else []:
        f.unlink(missing_ok=True)
        shutil.rmtree(f.with_suffix(""), ignore_errors=True)


# ------------------------------------------------------------------------------------------------ the hooks
def _output_of(event: dict) -> str:
    r = event.get("tool_response")
    if isinstance(r, dict):
        parts = [str(r.get(k) or "") for k in ("stdout", "stderr", "output", "error")]
        text = "\n".join(p for p in parts if p)
    else:
        text = str(r or "")
    return text or str(event.get("error") or "")


def _exit_status(event: dict, failed: bool, platform: str) -> bool | None:
    """True for a command the hook saw succeed, False for one it saw fail, None when it cannot tell. Claude Code
    calls PostToolUse after a shell command that exited 0 and PostToolUseFailure after one that did not; an
    explicit exit code in the response wins; an interrupted command tells nothing."""
    r = event.get("tool_response") if isinstance(event.get("tool_response"), dict) else {}
    for key in ("exit_code", "exitCode", "returncode", "return_code", "code"):
        if isinstance(r.get(key), int) and not isinstance(r.get(key), bool):
            return r[key] == 0
    if r.get("interrupted"):
        return None
    if failed:
        return False
    return True if platform in ("claude-code", "muse-code") else None


def _head_sha(cwd: str | None) -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd or None, capture_output=True, text=True,
                           timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def _task_checks(state: dict) -> list[tuple[str, str, str]]:
    """(piece, statement, command) of every runnable Check of the pieces this task uses."""
    from athos import store
    ids = list(dict.fromkeys([*(state.get("task_route") or []), *(state.get("task_loaded") or []),
                              *(state.get("task_opened") or [])]))
    out = []
    for pid in ids:
        p = store.get(pid)
        if p is not None:
            out += [(pid, sid, cmd) for sid, cmd in checks_of(p)]
    return out


def on_tool(event: dict, sid: str, failed: bool = False, platform: str = "claude-code") -> list[dict]:
    """A tool call ended (PostToolUse, or PostToolUseFailure with `failed`): a shell command that verified, committed
    or threw work away becomes an item of the open task. Subagents' calls and Athos's own commands are left out."""
    from athos import capture, edits
    if event.get("agent_id") or not edits.is_shell(event):
        return []
    cmd = (event.get("tool_input") or {}).get("command")
    cmd = " ".join(map(str, cmd)) if isinstance(cmd, list) else str(cmd or "")
    if not cmd.strip() or capture._ATHOS_COMMAND.search(cmd):
        return []
    state = session.load(sid)
    task_id = state.get("task_id")
    if not task_id:
        return []
    ok = _exit_status(event, failed, platform)
    public = bool(state.get("public"))
    shown = {} if public else {"cmd": redact(cmd)}
    added = []
    steps = classify(cmd, _task_checks(state))
    for step in steps:
        owned = step["owns_success"] if ok else step["owns_failure"] if ok is False else False
        strong = ok is not None and owned
        header = f"$ {'(command not kept: public repository)' if public else redact(cmd)}\n# exit: " + \
                 {True: "0 (succeeded)", False: "non-zero (failed)", None: "unknown"}[ok]
        output = _keep_output(task_id, _output_of(event), header) if strong else None
        item = {"type": "verify", "kind": step["kind"], "label": step["label"], "ok": ok,
                "strength": "strong" if strong else "weak",
                "polarity": "positive" if ok and strong else "negative" if ok is False and strong else "neutral",
                **({"check_of": step["check_of"]} if step["check_of"] else {}), **shown,
                **({"output": output} if output else {}),
                **({} if strong else {"why_weak": "exit status unknown" if ok is None else
                    "exit status not this command's (piped, or not last in its chain)"})}
        if add(task_id, item):
            added.append(item)
    if ok:
        for seg, _sep in segments(cmd):
            bare = _bare(seg)
            if _COMMIT.match(bare):
                item = {"type": "commit", "strength": "strong", "polarity": "positive",
                        **({"sha": sha} if (sha := _head_sha(event.get("cwd"))) else {})}
            elif _REVERT.match(bare):
                item = {"type": "revert", "strength": "strong", "polarity": "negative", **shown}
            else:
                continue
            if add(task_id, item):
                added.append(item)
    return added


def note_person_edits(found: list[dict], fallback_task: str | None = None) -> None:
    """The edit detector's changes given to the person (edits.record): each one a strong correction of the task that
    wrote the file."""
    for f in found or []:
        add(f.get("task_id") or fallback_task, {"type": "person_edit", "strength": "strong", "polarity": "negative",
                                                "file_sha": f.get("file_sha"), "piece": f.get("piece"),
                                                "statement": f.get("statement"), "basis": f.get("basis")})


def note_reaction(task_id: str | None, result: str | None) -> None:
    """The person's next words judged the task (eval.infer_mark): a weak item, read from words by a heuristic."""
    if task_id and result:
        add(task_id, {"type": "reaction", "result": result, "strength": "weak",
                      "polarity": "positive" if result == "ok" else "negative"})


# ------------------------------------------------------------------------------------------------ judging it
def strong(items: list[dict]) -> list[dict]:
    return [i for i in items if i.get("strength") == "strong"]


def qualifies(items: list[dict]) -> tuple[bool, str]:
    """Whether a task's evidence is enough to learn from: at least one strong positive item (a verification that
    passed, a commit), no strong negative item after the last strong positive one (a failed verification, a revert,
    a change the person made), and the last verification that ran not a failure. Returns (ok, reason)."""
    hard = strong(items)
    positives = [n for n, i in enumerate(hard) if i.get("polarity") == "positive"]
    if not positives:
        return False, "no_strong_evidence"
    verifies = [i for i in hard if i.get("type") == "verify"]
    if verifies and verifies[-1].get("ok") is False:
        return False, "last_verification_failed"
    if any(i.get("polarity") == "negative" for i in hard[positives[-1] + 1:]):
        return False, "correction_after_success"
    return True, "strong_evidence"


def summary(items: list[dict], task_id: str | None = None, limit: int = 8) -> list[str]:
    """The short `kind:detail` list a piece's frontmatter keeps: each strong item once, then the task it came from."""
    out: list[str] = []
    for i in strong(items):
        if i.get("type") == "verify":
            token = f"verify:{i.get('label')}:{'ok' if i.get('ok') else 'failed'}"
        elif i.get("type") == "commit":
            token = "commit" + (f":{i['sha']}" if i.get("sha") else "")
        else:
            token = str(i.get("type"))
        token = re.sub(r"[\s,\[\]]+", "-", token)
        if token not in out:
            out.append(token)
    out = out[:limit - 1]
    if task_id:
        out.append(f"task:{task_id}")
    return out


def counts(items: list[dict]) -> dict:
    """How many items of each strength and polarity: what the `learn` event keeps."""
    out = {"strong": 0, "weak": 0, "positive": 0, "negative": 0}
    for i in items:
        out[i.get("strength", "weak")] = out.get(i.get("strength", "weak"), 0) + 1
        if i.get("polarity") in ("positive", "negative"):
            out[i["polarity"]] += 1
    return out


def outputs(items: list[dict]) -> list[str]:
    """The output files the task's strong verification items kept, oldest first, that still exist."""
    return [i["output"] for i in items if i.get("output") and os.path.isfile(i["output"])]
