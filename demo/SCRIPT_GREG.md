# Twenty seconds: the same know-how, Claude Code then Codex

One folder, two agents. Claude Code already learned how this package is released (demo/prep.sh, off camera); now it
releases 0.3.0 with that know-how, and Codex releases 0.4.0 in the same folder without being told anything. The bars
under the prompt, and `athos watch` beside Codex, show how each one applied it: success over the marked tasks, mean
time, and time saved against the first run.

## Before the take

```
sh demo/setup.sh && sh demo/prep.sh
```

Layout: one tmux window, Claude Code / Codex on the left, `athos watch` on the right (`athos watch` in
`~/athos-demo/greet`, with the same three lines setup.sh printed).

## The take (real time about 80 s; the GIF speeds up the waits to 20 s)

| GIF | What happens |
|---|---|
| 0–5 s | Claude Code: `Release 0.3.0 with a new name_upper option for greet() that uppercases the name.` It works with the release piece loaded. Press **Good** on the band. The orange bar fills: `1/1 good · NN s · NN% time saved`. |
| 5–8 s | Quit Claude Code. In the same folder: `codex`. |
| 8–15 s | Codex: `Release 0.4.0 with a new name_lower option for greet() that lowercases the name.` No conventions given. It bumps both versions, adds the changelog entry on top, commits `release 0.4.0`, tags `v0.4.0` "greet 0.4.0". |
| 15–20 s | Press **g** in `athos watch`. The blue bar fills next to the orange one. End card: "Your know-how. Any agent." |

Record it with any screen recorder and cut the waits; Codex asks before writing to `.git` (its sandbox), so approve
that on camera or cut it. The numbers on screen are the real ones of that take, never edited.
