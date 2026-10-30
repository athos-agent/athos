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
  last_saved: { id: string; title: string; version: number; platforms: string[] } | null
  /** The know-how the current task follows. */
  following: { id: string; title: string; version: number; steps: number; wiki: boolean; step_names?: string[]; platforms: string[] }[]
  bars: {
    piece: string
    title: string
    baseline_request_chars: number | null
    agents: Bar[]
  } | null
  /** The last task did enough work to be worth keeping: the band offers [Save] (interactive Claude Code). */
  offer: { task_id: string; reason: 'work' | 'checklist' } | null
  /** The pieces this task loaded, with the request's words that loaded each one. */
  loads?: { id: string; title: string; why: string[]; record?: { uses: number; ok: number; marked: number; agents: string[] } }[]
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
    steps: { id: string; do: string; state: 'done' | 'now' | 'ahead' }[]
  }[]
  /** Subagents and skills the task used, in order. */
  beside: ({ kind: 'agent'; name: string; why: string } | { kind: 'skill'; name: string })[]
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
