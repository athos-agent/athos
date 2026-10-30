// Athos's trail in OpenCode's own sidebar: which of the person's ways of working the task follows, in a sentence,
// then its steps ticked as the agent reports them (✓ done, ▶ now, ○ ahead), and whether a connector guards the data.
// The same data as Claude Desktop's panel and `athos watch --trail`, read from `athos status --json`.
// Its two buttons are commands in OpenCode's palette (ctrl+p): "Athos: change this step" and "Athos: save as a way of
// working". Each sends the same message as Desktop's panel to the session, so nobody has to type a command.
//
// OpenCode loads plugins without Solid's JSX transform, so this file is compiled once to athos-sidebar.js
// (`node opencode/build-sidebar.mjs`) and `athos opencode install` installs the compiled file.
import { createSignal } from "solid-js"
import { execFile } from "node:child_process"

const ATHOS = process.env.ATHOS_BIN || "__ATHOS__"
const POLL_MS = 1500

type Step = { id: string; label: string; state: "done" | "now" | "ahead" }
type Piece = { id: string; title: string; steps: Step[] }
type Status = {
  lang?: string
  save_prompt?: string
  trail?: { pieces: Piece[]; new: string[]; connectors?: { name: string; active: boolean }[] }
}

function read(cwd: string): Promise<Status> {
  return new Promise((resolve) => {
    execFile(ATHOS, ["status", "--json"], { cwd, timeout: 10000 }, (err, out) => {
      if (err) return resolve({})
      try {
        resolve(JSON.parse(String(out).trim().split("\n").pop() || "{}"))
      } catch {
        resolve({})
      }
    })
  })
}

const MARK = { done: "✓", now: "▶", ahead: "○" }

// The step a change is about: the one in progress, else the last one done, else the first.
function current(piece: Piece): Step | undefined {
  const done = piece.steps.filter((x) => x.state === "done")
  return piece.steps.find((x) => x.state === "now") || done[done.length - 1] || piece.steps[0]
}

export const tui = async (api: any) => {
  const cwd = process.cwd()
  const [status, setStatus] = createSignal<Status>(await read(cwd))
  const timer = setInterval(async () => setStatus(await read(cwd)), POLL_MS)
  api.lifecycle.onDispose(() => clearInterval(timer))

  // The message goes to the session as the person's own, through the prompt, as when they type it.
  const say = async (text: string) => {
    await api.client.tui.appendPrompt({ text })
    await api.client.tui.submitPrompt()
  }
  const change = () => {
    const s = status()
    const es = s.lang === "es"
    const piece = s.trail?.pieces?.[0]
    const step = piece && current(piece)
    if (!piece || !step) return
    api.ui.dialog.replace(() => (
      <api.ui.DialogPrompt
        title={es ? "¿Cómo tiene que cambiar este paso?" : "How should this step change?"}
        description={() => <text>{step.label}</text>}
        placeholder={es ? "por ejemplo: además, comparar con el índice ICL" : "e.g. also compare against the CPI"}
        onConfirm={(value: string) => {
          api.ui.dialog.clear()
          if (value.trim()) say(`${es ? "Athos · ajustar" : "Athos · adjust"} ${piece.id}#${step.id}: ${value.trim()}`)
        }}
        onCancel={() => api.ui.dialog.clear()}
      />
    ))
  }
  const save = () => {
    const s = status()
    say(s.save_prompt || "Athos · save: keep this task as a way of working")
  }
  // Legacy in OpenCode 1.19, still how a v1 plugin adds palette entries.
  if (api.command?.register) {
    const off = api.command.register(() => {
      const s = status()
      const es = s.lang === "es"
      const piece = s.trail?.pieces?.[0]
      return [
        { title: es ? "Athos: cambiar este paso" : "Athos: change this step", value: "athos.change",
          category: "Athos", enabled: !!piece, onSelect: change },
        { title: es ? "Athos: guardar como forma de trabajar" : "Athos: save as a way of working", value: "athos.save",
          category: "Athos", onSelect: save },
      ]
    })
    api.lifecycle.onDispose(off)
  }

  api.slots.register({
    slots: {
      sidebar_content: (ctx: any) => {
        const t = ctx.theme.current
        const s = status()
        const es = s.lang === "es"
        const piece = s.trail?.pieces?.[0]
        if (!piece) return null
        const steps = piece.steps
        const i = steps.findIndex((x) => x.state === "now")
        const done = steps.filter((x) => x.state === "done").length
        const where = i >= 0
          ? (es ? `Paso ${i + 1} de ${steps.length}` : `Step ${i + 1} of ${steps.length}`)
          : done === steps.length
            ? (es ? `Apliqué los ${done} pasos` : `All ${done} steps applied`)
            : (es ? `${steps.length} pasos` : `${steps.length} steps`)
        const guard = (s.trail?.connectors || []).map((c) =>
          c.active ? (es ? `🔒 datos por ${c.name}` : `🔒 data through ${c.name}`)
                   : (es ? `⚠ ${c.name} no está activo` : `⚠ ${c.name} is not running`))
        return (
          <box flexDirection="column" paddingTop={1}>
            <text fg={t.accent}>Athos</text>
            <text fg={t.textMuted}>{(es ? "Sigo «" : "Following «") + piece.title + "»"}</text>
            <text fg={t.textMuted}>{where}</text>
            {guard.map((g) => <text fg={t.textMuted}>{g}</text>)}
            {steps.map((x) => (
              <text fg={x.state === "now" ? t.accent : x.state === "done" ? t.success : t.textMuted}>
                {MARK[x.state] + " " + (x.label.length > 34 ? x.label.slice(0, 33) + "…" : x.label)}
              </text>
            ))}
            {(s.trail?.new || []).map((n) => <text fg={t.warning}>{"+ " + n}</text>)}
          </box>
        )
      },
    },
  })
}

export default { id: "athos-sidebar", tui }
