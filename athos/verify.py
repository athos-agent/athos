"""The independent verifier: the model that did the work never grades it.

After an autonomous save (athos/autolearn.py), Athos writes a bundle of files for the task, `<home>/verify/<id>-v<n>-
<task>/`:

    diff.patch          what the task changed, from git: the commits it made and what is left uncommitted
    verification.txt    the output the tool hook kept of each verification command, with its exit status
    piece.md            the candidate piece, as stored
    checks.json         the piece's Check commands
    prompt.txt          the prompt the verifier got (fixed text and the four paths above, nothing else)
    result.json         what came back

and starts a separate process, detached so no hook waits for it: a headless run of the person's own Claude Code
(`claude -p`) with read-only tools (Read, Grep, Glob), a fresh context, `--safe-mode` (no plugins, hooks, CLAUDE.md
or MCP servers, so Athos itself is inert there), a throwaway ATHOS_HOME and ATHOS_HOOKS=off besides, no session kept,
a timeout, and a spending cap per run. It gets PATHS only: never the worker's summary, nor the conversation. It runs on
a different frontier model from the one that did the work when the settings name two (the same one otherwise, recorded
as `same_model_fallback`), and answers a fixed rubric, one verdict per criterion, as JSON.

Every run counts against a daily cap shared with replays (autolearn `budget`), and is recorded as a `model_run` event
with its cost when Claude Code reports one. A failed, refused or timed-out run leaves the piece a candidate and says
why in a `grade` and a `learn` event. The runner is a plain function (`claude_runner`), so tests pass their own.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from athos import autolearn, eval as ev, evidence, paths, session, store

CRITERIA = ("evidence_passed", "piece_matches_work", "checks_runnable", "no_private_data", "reusable")
INPUTS = ("diff.patch", "verification.txt", "piece.md", "checks.json")
DIFF_CAP = 200_000          # characters of the diff handed over
TOOLS = "Read,Grep,Glob"    # read-only: the verifier looks, it never changes anything
KNOWN_ALIASES = ("opus", "fable", "sonnet", "haiku")
MAX_ATTEMPTS = 2            # a verifier run that errored is retried once, later

PROMPT = """You are an independent verifier of a piece of know-how that another model wrote after doing some work. \
You did not do the work and you have not seen its conversation. Judge only what the files below show, reading them \
with your tools; anything they claim that the files do not show counts as not shown.

Files:
- the change the work made, as a diff: {diff}
- the output of the verification commands that ran, with their exit status: {output}
- the candidate piece: {piece}
- the piece's Check commands, as JSON: {checks}

Criteria:
1. evidence_passed: the verification output shows the commands ended successfully, with no failure after the last \
success.
2. piece_matches_work: every step of the piece is backed by the diff or the verification output; nothing in it \
claims what they do not show.
3. checks_runnable: at least one Check is a concrete command that could be run again later in this repository to tell \
whether its step went right.
4. no_private_data: the piece holds no secret, credential, personal data or folder of one particular computer.
5. reusable: the piece is a way of working someone could follow on a later task, not a narration of this one.

Answer with only this JSON object and nothing else:
{{"evidence_passed": {{"pass": true, "why": "<one short line>"}}, "piece_matches_work": {{"pass": true, "why": "..."}}, \
"checks_runnable": {{"pass": true, "why": "..."}}, "no_private_data": {{"pass": true, "why": "..."}}, \
"reusable": {{"pass": true, "why": "..."}}}}
(use false where a criterion is not met)"""


# ------------------------------------------------------------------------------------------------ the prompt
def prompt_for(bundle: Path) -> tuple[str, dict]:
    """The verifier's prompt for a bundle, and the paths it names: the fixed text with four paths, nothing else."""
    named = {"diff": str(bundle / "diff.patch"), "output": str(bundle / "verification.txt"),
             "piece": str(bundle / "piece.md"), "checks": str(bundle / "checks.json")}
    return PROMPT.format(**named), named


def paths_only(prompt: str, named: dict, bundle: str | Path) -> bool:
    """Whether a verifier prompt carries paths only: it is exactly the fixed text with the four bundle files filled
    in, each an absolute path to one of the allowed files inside the bundle. A prompt with the worker's summary, a
    transcript or any other text in it fails."""
    root = str(Path(bundle))
    if set(named) != {"diff", "output", "piece", "checks"}:
        return False
    for value in named.values():
        p = Path(value)
        if not p.is_absolute() or str(p.parent) != root or p.name not in INPUTS or "\n" in value:
            return False
    return prompt == PROMPT.format(**named)


# ------------------------------------------------------------------------------------------------ the bundle
def root() -> Path:
    return paths.home() / "verify"


def bundle_dir(piece: store.Piece, task_id: str | None) -> Path:
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{piece.id}-v{piece.version}-{task_id or 'none'}")
    return root() / name


def _git(cwd: str | None, *args: str) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd or None, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def task_diff(cwd: str | None, items: list[dict]) -> str:
    """What the task changed, from git only: each commit it made (`git show`), then what is still uncommitted against
    HEAD, then the new files git does not track yet, by name. Never anything the model wrote about it."""
    if not cwd or not _git(cwd, "rev-parse", "--git-dir"):
        return "(not a git repository: no diff available)\n"
    parts = []
    for item in items:
        if item.get("type") == "commit" and item.get("sha"):
            parts.append(_git(cwd, "show", "--stat", "--patch", "--no-color", item["sha"]))
    pending = _git(cwd, "diff", "--no-color", "HEAD")
    if pending.strip():
        parts.append("# uncommitted changes\n" + pending)
    new = _git(cwd, "ls-files", "--others", "--exclude-standard")
    if new.strip():
        parts.append("# new files not tracked by git\n" + new)
    text = "\n".join(p for p in parts if p.strip()) or "(no change found in git)\n"
    return text[:DIFF_CAP] + ("\n… (cut)\n" if len(text) > DIFF_CAP else "")


def _verification_text(items: list[dict]) -> str:
    lines = ["# verification commands the hooks saw in this task, oldest first", ""]
    for i in items:
        if i.get("type") != "verify":
            continue
        status = {True: "succeeded", False: "failed", None: "unknown"}[i.get("ok")]
        lines.append(f"- {i.get('kind')} ({i.get('label')}): {status}, {i.get('strength')} evidence"
                     + (f", the Check of {i['check_of']}" if i.get("check_of") else ""))
    for out in evidence.outputs(items):
        lines += ["", f"## {Path(out).name}", Path(out).read_text(errors="ignore")]
    return "\n".join(lines) + "\n"


def build_bundle(piece: store.Piece, task_id: str | None, cwd: str | None) -> Path:
    """Write the verifier's four input files for a candidate, from git, the hooks' evidence and the store."""
    items = evidence.of_task(task_id)
    folder = bundle_dir(piece, task_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "diff.patch").write_text(task_diff(cwd, items))
    (folder / "verification.txt").write_text(_verification_text(items))
    (folder / "piece.md").write_text(store.render(piece))
    checks = [{"statement": sid, "command": cmd} for sid, cmd in evidence.checks_of(piece)]
    (folder / "checks.json").write_text(json.dumps(checks, indent=1, ensure_ascii=False))
    (folder / "meta.json").write_text(json.dumps({"piece": piece.id, "version": piece.version, "task_id": task_id,
                                                  "worker_model": piece.learned_by, "attempts": 0}))
    return folder


# ------------------------------------------------------------------------------------------------ which model
def family(model: str | None) -> str:
    """`opus` for claude-opus-5-5 or the alias opus; "" when it can't be told."""
    m = (model or "").strip().lower()
    if m in KNOWN_ALIASES:
        return m
    found = re.match(r"claude-([a-z]+)-", m)
    return found.group(1) if found else ""


def candidates() -> list[str]:
    """The models a verifier may run on: the settings' list, else one per frontier family the tiers name (an exact id
    as written, a `claude-<family>-*` pattern as its Claude Code alias when there is one)."""
    from athos import tiers
    chosen = autolearn.settings()["verifier"].get("models")
    if isinstance(chosen, list) and chosen:
        return [str(m) for m in chosen]
    out = []
    for p in tiers.patterns()[tiers.FRONTIER]:
        if not re.search(r"[*?\[]", p):
            out.append(p)
        else:
            fam = re.match(r"claude-([a-z]+)-\*$", p.lower())
            if fam and fam.group(1) in KNOWN_ALIASES:
                out.append(fam.group(1))
    return list(dict.fromkeys(out))


def pick_model(worker: str | None) -> tuple[str, bool]:
    """(model, same_model_fallback): the first candidate of another family than the worker's; else the first one (or
    the worker's own model), recorded as a fallback."""
    options = candidates()
    mine = family(worker)
    for m in options:
        if family(m) and family(m) != mine:
            return m, False
    return (options[0] if options else (worker or "opus")), True


# ------------------------------------------------------------------------------------------------ the budget
def _today() -> str:
    return ev.now().astimezone(_dt.timezone.utc).date().isoformat()


def spent_today() -> tuple[int, float]:
    """(runs, US$) of every model run Athos started today (UTC): verifier and replay together. A run that reported
    no cost counts the settings' estimate."""
    estimate = float(autolearn.settings()["budget"].get("usd_estimate_per_run") or 0)
    runs, usd = 0, 0.0
    for e in ev.events():
        if e.get("type") == "model_run" and str(e.get("at", ""))[:10] == _today() and e.get("started", True):
            runs += 1
            usd += float(e["cost_usd"]) if isinstance(e.get("cost_usd"), (int, float)) else estimate
    return runs, round(usd, 4)


def allowance(per_run: float | None = None) -> tuple[bool, str, float]:
    """Whether another model run fits today's cap, why not, and the most it may spend (the per-run cap, cut to what
    is left of the day's)."""
    s = autolearn.settings()
    budget = s["budget"]
    runs, usd = spent_today()
    left = float(budget.get("usd_per_day") or 0) - usd
    if runs >= int(budget.get("runs_per_day") or 0):
        return False, f"daily cap of {budget.get('runs_per_day')} runs reached", 0.0
    if left < 0.01:
        return False, f"daily cap of US${budget.get('usd_per_day')} reached", 0.0
    cap = per_run if per_run is not None else float(s["verifier"].get("max_usd_per_run") or 0)
    return True, "", round(min(cap, left), 4)


def note_run(purpose: str, piece: store.Piece | None, model: str, result: dict | None, cap: float,
             refused: str = "", **more) -> dict:
    """The `model_run` event: a run Athos started (or refused to start), what it cost, the caps it ran under."""
    s = autolearn.settings()
    cost = (result or {}).get("cost_usd")
    event = {"type": "model_run", "purpose": purpose, "piece": piece.id if piece else None,
             "version": piece.version if piece else None, "model": model, "started": not refused,
             "refused": refused or None, "ok": bool(result and result.get("ok")),
             "error": (result or {}).get("error"), "cost_usd": cost if isinstance(cost, (int, float)) else None,
             "cost_estimated": not isinstance(cost, (int, float)) and not refused,
             "usd_cap_run": cap, "usd_per_day": s["budget"].get("usd_per_day"),
             "runs_per_day": s["budget"].get("runs_per_day"), "duration_s": (result or {}).get("duration_s"),
             "usd_estimate_per_run": s["budget"].get("usd_estimate_per_run"),
             "project": piece.projects[0] if piece and piece.projects else None, **more}
    ev.audit(event)
    return event


# ------------------------------------------------------------------------------------------------ the runner
def child_env(home: str) -> dict:
    """The verifier's environment: a throwaway ATHOS_HOME and Athos's hooks and capture off, so nothing it does reaches
    the person's store even if a hook ran (with `--safe-mode` none does)."""
    env = {**os.environ, "ATHOS_HOME": home, "ATHOS_HOOKS": "off", "ATHOS_CAPTURE": "off",
           "CLAUDE_CODE_AUTO_CONNECT_IDE": "false"}
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    return env


def command(prompt: str, model: str, bundle: Path, max_usd: float) -> list[str]:
    return ["claude", "-p", prompt, "--output-format", "json", "--model", model, "--tools", TOOLS,
            "--allowedTools", TOOLS.replace(",", " "), "--permission-mode", "dontAsk", "--no-session-persistence",
            "--safe-mode", "--strict-mcp-config", "--max-budget-usd", f"{max_usd:.2f}", "--add-dir", str(bundle)]


def claude_runner(prompt: str, bundle: Path, model: str, timeout: float, max_usd: float) -> dict:
    """One headless Claude Code run, isolated (see `child_env` and `command`). {ok, text, cost_usd, error,
    duration_s}; never raises for a run that failed."""
    home = tempfile.mkdtemp(prefix="athos-verifier-")
    t0 = time.monotonic()
    try:
        r = subprocess.run(command(prompt, model, bundle, max_usd), cwd=str(bundle), env=child_env(home),
                           capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {"ok": False, "text": "", "cost_usd": None, "error": f"timeout after {timeout:.0f} s",
                "duration_s": round(time.monotonic() - t0, 1)}
    except OSError as problem:
        return {"ok": False, "text": "", "cost_usd": None, "error": f"could not start claude: {type(problem).__name__}",
                "duration_s": 0.0}
    finally:
        shutil.rmtree(home, ignore_errors=True)
    took = round(time.monotonic() - t0, 1)
    try:
        out = json.loads(r.stdout)
    except ValueError:
        return {"ok": False, "text": "", "cost_usd": None, "duration_s": took,
                "error": f"exit {r.returncode}: " + " ".join((r.stderr or r.stdout).split())[-200:]}
    cost = out.get("total_cost_usd")
    bad = bool(out.get("is_error")) or r.returncode != 0
    return {"ok": not bad, "text": str(out.get("result") or ""), "cost_usd": cost, "duration_s": took,
            "error": (" ".join(str(out.get("result") or out.get("subtype") or "error").split())[:200] if bad else None)}


def verdict_of(text: str) -> dict | None:
    """Each criterion's verdict ({criterion: {"pass": bool, "why": str}}) from the verifier's answer; None when it
    holds no readable JSON object. A criterion it did not answer fails."""
    found = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(found.group(0)) if found else None
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    out = {}
    for c in CRITERIA:
        v = data.get(c)
        ok = v.get("pass") is True if isinstance(v, dict) else v is True
        why = str(v.get("why") or "")[:200] if isinstance(v, dict) else ("" if c in data else "not answered")
        out[c] = {"pass": ok, "why": why}
    return out


# ------------------------------------------------------------------------------------------------ one verification
def run(piece_id: str, bundle: Path | None = None, runner=claude_runner) -> dict:
    """Verify one candidate from its bundle: check the cap, pick the model, run, read the verdict, record it (`verify`,
    `model_run`, `grade` and `learn` events) and hand it to the grading (athos/grade.py). Returns the outcome."""
    piece = store.get(piece_id)
    if piece is None:
        return {"piece": piece_id, "outcome": "error", "error": "no such piece"}
    folder = Path(bundle) if bundle else _bundle_of(piece)
    meta = _meta(folder) if folder else {}
    if folder is None or not all((folder / f).is_file() for f in INPUTS):
        return _record(piece, None, None, None, "error", "no bundle for this piece", meta)
    s = autolearn.settings()
    if not s["verifier"].get("on"):
        return _record(piece, folder, None, None, "skipped", "the verifier is off", meta)
    allowed, why, cap = allowance()
    model, fallback = pick_model(piece.learned_by or meta.get("worker_model"))
    if not allowed:
        note_run("verify", piece, model, None, 0.0, refused=why)
        return _record(piece, folder, model, None, "skipped", why, meta, fallback=fallback)
    prompt, named = prompt_for(folder)
    (folder / "prompt.txt").write_text(prompt)
    meta["attempts"] = int(meta.get("attempts") or 0) + 1
    (folder / "meta.json").write_text(json.dumps(meta))
    result = runner(prompt, folder, model, float(s["verifier"].get("timeout_s") or 300), cap)
    (folder / "result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    note_run("verify", piece, model, result, cap)
    if not result.get("ok"):
        return _record(piece, folder, model, None, "error", result.get("error") or "the run failed", meta,
                       fallback=fallback, cost=result.get("cost_usd"), named=named, prompt=prompt)
    verdict = verdict_of(result.get("text", ""))
    if verdict is None:
        return _record(piece, folder, model, None, "error", "the answer held no readable verdict", meta,
                       fallback=fallback, cost=result.get("cost_usd"), named=named, prompt=prompt)
    passed = all(v["pass"] for v in verdict.values())
    out = _record(piece, folder, model, verdict, "pass" if passed else "fail", "", meta, fallback=fallback,
                  cost=result.get("cost_usd"), named=named, prompt=prompt)
    after = store.get(piece_id)
    if passed and after is not None and after.status == "candidate" and s["replay"].get("on"):
        from athos import replay              # off by default: a replay on an apply model costs two more runs
        out["replay"] = replay.run_candidate(piece_id, runner)
    return out


def _bundle_of(piece: store.Piece) -> Path | None:
    found = sorted(root().glob(re.sub(r"[^A-Za-z0-9_.-]", "_", f"{piece.id}-v{piece.version}-") + "*"))
    return found[-1] if found else None


def _meta(folder: Path | None) -> dict:
    try:
        return json.loads((folder / "meta.json").read_text()) if folder else {}
    except (OSError, ValueError):
        return {}


def _record(piece: store.Piece, folder: Path | None, model: str | None, verdict: dict | None, outcome: str,
            error: str, meta: dict, fallback: bool = False, cost=None, named: dict | None = None,
            prompt: str | None = None) -> dict:
    """The `verify` event, then the grading's turn (a verdict may promote the piece; anything else leaves it as it
    is and says why)."""
    from athos import grade
    out = {"piece": piece.id, "version": piece.version, "task_id": meta.get("task_id"), "outcome": outcome,
           "model": model, "worker_model": piece.learned_by or meta.get("worker_model"),
           "same_model_fallback": fallback, "verdict": {c: v["pass"] for c, v in (verdict or {}).items()} or None,
           "why": {c: v["why"] for c, v in (verdict or {}).items()} or None, "error": error or None,
           "cost_usd": cost if isinstance(cost, (int, float)) else None, "bundle": str(folder) if folder else None,
           "inputs": sorted(Path(v).name for v in (named or {}).values()) or None,
           "prompt_file": str(folder / "prompt.txt") if folder and prompt else None,
           "paths_only": paths_only(prompt, named, folder) if prompt and named and folder else None,
           "attempts": meta.get("attempts", 0), "body_sha": grade.body_sha(piece)}
    project = piece.projects[0] if piece.projects else None
    ev.audit({"type": "verify", **out, "project": project},
             line=f"verifier on {_name(piece, project)}: {outcome}" + (f" ({error})" if error else "")
             + (f" · {model}" if model else "") + (" · same model as the worker" if fallback and model else ""),
             project=project)
    grade.on_verdict(piece.id, out)
    return out


def _name(piece: store.Piece, project: str | None) -> str:
    from athos import load
    return load.loggable([piece], project)


# ------------------------------------------------------------------------------------------------ starting it
def pending() -> list[tuple[str, Path]]:
    """Candidates whose current version has a bundle and no verdict yet (never run, or an error to retry while
    attempts remain), oldest first."""
    done = {}
    for e in ev.events():
        if e.get("type") == "verify" and e.get("outcome") in ("pass", "fail"):
            done[(e.get("piece"), e.get("version"))] = True
    out = []
    for p in store.all_pieces():
        if p.status != "candidate" or (p.id, p.version) in done:
            continue
        folder = _bundle_of(p)
        if folder and int(_meta(folder).get("attempts") or 0) < MAX_ATTEMPTS:
            out.append((p.id, folder))
    return out


def _lock() -> Path:
    return root() / ".running"


def running() -> bool:
    try:
        limit = float(autolearn.settings()["verifier"].get("timeout_s") or 300) + 60
        return time.time() - _lock().stat().st_mtime < limit
    except OSError:
        return False


def spawn(athos_cmd: Path, args: list[str], popen=subprocess.Popen) -> bool:
    """Start `athos verify …` detached, at low priority, printing nothing: the hook or the save never waits. Nothing
    starts with ATHOS_SPAWN=off (the tests) unless a stub `popen` is passed."""
    if os.environ.get("ATHOS_SPAWN", "").lower() == "off" and popen is subprocess.Popen:
        return False
    argv = [sys.executable, str(athos_cmd), "verify", *args, "--quiet"]
    if os.name == "posix" and Path("/usr/bin/nice").exists():
        argv = ["/usr/bin/nice", "-n", "10", *argv]
    try:
        popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              start_new_session=True, close_fds=True)
    except OSError:
        return False
    return True


def after_save(piece: store.Piece, state: dict, cwd: str | None, athos_cmd: Path, popen=subprocess.Popen) -> bool:
    """Right after `athos save --auto`: write the bundle and start the verifier in the background, when it is on and
    today's cap allows; otherwise the piece stays a candidate and a `grade` event says why. Returns whether it
    started."""
    from athos import grade
    folder = build_bundle(piece, state.get("task_id"), cwd)
    if not autolearn.settings()["verifier"].get("on"):
        grade.note(piece.id, "candidate", "candidate", "verifier_off")
        return False
    allowed, why, _cap = allowance()
    if not allowed:
        grade.note(piece.id, "candidate", "candidate", f"verifier_not_started: {why}")
        return False
    return spawn(athos_cmd, [piece.id, "--bundle", str(folder)], popen)


def maybe_spawn_pending(athos_cmd: Path, popen=subprocess.Popen) -> bool:
    """Stop hook: a candidate still waiting for its verdict (the cap was reached, or the run errored) is verified now,
    in the background, when the verifier is on, idle, and today's cap allows."""
    if not autolearn.settings()["verifier"].get("on") or running() or not allowance()[0] or not pending():
        return False
    return spawn(athos_cmd, ["--pending"], popen)


def run_pending(runner=claude_runner, limit: int = 1) -> list[dict]:
    out = []
    for pid, folder in pending()[:limit]:
        out.append(run(pid, folder, runner))
    return out


def take_lock() -> bool:
    if running():
        return False
    root().mkdir(parents=True, exist_ok=True)
    _lock().write_text(str(os.getpid()))
    return True


def release_lock() -> None:
    _lock().unlink(missing_ok=True)
