---
description: Keep what this task taught as a piece of your know-how, right now
allowed-tools: Bash(python3:*)
---
Look back over the work in this conversation and judge whether it taught something worth reusing: the way the problem
was solved, the criteria that decided it, the steps in order, the mistakes that were avoided. When it taught nothing
reusable, say that in a single line and stop. Otherwise keep exactly one piece, with this command:

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/athos" save <<'EOF'
---
title: <a few words, as an instruction: what this piece does>
when: <the situation it is for, precise enough that a later request for it matches>
id: <only when improving a piece that already exists: that piece's id>
note: <only when improving: what changed, and the reason>
---
<the way it was solved: steps, criteria, commands, mistakes to avoid. Copy the user's own conventions exactly as they
are (names, message formats, paths, flags) and never replace them with placeholders. Leave out secrets, tokens and
personal data.>
EOF
```

Finish with one line telling the user which piece you saved or improved.
