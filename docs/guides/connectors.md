# Connectors: when a way of working needs a service

*Español: [conectores.md](conectores.md)*

Some ways of working need something outside the agent to be done well. A lawyer's contract review should not send a
client's name, email or bank account to a cloud model; a gateway that masks them first is part of *how* that lawyer
works. Athos calls such a service a **connector**.

A way of working asks for a connector where a step needs it, with `[[connector:<name>]]`. When that way of working is
loaded, Athos checks the connector and tells both the model and you:

- **Active**: the model is told that personal data may reach it as placeholders like `[[PERSON_7f3a]]` and to keep them
  exactly as they are; the panel shows **🔒 personal data goes through pii-guard**.
- **Not running**: the model is told not to process client personal data and to ask you to start it or anonymise; the
  panel shows **⚠ pii-guard is not running**.

Athos never starts a service or changes an agent's settings on its own: you run the service, and you choose which
agent goes through it.

## The first connector: pii-guard

[pii-guard](https://github.com/watt-mind/pii-guard) (Watt Mind, Apache-2.0) is an OpenAI-compatible gateway that runs on
your computer. Names, emails, addresses, IDs and bank accounts become reversible placeholders before the request leaves,
and come back with the real values in the answer. Language packs: Hungarian, English, German, Polish.

### 1. Start pii-guard (in its own terminal)

It needs [uv](https://docs.astral.sh/uv/) and a key for the model behind it (here Meta's Model API):

```bash
export META_API_KEY="<your key>"          # or read it from where you keep it
uvx --python 3.12 --from 'wattmind-pii-guard[ner] @ git+https://github.com/watt-mind/pii-guard' pii-guard up --upstream meta
```

The first run downloads about 2 GB (PyTorch and its name model). It is ready when it listens on `127.0.0.1:8787`; keep
that terminal open. Check: `curl -s http://127.0.0.1:8787/v1/status`.

### 2. Tell Athos about it

```bash
athos connector add pii-guard     # writes ~/.athos/connectors/pii-guard.md (readable, editable)
athos connector check pii-guard   # active / not running
athos connector list
```

### 3. Ask for it in a way of working

In the step where client data comes in, name it. The law starters (`athos start --profile law`) already do:

```markdown
## #data_out
**When:** before pasting or opening the contract.
**Do:** confirm whether it holds client data; if so, propose anonymising, running the task through
[[connector:pii-guard]], or a local model.
```

### 4. Send your agent through it

pii-guard works with agents unchanged: only the model's base URL changes. In OpenCode, a provider in `opencode.json`:

```json
{ "provider": { "pii-guard": { "npm": "@ai-sdk/openai-compatible", "name": "pii-guard → Meta",
    "options": { "baseURL": "http://127.0.0.1:8787/v1", "apiKey": "unused" },
    "models": { "muse-spark-1.3": {} } } },
  "model": "pii-guard/muse-spark-1.3" }
```

For other agents, `athos connector wire pii-guard <agent>` prints pii-guard's own command (codex, muse-code,
claude-code); see pii-guard's [integration guides](https://github.com/watt-mind/pii-guard/tree/develop/docs/integrations).

### What it looks like

Checked with OpenCode 1.19.5 on Muse Spark 1.3 and a fictional lease holding two people, two emails, a phone, an
address, a date of birth and a bank account. pii-guard masked all of them before the request left; the answer came back
with no placeholder and the real values; OpenCode's sidebar showed *Following «Review a contract against your
checklist» · All 4 steps applied · 🔒 data through pii-guard*.

## Write your own

A connector is a markdown file in `~/.athos/connectors/<name>.md`:

```markdown
---
name: my-gateway
kind: gateway                      # gateway (model traffic), tool (an MCP server) or command (a local CLI)
what: one line the person and the model read
check: http://127.0.0.1:9000/health  # Athos calls it (1 s); no check = always active
start: the command you run to start it
---
Notes for you and for the model.
```

pii-guard is pseudonymisation, not anonymisation or a compliance guarantee: anything its detectors miss passes through.
You are still the one who decides what client data goes into a task.
