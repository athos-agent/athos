/** What `athos status --json` reports: the store, this session's pieces and its last task. */
export type Status = {
  pieces: number
  enabled: number
  loading: string
  loaded: string[]
  to_mark: number
  last: {
    task_id: string
    result: 'unevaluated' | 'ok' | 'corrected' | 'failed'
    pieces: string[]
    saved: string[]
    improved: string[]
  } | null
}

declare module 'claude-code' {
  interface PluginState {
    athos: { snap: Status | null; dismissed: string | null }
  }
}
