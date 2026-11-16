"""Evidence for autonomous learning: what the hooks saw happen during a task, gathered without asking anyone.

Each task keeps a list of items in `<home>/evidence/<task_id>.jsonl` (one JSON object per line, append-only), and the
output of each verification command it ran in `<home>/evidence/<task_id>/out-<n>.txt` (the last OUTPUT_CAP
characters), for the independent verifier to read. Nothing leaves the machine.

Kinds of item:

    verify       a verification command ran (`label`: the runner, `kind`: test, build, lint, typecheck or check),
                 `ok` true or false, `check_of` the piece statement whose **Check:** it is, when it is one, and `rule`,
                 when strong, the rule that made it so
    commit       HEAD moved during a shell command to a commit made during it (`sha`): seen by watching HEAD
                 (`observe_head`), never by reading the command
    revert       HEAD moved back on the same branch, or a command that throws work away succeeded (`git revert`,
                 `git reset --hard`, `git checkout -- …`, `git restore`)
    rewrite      HEAD moved sideways on the same branch (a rebase, a reset onto another commit): not a commit
    person_edit  the edit detector gave a change to the person (athos/edits.py): a correction of what the agent wrote
    reaction     the person's next words judged the task (`eval.infer_mark`): ok or corrected
    model_claim  the model's own statement about its work (an `evidence:` line it wrote when saving)

Each item is **strong** (an exit status the hook observed, a runner's own summary Athos reads exactly, or an
artifact: a commit, a file the person changed) or **weak** (words: the model's claim, or a reaction read from the
person's words by a heuristic), and `positive`, `negative` or `neutral` for the work. Commands are read as the shell
decides what runs (`_Parser`: heredocs, continuations, comments, sequences, groups); which verification owns the
command's exit status is decided by `_walk`, and a failure is never taken for a success.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from athos import paths, session

OUTPUT_CAP = 4000          # characters of a verification command's output kept for the verifier
ITEMS_CAP = 60             # weak items per task; later weak ones are dropped, strong ones never are
STRONG_CAP = 2000          # a bound on one task's file only: far more strong items than any task produces
OUTPUTS_CAP = 20           # output files per task
KEEP_TASKS = 300           # evidence of older tasks is removed

# Words that only prefix the real command.
_PREFIX = re.compile(r"^(?:(?:[A-Za-z_][A-Za-z0-9_]*=\S*|time|nice(?:\s+-n\s*-?\d+)?|timeout\s+\S+|env|command|"
                     r"npx|bunx|uv\s+run|poetry\s+run|pipenv\s+run|pdm\s+run|hatch\s+run|bundle\s+exec|"
                     r"xvfb-run)\s+)+")
_PY = r"python[0-9.]*\s+-m\s+"
_JS = r"(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?"
# (kind, label group or fixed label, pattern) — matched at the start of a segment, after the prefixes above.
_END = r"(?![\w-])"         # the runner's own word ends here: `pytest-watch` and `make test-clean` are other words
VERIFY = [
    ("test", re.compile(rf"^(?:{_PY})?(pytest|py\.test|unittest|nose2?|tox|nox){_END}")),
    ("test", re.compile(rf"^(jest|vitest|mocha|ava|rspec|phpunit|ctest|trial|nosetests|playwright\s+test|cypress\s+run)"
                        rf"{_END}")),
    ("test", re.compile(rf"^{_JS}(test(?::[\w:.-]+)?){_END}")),
    ("test", re.compile(rf"^(go|cargo|deno|swift|mix|dotnet|bazel|zig)\s+test{_END}")),
    ("test", re.compile(rf"^(?:mvn|\./mvnw)\b.*(?<![\w-])(test|verify){_END}")),
    ("test", re.compile(rf"^(?:gradle|\./gradlew)\b.*(?<![\w-])(test|check){_END}")),
    ("test", re.compile(rf"^make\s+(test|tests|check){_END}")),
    ("typecheck", re.compile(rf"^(mypy|pyright|pyre){_END}")),
    ("typecheck", re.compile(r"^(tsc)\b.*--noEmit\b")),
    ("typecheck", re.compile(rf"^{_JS}(typecheck|type-check|tsc|check-types){_END}")),
    ("typecheck", re.compile(rf"^(cargo\s+check|go\s+vet){_END}")),
    ("lint", re.compile(r"^(flake8|pylint|eslint|stylelint|shellcheck|rubocop|golangci-lint|hadolint|markdownlint|"
                        r"biome\s+(?:check|lint)|ruff\s+check|ruff\s+format\s+.*--check|black\s+.*--check|"
                        rf"isort\s+.*--check|prettier\s+.*--check|gofmt\s+-l){_END}")),
    ("lint", re.compile(rf"^{_JS}(lint(?::[\w:.-]+)?){_END}")),
    ("lint", re.compile(rf"^(cargo\s+clippy){_END}")),
    ("check", re.compile(rf"^{_JS}(validate|verify|check)(?::[\w:.-]+)?{_END}")),
    ("build", re.compile(rf"^{_JS}(build(?::[\w:.-]+)?){_END}")),
    ("build", re.compile(rf"^(cargo|go|swift|dotnet|zig)\s+build{_END}")),
    ("build", re.compile(r"^make\s+(build|all)\s*$")),
    ("build", re.compile(rf"^(?:mvn|\./mvnw)\b.*(?<![\w-])(package|compile|install){_END}")),
    ("build", re.compile(rf"^(?:gradle|\./gradlew)\b.*(?<![\w-])(build|assemble){_END}")),
    ("build", re.compile(r"^(tsc)\b(?!.*--noEmit)")),
]
# Words that make a runner report on itself, list what it would run, or pretend: it then verifies nothing.
_INFO_FLAGS = {"--version", "-V", "--help", "-h", "--collect-only", "--co", "--no-run", "--listTests", "--list-tests",
               "--list", "--dry-run", "--just-print", "--recon", "--setup-plan", "--fixtures", "--showconfig"}
_MAKE_DRY = {"-n", "--dry-run", "--just-print", "--recon", "-q", "--question"}
_FIXING = {"--fix", "--fix-only", "--write", "--unsafe-fixes"}
# Tasks a gradle or maven run was told to leave out (`-x test`): they did not run.
_EXCLUDED = re.compile(r"\s(?:-x|--exclude-task)\s+\S+")
# What a test runner prints when it ran no test at all, and what it prints when it ran some.
_NO_TESTS = [re.compile(p, re.I | re.M) for p in (
    r"^Ran 0 tests\b", r"\bcollected 0 items\b", r"\bno tests ran\b", r"\[no test files\]", r"\bno tests to run\b",
    r"^running 0 tests\s*$", r"\bNo tests found\b", r"^\s*0 passing\b", r"\bNo test files found\b",
    r"\bTests:\s+0 total\b")]
_SOME_TESTS = [re.compile(p, re.I | re.M) for p in (
    r"^Ran [1-9]\d* tests?\b", r"\bcollected [1-9]\d* items?\b", r"\b[1-9]\d* (?:passed|failed)\b",
    r"^ok\s+\S+\s+[\d.]+s\b", r"^running [1-9]\d* tests?\s*$", r"^\s*[1-9]\d* passing\b",
    r"\bTests:\s+.*\b[1-9]\d* (?:passed|total)\b", r"^(?:PASS|FAIL)\s+\S+", r"\b[1-9]\d* examples?, \d+ failures?\b",
    r"\bTests run: [1-9]\d*")]
_SETUP = re.compile(r"^(cd|pushd|popd|export|source|\.|set|unset|ulimit|true)\b")


class _Reverts:
    """Whether a simple command throws work away: `git revert` (not `--abort` or `--quit`, which undo nothing), `git
    reset --hard` (not onto the remote's branch, which only catches up with it), `git checkout -- <files>` or `git
    checkout .`, and `git restore` of the working tree (not `--staged` alone, which only unstages)."""

    _GIT = re.compile(r"^git\s+(?:-C\s+\S+\s+)?(\S+)(.*)$")
    _REMOTE = re.compile(r"(?:^|\s)(?:(?:origin|upstream)/\S+|\S*@\{u(?:pstream)?\}|FETCH_HEAD)(?:\s|$)")

    def match(self, bare: str) -> bool | None:
        found = self._GIT.match(bare or "")
        if not found:
            return None
        verb, rest = found.group(1), " " + found.group(2).strip() + " "
        words = rest.split()
        if verb == "revert":
            return None if {"--abort", "--quit"} & set(words) else True
        if verb == "reset":
            return True if "--hard" in words and not self._REMOTE.search(rest) else None
        if verb == "checkout":
            return True if ("--" in words or words == ["."]) else None
        if verb == "restore":
            staged = {"--staged", "-S"} & set(words)
            tree = {"--worktree", "-W"} & set(words)
            return True if (tree or not staged) else None
        return None


_REVERT = _Reverts()
_SECRET = re.compile(r"(?i)\b(?:[a-z0-9_]*(?:token|secret|password|passwd|api[_-]?key|auth)[a-z0-9_]*)=\S+"
                     r"|\b[A-Za-z0-9+/_-]{32,}\b")


# ------------------------------------------------------------------------------------------------ reading commands
class Group:
    """A subshell `( … )` or a brace group `{ …; }`: one command to the list around it, whose exit status is the one
    of the last command inside it. `parts` are its own (node, separator) pairs."""

    def __init__(self, parts: list):
        self.parts = parts

    def __repr__(self) -> str:                    # for test failures
        return f"Group({self.parts!r})"


_HEREDOC = re.compile(r"<<(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([A-Za-z0-9_.@%+-]+))")


class _Parser:
    """A shell command read into lists of (node, separator): a node is a simple command (its text) or a Group. It
    reads what decides which commands run and in what order, and nothing more: quotes, backslash escapes, line
    continuations, comments, `$( … )` and backquotes (kept inside their word), heredocs (the body is data, and the
    command goes on after the terminator line), `&&`, `||`, `|`, `;`, `&`, newlines, and grouping. Anything it does
    not know stays inside a simple command, which then simply matches no verification."""

    def __init__(self, text: str):
        self.t = text
        self.i = 0
        self.pending: list[tuple[str, bool]] = []      # heredocs opened on this line: (terminator, strip tabs)

    def parse(self, closer: str = "") -> list:
        out: list = []
        buf: list[str] = []
        node = None                                       # a Group just closed, waiting for its separator
        t = self.t

        def flush(sep: str) -> None:
            nonlocal buf, node
            text = "".join(buf).strip()
            if node is not None:
                out.append([node, sep])
            elif text:
                out.append([text, sep])
            elif sep in ("&&", "||", "|") and out:
                out[-1][1] = sep                          # `a\n&& b` is not shell, but never lose the operator
            buf, node = [], None

        while self.i < len(t):
            ch = t[self.i]
            at_start = node is None and not "".join(buf).strip()
            if ch in "'\"":
                end = self._quoted(self.i)
                buf.append(t[self.i:end])
                self.i = end
                continue
            if ch == "\\":
                if t.startswith("\\\n", self.i):          # a line continuation: one line
                    buf.append(" ")
                else:
                    buf.append(t[self.i:self.i + 2])
                self.i += 2
                continue
            if t.startswith("$(", self.i) or ch == "`":
                end = self._substitution(self.i)
                buf.append(t[self.i:end])
                self.i = end
                continue
            if ch == "#" and (self.i == 0 or t[self.i - 1] in " \t\n;&|()"):
                end = t.find("\n", self.i)                # a comment runs nothing
                self.i = len(t) if end == -1 else end
                continue
            if t.startswith("<<", self.i) and not t.startswith("<<<", self.i):
                found = _HEREDOC.match(t, self.i)
                if found:
                    word = next(g for g in found.groups()[1:] if g is not None)
                    self.pending.append((word, found.group(1) == "-"))
                    buf.append(" " + found.group(0) + " ")
                    self.i = found.end()
                    continue
            if t.startswith("<<<", self.i):
                buf.append("<<<")
                self.i += 3
                continue
            if closer and ch == closer and (closer == ")" or at_start):
                flush("")
                self.i += 1
                return self._ended(out)
            if ch == "(" and at_start:
                self.i += 1
                node = Group(self.parse(")"))
                continue
            if ch == "{" and at_start and t[self.i + 1:self.i + 2] in (" ", "\t", "\n"):
                self.i += 1
                node = Group(self.parse("}"))
                continue
            if ch == "\n":
                flush(";")
                self.i += 1
                self._skip_heredoc_bodies()
                continue
            if t.startswith(("&&", "||"), self.i):
                flush(t[self.i:self.i + 2])
                self.i += 2
                continue
            if t.startswith("|&", self.i):
                flush("|")
                self.i += 2
                continue
            if ch in ";|":
                flush(ch)
                self.i += 1
                while t.startswith(";", self.i):          # `;;` of a case: nothing more to read
                    self.i += 1
                continue
            if ch == "&" and not (buf and buf[-1] in "<>") and not t.startswith("&>", self.i):
                flush("&")
                self.i += 1
                continue
            buf.append(ch)
            self.i += 1
        flush("")
        return self._ended(out)

    @staticmethod
    def _ended(out: list) -> list:
        """A list's last command is followed by nothing: a trailing `;` or newline separates it from nothing."""
        if out and out[-1][1] == ";":
            out[-1][1] = ""
        return out

    def _quoted(self, start: int) -> int:
        t, q, i = self.t, self.t[start], start + 1
        while i < len(t):
            if t[i] == "\\" and q == '"':
                i += 2
                continue
            if t[i] == q:
                return i + 1
            i += 1
        return len(t)

    def _substitution(self, start: int) -> int:
        t = self.t
        if t[start] == "`":
            i = start + 1
            while i < len(t) and t[i] != "`":
                i += 2 if t[i] == "\\" else 1
            return min(i + 1, len(t))
        depth, i = 0, start + 1
        while i < len(t):
            if t[i] in "'\"":
                i = self._quoted(i)
                continue
            if t[i] == "(":
                depth += 1
            elif t[i] == ")":
                depth -= 1
                if depth == 0:
                    return i + 1
            i += 1
        return len(t)

    def _skip_heredoc_bodies(self) -> None:
        """After the newline that ends a line which opened heredocs: their bodies, up to each terminator line, are
        data. A body with no terminator takes the rest of the command."""
        t = self.t
        while self.pending:
            word, tabs = self.pending.pop(0)
            while self.i < len(t):
                end = t.find("\n", self.i)
                line = t[self.i:] if end == -1 else t[self.i:end]
                self.i = len(t) if end == -1 else end + 1
                if (line.lstrip("\t") if tabs else line) == word:
                    break
            else:
                self.pending.clear()


def parse(cmd: str) -> list:
    """A shell command as lists of (node, separator) pairs (`_Parser`): each node a simple command or a Group."""
    return [tuple(p) for p in _Parser(str(cmd or "")).parse()]


def _flat(parts: list, sep_after: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for n, (node, sep) in enumerate(parts):
        last_sep = sep_after if n == len(parts) - 1 and sep == "" else sep
        if isinstance(node, Group):
            inner = _flat([tuple(p) for p in node.parts], last_sep)
            out += inner
        else:
            out.append((node, last_sep))
    return out


def segments(cmd: str) -> list[tuple[str, str]]:
    """A shell command cut into its simple commands, each with the separator that follows it (`&&`, `||`, `|`, `;`,
    `&`, or "" for the last), quotes, heredocs and groups read as `_Parser` reads them (a group's commands are listed
    in place, the last one taking the group's separator). Redirections such as `2>&1` stay inside their command."""
    return _flat(parse(cmd))


def _bare(segment: str) -> str:
    """A simple command without its env assignments, wrappers and redirections, whitespace folded."""
    text = re.sub(r"\s+\d*[<>]+&?\s*\S+", " ", " " + segment).strip()
    text = " ".join(text.split())
    return _PREFIX.sub("", text)


def kind_of(segment: str) -> tuple[str, str] | None:
    """(kind, label) when a simple command is a verification command (a test runner, a build, a linter, a type
    checker), else None. Subshells and `sh -c` strings are not read. A run that only reports on the runner, lists
    what it would run or pretends (`--version`, `--help`, `--collect-only`, `--no-run`, `make -n`), a linter told to fix
    instead of check (`--fix`, `lint:fix`), and the tasks a gradle or maven run leaves out (`-x test`) verify nothing."""
    bare = _bare(segment)
    if not bare or bare.startswith(("(", "{", "$(")) or re.match(r"^(?:ba|z)?sh\s+-c\b", bare):
        return None
    words = bare.split()
    if _INFO_FLAGS & set(words) or (words[0] == "make" and _MAKE_DRY & set(words)) or _FIXING & set(words):
        return None
    matched = _EXCLUDED.sub(" ", bare)
    for kind, rx in VERIFY:
        found = rx.match(matched)
        if found:
            label = (found.group(1) if found.groups() and found.group(1) else words[0])
            if "fix" in label.lower():
                return None
            return kind, " ".join(label.split())[:40]
    return None


def tests_ran(output: str) -> bool | None:
    """Whether a test runner's output shows at least one test ran: True when it counts some, False when it says it ran
    none (`Ran 0 tests`, `collected 0 items`, `[no test files]`, `running 0 tests`, `No tests found`, `0 passing`),
    None when it says neither."""
    text = output or ""
    if any(rx.search(text) for rx in _SOME_TESTS):
        return True
    if any(rx.search(text) for rx in _NO_TESTS):
        return False
    return None


def _norm(cmd: str) -> str:
    return " ".join(_bare(cmd).split())


def checks_of(piece) -> list[tuple[str, str]]:
    """(statement id, command) for each runnable **Check:** of a piece: a command in backticks that is itself a
    verification (a test runner, a build, a linter, a type checker). A Check of `git status` or `cat VERSION` reads
    something and proves nothing, so it is not runnable, and running it is no evidence."""
    from athos import wiki
    out = []
    for st in wiki.statements(piece):
        for found in re.findall(r"`([^`\n]+)`", st.check or ""):
            if found.strip() and kind_of(found.strip()):
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


# `set -o pipefail` (or -euo pipefail, -e -o pipefail...) as a command of its own; `set +o pipefail` does not match.
_PIPEFAIL_ON = re.compile(r"^set\s+(?:-[a-zA-Z]+\s+)*-[a-zA-Z]*o\s+pipefail(?:\s+-[a-zA-Z]+)*$")
# A pure pager or filter that passes the output on and fails only on its own trouble: tail, head, tee, with plain
# options and file names. Anything that could run something else or decide on the text (grep, sort, awk) is not one.
_PURE_FILTER = re.compile(r"^(?:tail|head)(?:\s+(?:-[A-Za-z]+|--[a-z-]+(?:=\d+)?|[-+]?\d+[kmbcl]?))*$"
                          r"|^tee(?:\s+-[a-z]+)*(?:\s+[\w./-]+)*$")


def _success_through_pipefail(parts: list[tuple[str, str]], i: int) -> bool:
    """Whether a verification piped only into pure filters still owns the command's success: only when the command
    itself turns `pipefail` on first, chained with `&&` so a shell that cannot turn it on never runs the rest. Then the
    pipeline succeeds only if every part of it did, the verification included. The hook does not say how the shell
    was started, so without that `set` in the command a pipe stays weak. The verification must start its pipeline,
    every part after it be a pure filter, and the pipeline be the last thing that runs or be followed only by `&&`."""
    if parts[i][1] != "|" or (i and parts[i - 1][1] == "|"):
        return False
    if not all(s == "&&" for _, s in parts[:i]):
        return False
    sets = [n for n, (seg, _sep) in enumerate(parts[:i]) if _PIPEFAIL_ON.match(" ".join(seg.split()))]
    if not sets or any("pipefail" in seg for n, (seg, _sep) in enumerate(parts) if n not in sets):
        return False
    j = i + 1
    while j < len(parts):
        seg = " ".join(parts[j][0].split())
        if re.search(r"[$`()<>;&|\\'\"]", seg) or not _PURE_FILTER.match(seg):
            return False
        if parts[j][1] != "|":
            break
        j += 1
    else:
        return False
    return all(s in ("&&", "") for _, s in parts[j:])


def _text_of(node) -> str:
    return "( … )" if isinstance(node, Group) else node


# Where a command writes its standard output to a file instead of the tool's output (`> out.txt`, `&> log`, `>> x`);
# `2>&1`, `2> err.txt` and `>&2` leave it where the hook can read it.
_STDOUT_TO_FILE = re.compile(r"(?:^|\s)(?:1?>>?|&>>?)\s*(?!&)[^\s&]")


_PRINTERS = {"echo", "printf", "cat", "less", "more", "sed", "awk", "jq", "bat", "tac", "nl", "column", "fold",
             "yes"}


def _pure_pipe_after(parts: list, i: int) -> bool:
    """The verification starts its pipeline and everything it is piped into is a pure filter (tail, head, tee)."""
    if i and parts[i - 1][1] == "|":
        return False
    j = i
    while parts[j][1] == "|":
        j += 1
        if j >= len(parts):
            return False
        node = parts[j][0]
        seg = " ".join(_text_of(node).split())
        if isinstance(node, Group) or re.search(r"[$`()<>;&|\\'\"]", seg) or not _PURE_FILTER.match(seg):
            return False
    return True


def _walk(parts: list, owns_s: bool, owns_f: bool, checks: list, out: list, depth: int = 0) -> None:
    """Each verification in a list of (node, separator), with whether the whole command's exit status is its own.
    Within one list: the commands after the last `;`, newline or `&` before it are its and-or list; it owns a
    success when it is not piped or sent to the background, only `&&` comes before it in that list and only `&&` after
    it to the end (so the command succeeded only if it did), and a failure when it is also the last command and
    nothing but setup (`cd`, `export`, …) runs before it in its list. A group owns what its last command owns, and
    hands that down to the commands inside it."""
    flat = [(_text_of(node), sep) for node, sep in parts]
    for i, (node, sep) in enumerate(parts):
        start = max([n + 1 for n in range(i) if parts[n][1] in (";", "&")], default=0)
        piped = sep in ("|", "&") or (i and parts[i - 1][1] == "|")
        chain_before = all(parts[n][1] == "&&" for n in range(start, i))
        chain_after = all(parts[n][1] in ("&&", "") for n in range(i, len(parts)))
        local_s = not piped and chain_before and chain_after
        last = i == len(parts) - 1
        setup = all(not isinstance(parts[n][0], Group) and _SETUP.match(_bare(parts[n][0])) for n in range(start, i))
        local_f = not piped and last and chain_before and setup
        if local_s:
            rule = "alone" if len(parts) == 1 else ("last_in_sequence" if last and start == i else "and_chain")
        else:
            rule = ""
        if not local_s and depth == 0 and _success_through_pipefail(flat, i):
            local_s, rule = True, "pipefail"
        if isinstance(node, Group):
            _walk([tuple(p) for p in node.parts], owns_s and local_s, owns_f and local_f, checks, out, depth + 1)
            continue
        found = kind_of(node)
        if not found:
            continue
        out.append({"kind": found[0], "label": found[1], "check_of": _check_match(node, checks),
                    "owns_success": bool(owns_s and local_s), "owns_failure": bool(owns_f and local_f),
                    "rule": rule if owns_s and local_s else "",
                    "pure_pipe": bool(not sep == "&" and _pure_pipe_after(parts, i)),
                    "stdout_to_file": bool(_STDOUT_TO_FILE.search(" " + node)),
                    "background": sep == "&", "_text": node})


def classify(cmd: str, checks: list[tuple[str, str, str]] | None = None) -> list[dict]:
    """Every verification step of a shell command (read by `_Parser`: heredoc bodies, comments and substitutions
    run nothing here): each with its kind, label, the Check it runs (if any), whether the command's exit status
    belongs to it on success (`owns_success`) and on failure (`owns_failure`), and the rule that gave it the success
    (`rule`: `alone`, `and_chain`, `last_in_sequence` or `pipefail`; see `_walk`). A verification piped only into
    tail, head or tee owns the success only when the command turns `pipefail` on itself (`_success_through_pipefail`);
    a failure is never taken for a success."""
    out: list[dict] = []
    _walk(parse(cmd), True, True, checks or [], out)
    simple = [t for t, _ in segments(cmd)]
    for s in out:
        mine = s.pop("_text")
        # Something else in the command prints text of its own choosing (an echo, a log read back): a summary in the
        # output may then not be the runner's.
        s["others_print"] = any((_bare(t).split() or [""])[0] in _PRINTERS for t in simple if t != mine)
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
    """Append one item to a task's evidence. None (nothing written) without a task, or for a weak item past ITEMS_CAP
    weak items: a strong item (a failure, a revert, a change the person made) is never dropped, or a long task's last
    failure would go unseen and its earlier pass would still count."""
    if not task_id:
        return None
    from athos import eval as ev
    target = file_of(task_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    strong_item = item.get("strength") == "strong"
    try:
        lines = target.read_text().splitlines() if target.exists() else []
    except OSError:
        lines = []
    weak = sum(1 for line in lines if '"strength": "strong"' not in line)
    if (not strong_item and weak >= ITEMS_CAP) or len(lines) >= STRONG_CAP:
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


def _git_dir(cwd: str | None) -> Path | None:
    """The git folder of the repository a folder is in, found by looking at the disk only (no git process): the
    `.git` folder, or the folder a `.git` file points to (a worktree, a submodule). None outside any repository."""
    try:
        here = Path(cwd or os.getcwd()).resolve()
    except OSError:
        return None
    for folder in [here, *here.parents]:
        dot = folder / ".git"
        if dot.is_dir():
            return dot
        if dot.is_file():
            try:
                text = dot.read_text(errors="ignore").strip()
            except OSError:
                return None
            if text.startswith("gitdir:"):
                found = Path(text[7:].strip())
                return found if found.is_absolute() else (folder / found)
            return None
    return None


def _head_sha(cwd: str | None, short: bool = True) -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "--quiet", "--verify", *(["--short"] if short else []), "HEAD"],
                           cwd=cwd or None, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


def head(cwd: str | None) -> str:
    """The repository's HEAD: "" when there is none yet (or no repository)."""
    return _head_sha(cwd, short=False) or ""


def start_stamp(cwd: str | None) -> dict:
    """What the PreToolUse hook keeps of the repository before a shell command runs, so its end can see whether
    HEAD moved: {"head": the full hash ("" in a repository with no commit yet), "branch": the ref HEAD points to
    ("" when detached)}. Read from the git folder's files, without starting git (git is asked only when the files do
    not say, as with the reftable storage); {} outside a repository."""
    gd = _git_dir(cwd)
    if gd is None:
        return {}
    try:
        text = (gd / "HEAD").read_text(errors="ignore").strip()
    except OSError:
        return {}
    branch = text[5:].strip() if text.startswith("ref:") else ""
    sha = _read_ref(gd, branch) if branch else (text if _SHA.fullmatch(text) else None)
    return {"head": head(cwd) if sha is None else sha, "branch": branch}


_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


def _read_ref(gd: Path, ref: str) -> str | None:
    """The hash a branch points to, read from the git folder's files (the loose ref, else packed-refs; a worktree's
    refs live in its common folder): "" for a branch with no commit yet, None when the files do not say (another
    ref storage), and then git itself is asked."""
    common = gd
    try:
        if (gd / "commondir").is_file():
            found = Path((gd / "commondir").read_text().strip())
            common = found if found.is_absolute() else (gd / found)
        for folder in dict.fromkeys([gd, common]):
            loose = folder / ref
            if loose.is_file():
                value = loose.read_text(errors="ignore").strip()
                return value if _SHA.fullmatch(value) else None
        packed = common / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(errors="ignore").splitlines():
                bits = line.split()
                if len(bits) == 2 and bits[1] == ref and _SHA.fullmatch(bits[0]):
                    return bits[0]
        if (common / "reftable").exists():
            return None
    except OSError:
        return None
    return ""


_FRESH_SLACK_S = 2          # commit times are whole seconds: a commit made right as the call started is still its


def _commits_between(cwd: str | None, old: str, new: str) -> tuple[list[dict], list[dict]] | None:
    """(commits only behind the old HEAD, commits only behind the new one), newest first, each with its hash,
    parents and author and committer times; None when git cannot say (an old HEAD that no longer exists)."""
    rng = [f"{old}...{new}"] if old else [new]
    try:
        r = subprocess.run(["git", "log", "--left-right", "--format=%m %H %at %ct %P", "-n", "200", *rng, "--"],
                           cwd=cwd or None, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    left, right = [], []
    for line in r.stdout.splitlines():
        bits = line.split()
        if len(bits) < 4 or bits[0] not in "<>":
            continue
        c = {"sha": bits[1], "at": int(bits[2]), "ct": int(bits[3]), "parents": bits[4:]}
        (left if bits[0] == "<" and old else right).append(c)
    return left, right


COMMITS_PER_CALL = 20       # commits recorded for one tool call at most


def observe_head(cwd: str | None, started: dict | None, state: dict) -> list[dict]:
    """The items a tool call's effect on HEAD gives, whatever the command's text was (a heredoc message, `-F -`, an
    alias, a script that commits). Compares the PreToolUse stamp (`start_stamp`) with HEAD now:

        forward       one strong `commit` per commit reachable from the new HEAD and not from the old one that was
                      made during the call (author and committer times at or after its start): commits that only
                      arrived (a fast-forward pull or merge, a checkout) are not the task's
        amend         the tip replaced by one commit with the same parents, committed during the call: one `commit`
        backwards     same branch, commits dropped and none added (`git reset --hard HEAD~1`): a strong negative
                      `revert`, never a commit
        sideways      same branch, commits dropped and others added (a reset onto another commit, a rebase): a
                      strong `rewrite`, neither commit nor revert; commits authored during the call still count
        other branch  only commits made during the call count; nothing is dropped

    A commit while a subagent was working (it started a call after this one began) is kept weak: it may be the
    subagent's. Nothing without a stamp, or when HEAD did not move."""
    if not started or "head" not in started or not started.get("at"):
        return []
    now = start_stamp(cwd)
    old, new = started.get("head") or "", now.get("head") or ""
    if not now or not new or new == old:
        return []
    found = _commits_between(cwd, old, new)
    if found is None:
        return []
    left, right = found
    t0 = float(started["at"]) - _FRESH_SLACK_S
    same_branch = (now.get("branch") or "") == (started.get("branch") or "")
    out: list[dict] = []
    amend = (same_branch and len(left) == 1 and len(right) == 1 and right[0]["parents"] == left[0]["parents"]
             and right[0]["ct"] >= t0)
    if amend:
        made = [{**right[0], "amend": True}]
    else:
        if same_branch and left:
            kind = "rewrite" if right else "revert"
            out.append({"type": kind, "strength": "strong", "polarity": "negative" if kind == "revert" else "neutral",
                        "basis": "head_moved_back" if kind == "revert" else "head_moved_sideways",
                        "dropped": len(left)})
        made = [c for c in reversed(right) if c["at"] >= t0 and c["ct"] >= t0]
    live = session.live(state.get("_sid") or "") if state.get("_sid") else {}
    shared = float(state.get("subagent_at") or 0) >= float(started["at"]) or any(c.get("agent") for c in live.values())
    for c in made[-COMMITS_PER_CALL:]:
        item = {"type": "commit", "strength": "weak" if shared else "strong",
                "polarity": "neutral" if shared else "positive", "sha": c["sha"][:12], "basis": "head_moved",
                **({"amend": True} if c.get("amend") else {}),
                **({"why_weak": "a subagent was working at the same time: it may be its commit"} if shared else {})}
        out.append(item)
    return out


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


def background(event: dict) -> bool:
    """A tool call the agent sent to the background: its hook comes when it started, not when it ended, so the exit
    status it carries is not the command's (Claude Code: `run_in_background`, and a `backgroundTaskId` in the answer)."""
    tin = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    r = event.get("tool_response") if isinstance(event.get("tool_response"), dict) else {}
    return bool(tin.get("run_in_background") or r.get("backgroundTaskId") or r.get("backgroundTaskID"))


# ------------------------------------------------------------------------------------------------ runner summaries
# The final summary of a test runner whose format Athos reads exactly. Only these, and only when the command names the
# runner itself (`pytest`, `python -m unittest`, `jest`, `vitest`): `npm test` may run anything.
_PYTEST_COUNT = r"\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?|rerun)"
_SUMMARY = {
    "pytest": re.compile(rf"^(?:=+ )?((?:{_PYTEST_COUNT})(?:, {_PYTEST_COUNT})*) in \d+(?:\.\d+)?s"
                         r"(?: \(\d+:\d\d:\d\d\))?(?: =+)?[ \t]*$", re.M),
    "unittest": re.compile(r"^(Ran \d+ tests? in \d+(?:\.\d+)?s)[ \t]*\n[ \t]*\n(OK(?: \([^)\n]*\))?|FAILED \([^)\n]*\))"
                           r"[ \t]*$", re.M),
    "jest": re.compile(r"^Tests:\s+((?:\d+ (?:failed|skipped|todo|passed), )*\d+ total)[ \t]*$", re.M),
    "vitest": re.compile(r"^[ \t]*Tests[ \t]+((?:\d+ (?:failed|passed|skipped|todo))(?: \| \d+ (?:failed|passed|skipped|"
                         r"todo))*) \(\d+\)[ \t]*$", re.M),
}
_SUMMARY["py.test"] = _SUMMARY["pytest"]


def runner_summary(label: str, output: str) -> bool | None:
    """What a runner's own final summary in the output says: True when exactly one summary of that runner's exact
    format is there and it counts at least one passing test and no failure or error, False when exactly one is there
    and it counts a failure or an error, None otherwise (no summary, two of them, or a runner Athos does not read)."""
    rx = _SUMMARY.get(label)
    if rx is None:
        return None
    found = rx.findall(output or "")
    if len(found) != 1:
        return None
    text = " ".join(found[0]) if isinstance(found[0], tuple) else found[0]
    if label == "unittest":
        ran = int(re.search(r"Ran (\d+)", text).group(1))
        if "FAILED" in text:
            return False
        return True if ran > 0 else None
    if re.search(r"\b[1-9]\d* (?:failed|errors?)\b", text):
        return False
    return True if re.search(r"\b[1-9]\d* passed\b", text) else None


def _summary_may_decide(step: dict, steps: list[dict]) -> bool:
    """A step whose exit status is not its own may still be judged by its runner's summary: a test runner Athos reads,
    the only run of that runner in the command, piped (if at all) only into tail, head or tee, its output not sent to a
    file, not in the background, and nothing else in the command printing text of its own choosing."""
    return (step["kind"] == "test" and step["label"] in _SUMMARY and step.get("pure_pipe")
            and not step.get("stdout_to_file") and not step.get("background") and not step.get("others_print")
            and sum(1 for s in steps if s["label"] == step["label"]) == 1)


def on_tool(event: dict, sid: str, failed: bool = False, platform: str = "claude-code",
            started: dict | None = None) -> list[dict]:
    """A tool call ended (PostToolUse, or PostToolUseFailure with `failed`): a shell command that verified, committed
    or threw work away becomes an item of the open task. Subagents' calls and commands sent to the background are
    left out; Athos's own commands verify nothing, but a command that also runs one is still read. A commit is what
    HEAD did during the call (`observe_head`, from the PreToolUse stamp `started`), never what the command's text
    says."""
    from athos import edits
    if event.get("agent_id") or not edits.is_shell(event) or background(event):
        return []
    cmd = (event.get("tool_input") or {}).get("command")
    cmd = " ".join(map(str, cmd)) if isinstance(cmd, list) else str(cmd or "")
    if not cmd.strip():
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
    output_text = _output_of(event)
    for step in steps:
        owned = step["owns_success"] if ok else step["owns_failure"] if ok is False else False
        strong = ok is not None and owned
        item_ok = ok
        rule = (step["rule"] if ok else ("alone" if len(segments(cmd)) == 1 else "last_command")) if strong else ""
        why_weak = None if strong else ("exit status unknown" if ok is None else
                                        "exit status not this command's (piped, or not last in its chain)")
        if not strong and ok is True and _summary_may_decide(step, steps):
            said = runner_summary(step["label"], output_text)
            if said is not None:
                strong, item_ok, rule, why_weak = True, said, f"runner_summary:{step['label']}", None
        if strong and item_ok and step["kind"] == "test" and tests_ran(output_text) is False:
            strong, rule, why_weak = False, "", "no test ran (the runner said so)"
        # A chain with a verification in it failed and the failure cannot be pinned on anything: it counts against
        # the work until a later verification passes, or `pytest && npm run build` failing would leave an earlier
        # pass standing.
        unattributed = ok is False and not owned
        header = f"$ {'(command not kept: public repository)' if public else redact(cmd)}\n# exit: " + \
                 {True: "0 (succeeded)", False: "non-zero (failed)", None: "unknown"}[ok]
        output = _keep_output(task_id, output_text, header) if (strong or unattributed) else None
        item = {"type": "verify", "kind": step["kind"], "label": step["label"], "ok": item_ok,
                "strength": "strong" if (strong or unattributed) else "weak",
                "polarity": "positive" if item_ok and strong else "negative" if item_ok is False else "neutral",
                **({"rule": rule} if strong and rule else {}),
                **({"check_of": step["check_of"]} if step["check_of"] and strong else {}), **shown,
                **({"output": output} if output else {}),
                **({"unattributed": True} if unattributed else {}),
                **({} if strong or unattributed else {"why_weak": why_weak})}
        if add(task_id, item):
            added.append(item)
    observed = observe_head(event.get("cwd"), started, {**state, "_sid": sid})
    moved_back = any(i["type"] in ("revert", "rewrite") for i in observed)
    for item in observed:
        if add(task_id, item):
            added.append(item)
    if ok and not moved_back:
        for seg, _sep in segments(cmd):
            if _REVERT.match(_bare(seg)):
                item = {"type": "revert", "strength": "strong", "polarity": "negative", "basis": "command", **shown}
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
