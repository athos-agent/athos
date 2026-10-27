/** What `athos status --json` reports: the store, this session's pieces and its last task. */
export type Status = {
  pieces: number
  enabled: number
  loading: string
  loaded: string[]
  to_mark: number
  bars: {
    piece: string
    title: string
    baseline_s: number | null
    agents: Bar[]
  } | null
  last: {
    task_id: string
    result: 'unevaluated' | 'ok' | 'corrected' | 'failed'
    pieces: string[]
    saved: string[]
    improved: string[]
  } | null
}

/** One agent's row: how it applies the piece this project used last. */
export type Bar = {
  platform: string
  label: string
  uses: number
  evaluated: number
  ok: number
  success_rate: number | null
  mean_duration_s: number | null
  time_saved: number | null
}

declare module 'claude-code' {
  interface PluginState {
    athos: { snap: Status | null; dismissed: string | null }
  }
}
