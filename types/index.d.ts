/** What `athos status --json` reports: the store, this session's pieces and its last task. */
export type Status = {
  pieces: number
  /** The language the person chose with `athos start`: what they read follows it. */
  lang?: 'en' | 'es'
  enabled: number
  loading: string
  loaded: string[]
  to_mark: number
  /** The piece this session saved or improved last, and the agents where it is ready. */
  /** `recheck`: an improved piece the person corrected before, in their words ("2 past corrections to re-check"). */
  last_saved: { id: string; title: string; version: number; platforms: string[]; tests?: number; recheck?: string } | null
  /** The know-how the current task follows; `tests`: its past corrections `athos test` can re-check. */
  following: { id: string; title: string; version: number; steps: number; wiki: boolean; step_names?: string[]; platforms: string[]; tests?: number }[]
  /** Pieces a cheaper model matched the person's approved answers on (`athos shadow`); `told` once said. */
  handoff?: { piece: string; title: string; model: string; label: string; platform: string; matched: number; of: number; told: boolean }[]
  /** Whether background shadowing is on (`athos shadow on`). */
  shadow?: boolean
  bars: {
    piece: string
    title: string
    baseline_request_chars: number | null
    agents: Bar[]
  } | null
  /** The last task did enough work to be worth keeping: the band offers [Save] (interactive Claude Code). */
  offer: { task_id: string; reason: 'work' | 'checklist' } | null
  /** The pieces this task loaded, with the request's words that loaded each one. */
  loads?: { id: string; title: string; why: string[]; record?: { uses: number; ok: number; marked: number; agents: string[] }; tests?: number }[]
  /** The current task's trail: the know-how it walks, step by step, and what happened beside it. */
  trail?: Trail
  /** "Good morning, Ana": how the band greets the person when a session starts. */
  greeting?: string
  /** What [Save] submits: the save, in the person's language. */
  save_prompt?: string
  last: {
    task_id: string
    result: 'unevaluated' | 'ok' | 'corrected' | 'failed'
    pieces: string[]
    saved: string[]
    improved: string[]
  } | null
}

/** What the trail pane draws (`athos status --json` → `trail`). */
export type Trail = {
  task_id: string | null
  pieces: {
    id: string
    title: string
    version: number
    /** Loaded for the request, or opened by the agent on its own. */
    how: 'loaded' | 'read'
    why: string[]
    /** What it is for (the piece's "when"), how it has done, and the pages it leads to. */
    when?: string
    record?: { uses: number; ok: number; marked: number; agents: string[] }
    see?: { id: string; title: string }[]
    /** Each step as a person reads it: `label` (its moment, or the first sentence of what to do), `do`, `because`. */
    steps: { id: string; label?: string; do: string; because?: string; state: 'done' | 'now' | 'ahead'; piece?: string; depth?: number; if?: string }[]
  }[]
  /** Subagents and skills the task used, in order. */
  beside: ({ kind: 'agent'; name: string; why: string } | { kind: 'skill'; name: string })[]
  /** Connectors the loaded pieces ask for ([[connector:<name>]]), checked when the request came in. */
  connectors?: { name: string; what: string; active: boolean; set_up: boolean; start: string }[]
  /** Steps the task needed that the know-how doesn't have yet. */
  new: string[]
  busy: boolean
}

/** One agent's row: how it applies the piece this project used last. */
export type Bar = {
  platform: string
  label: string
  uses: number
  evaluated: number
  ok: number
  success_rate: number | null
  mean_request_chars: number | null
  prompt_saved: number | null
}

declare module 'claude-code' {
  interface PluginState {
    athos: {
      snap: Status | null; dismissed: string | null; offered: string | null; misfired: string | null
      /** The session has had its first request: the greeting is gone. */
      greeted: boolean
      /** The task whose trail the pane was opened for (once per task, unasked). */
      paneFor: string | null
    }
  }
}
