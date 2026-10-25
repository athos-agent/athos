---
description: Save what this task taught as a piece of your know-how, now
allowed-tools: Bash(python3:*)
---
Decide whether the work in this conversation taught reusable know-how: how it was solved, the criteria, the steps,
the mistakes avoided. If it did not, say so in one line. If it did, save exactly one piece by running:

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/athos" save <<'EOF'
---
title: <short imperative title>
when: <the situation this applies to, specific enough to match a future request>
id: <only to improve an existing piece: its id>
note: <only when improving: what changed and why>
---
<how it was solved: steps, criteria, commands, mistakes to avoid. Keep the user's exact conventions verbatim (names,
message formats, paths, flags); never turn them into placeholders. No secrets, tokens or personal data.>
EOF
```

Then tell the user in one line which piece was saved or improved.
