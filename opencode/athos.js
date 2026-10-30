// Athos for OpenCode: the same know-how as in Claude Code, Codex and Muse Code.
//
// Installed by `athos opencode --install` into ~/.config/opencode/plugins/athos.js, with ATHOS set to the athos
// command. Each OpenCode moment is handed to the same `athos hook` Claude Code uses, as platform `opencode`:
//   first message of a session  → session-start (the index of your know-how and how to save a piece)
//   every message                → prompt (the pieces that match it, added to the system prompt for this turn)
//   every tool call              → tool (counts work, so Athos only asks to save after a turn that changed something)
//   the session goes idle        → stop (records the task; if it was real work, asks once whether to save a piece)
// A failing hook never breaks the session: errors are ignored and OpenCode carries on.

import { execFileSync } from "node:child_process"

const ATHOS = process.env.ATHOS_BIN || "__ATHOS__"

// OpenCode's tool names, in the names Athos knows (the rest count as work).
const TOOLS = { read: "Read", grep: "Grep", glob: "Glob", list: "LS", webfetch: "WebFetch", websearch: "WebSearch",
  todowrite: "TodoWrite", todoread: "TodoWrite", bash: "Bash", edit: "Edit", write: "Write", patch: "Edit" }

export const AthosPlugin = async ({ directory, client }) => {
  const sessions = new Map()      // sessionID → { started, index, context, model, tokens, asking, askedText }
  const state = (id) => {
    if (!sessions.has(id)) sessions.set(id, { started: false, index: "", context: "", model: "", tokens: {} })
    return sessions.get(id)
  }

  // Synchronous on purpose: `opencode run` exits right after the session goes idle, without waiting for plugins.
  function hook(event, payload) {
    try {
      const out = execFileSync(ATHOS, ["hook", event, "--platform", "opencode"],
        { input: JSON.stringify(payload), encoding: "utf8", stdio: ["pipe", "pipe", "ignore"], timeout: 30000 })
      return out.trim() ? JSON.parse(out) : null
    } catch {
      return null
    }
  }
  const context = (out) => out?.hookSpecificOutput?.additionalContext || ""

  // The trail in OpenCode's own screen: a toast each time the task moves to another step of the person's know-how
  // (the full panel is `athos watch --web` beside it). Silent where there is no TUI (`opencode run`).
  let lastStep = ""
  function status() {
    try {
      return JSON.parse(execFileSync(ATHOS, ["status", "--json"],
        { cwd: directory, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"], timeout: 15000 }).trim().split("\n").pop())
    } catch {
      return null
    }
  }
  async function toastStep() {
    const st = status()
    const p = st?.trail?.pieces?.[0]
    if (!p) return
    const es = st.lang === "es"
    const i = p.steps.findIndex((x) => x.state === "now")
    const done = p.steps.filter((x) => x.state === "done").length
    const message = i >= 0
      ? (es ? `Athos · Paso ${i + 1} de ${p.steps.length}: ` : `Athos · Step ${i + 1} of ${p.steps.length}: `) + p.steps[i].label
      : done === p.steps.length ? (es ? `Athos · Apliqué los ${done} pasos de «${p.title}»` : `Athos · All ${done} steps of «${p.title}» done`)
      : ""
    if (!message || message === lastStep) return
    lastStep = message
    try {
      await client.tui.showToast({ body: { message, variant: "info" } })
    } catch {}
  }

  return {
    "chat.message": async (input, output) => {
      const s = state(input.sessionID)
      const prompt = output.parts.filter((p) => p.type === "text" && !p.synthetic).map((p) => p.text).join("\n")
        .replace(/^"([\s\S]*)"$/, "$1")             // `opencode run "<request>"` sends the quotes too
      if (s.asking && prompt === s.askedText) return        // our own "anything to keep?" line is not a new task
      s.asking = false
      const model = input.model || output.message?.model
      if (model?.providerID) s.model = `${model.providerID}/${model.modelID}`
      const base = { session_id: input.sessionID, cwd: directory, model: s.model || undefined }
      if (!s.started) {
        s.started = true
        s.index = context(hook("session-start", base))
      }
      s.tokens = {}
      s.open = true
      s.context = context(hook("prompt", { ...base, prompt }))
    },

    "experimental.chat.system.transform": async (input, output) => {
      const s = input.sessionID && sessions.get(input.sessionID)
      if (!s) return
      if (s.index) output.system.push(s.index)
      if (s.context) output.system.push(s.context)
    },

    "tool.execute.after": async (input) => {
      hook("tool", { session_id: input.sessionID, cwd: directory,
        tool_name: TOOLS[input.tool] || input.tool, tool_input: input.args || {} })
      if (/\bstep\b/.test(String(input.args?.command || ""))) await toastStep()
    },

    event: async ({ event }) => {
      if (event.type === "message.updated") {
        const m = event.properties?.info
        if (m?.role === "assistant" && m.tokens) {
          const s = state(m.sessionID)
          s.tokens[m.id] = m.tokens
          if (m.providerID && m.modelID) s.model = `${m.providerID}/${m.modelID}`
        }
        return
      }
      if (event.type !== "session.idle") return
      const id = event.properties?.sessionID
      if (id && sessions.has(id)) await stop(id, true)
      await toastStep()
    },

    // `opencode run` closes right after the session goes idle: record what is still open, without asking.
    dispose: async () => {
      for (const [id, s] of sessions) if (s.open) await stop(id, false)
    },
  }

  async function stop(id, ask) {
    const s = sessions.get(id)
    s.open = false
    const tokens = { input: 0, output: 0, cache_read: 0, cache_write: 0 }
    for (const t of Object.values(s.tokens)) {
      tokens.input += t.input || 0
      tokens.output += (t.output || 0) + (t.reasoning || 0)
      tokens.cache_read += t.cache?.read || 0
      tokens.cache_write += t.cache?.write || 0
    }
    const out = hook("stop", { session_id: id, cwd: directory, model: s.model || undefined,
      tokens, stop_hook_active: Boolean(s.asking) || !ask })
    if (ask && out?.decision === "block" && out.reason && !s.asking) {
      // OpenCode has no blocking stop: the question goes back to the agent as a message, once.
      s.asking = true
      s.askedText = out.reason
      try {
        await client.session.prompt({ path: { id }, body: { parts: [{ type: "text", text: out.reason }] } })
      } catch {}
    }
  }
}
