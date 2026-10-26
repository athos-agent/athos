# Demo script (2 minutes)

One real, repeatable task: releasing a tiny Python package with house conventions that no model can guess. Claude Code
learns them once; Codex reuses them; the report shows what each brought.

## Before each take

```
sh demo/setup.sh
export ATHOS_HOME=~/athos-demo/home
alias athos="python3 <path printed by setup.sh>"
```

Two terminals, both with those two lines run, font large enough to read. Codex logged in. The demo store starts empty,
so the status line reads `athos · 0 pieces`.

## 0:00–0:15 · The problem

Say: *"Every time I teach an AI how we do things here, that know-how stays locked in one tool and one chat. Athos
makes it mine."*

## 0:15–0:50 · Claude Code solves it, Athos captures it

Terminal 1:

```
cd ~/athos-demo/greet-claude
claude
```

Prompt (paste):

```
Release version 0.2.0 and add an `excited` option to greet() that ends with '!!!'. Our conventions: the version lives in TWO places (pyproject.toml and greet/__init__.py __version__); the CHANGELOG entry goes on top as '## [X.Y.Z] - YYYY-MM-DD' with '### Added' / '### Fixed'; run the tests before tagging; commit 'release X.Y.Z' and an annotated tag 'vX.Y.Z' whose message is 'greet X.Y.Z'.
```

When it finishes, Athos asks Claude to save what it learned; show the line "saved release-…", then the file:

```
athos list
```

Press **Good** on the band (or `/athos:mark g`). Exit Claude Code.

## 0:50–1:20 · Codex solves the same task, no explanation

Terminal 2:

```
cd ~/athos-demo/greet-codex
athos export --codex .agents/skills
codex "Release 0.3.0 with a new name_upper option for greet() that uppercases the name."
```

Point at Codex saying it uses the release skill, both version strings, the changelog format, the `release 0.3.0` commit
and the `greet 0.3.0` tag. Codex asks to run git outside its sandbox: approve it. Then mark it:

```
athos mark g
```

## 1:20–1:45 · What each model brought, on my work

```
athos report
```

Read two lines aloud: the piece's uses and success, and the two models side by side on my own tasks. Say:
*"Benchmarks measure someone else's tests. This measures mine."*

## 1:45–2:00 · Run it fast, locally

Terminal 2, same folder. Undo Codex's release so the local model can do it again (the id is the one `athos list`
showed). Have `ollama serve` running and the model already loaded (run any short prompt with it before the take):

```
git reset -q --hard HEAD~1 && git tag -d v0.3.0
athos delegate <the release piece's id> "Release 0.3.0 with a new name_upper option for greet() that uppercases the name." --model gemma4:12b
```

Approve each command as it is shown, then `athos report` again: a third line, `local / gemma4:12b`. Say: *"What I
have mastered now runs on my machine."*

Close on: *"Your AI know-how. Free to move, fast to run."*

## Timing (rehearsed headless, 2026-10-25)

Claude Code took 37 s including the capture, Codex 32 s, and the report is instant. That is about a minute and a
quarter of waiting inside a two-minute script, so paste the prompts rather than type them, and trim the waits in the
edit. In the rehearsal, Codex's sandbox kept `.git` read-only and it printed the exact `release 0.3.0` commit and
`greet 0.3.0` tag instead of running them. Interactively it asks to run them; approve.

Delegation, rehearsed on 2026-10-26 on a 16 GB Mac: gemma4:12b did the release (both versions, option, test, commit and
tag) in 93 s, but replaced the previous CHANGELOG entry instead of adding above it; a 4B model failed. Check
`git show HEAD -- CHANGELOG.md` before the take, and cut the wait in the edit. With other heavy apps open it took 6
minutes: close them.

## If a take goes wrong

Run `sh demo/setup.sh` again: it wipes `~/athos-demo` (projects and demo store) and starts over. Your real
`~/.athos` is never touched.
