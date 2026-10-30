// Athos's trail in OpenCode's own sidebar: which of the person's ways of working the task follows, in a sentence,
// then its steps ticked as the agent reports them (✓ done, ▶ now, ○ ahead), and whether a connector guards the data.
// The same data as Claude Desktop's panel and `athos watch --trail`, read from `athos status --json`.
//
// OpenCode loads plugins without Solid's JSX transform, so this file is compiled once to athos-sidebar.js
// (`node opencode/build-sidebar.mjs`) and `athos opencode install` installs the compiled file.
import { createSignal } from "solid-js"
import { execFile } from "node:child_process"

const ATHOS = process.env.ATHOS_BIN || "__ATHOS__"
const POLL_MS = 1500

type Step = { id: string; label: string; state: "done" | "now" | "ahead" }
type Piece = { title: string; steps: Step[] }
type Status = {
  lang?: string
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

export const tui = async (api: any) => {
  const cwd = process.cwd()
  const [status, setStatus] = createSignal<Status>(await read(cwd))
  const timer = setInterval(async () => setStatus(await read(cwd)), POLL_MS)
  api.lifecycle.onDispose(() => clearInterval(timer))

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
