// Athos in the terminal. The status line counts the know-how ("athos · N pieces · K loaded here · M to mark"); the
// band above the prompt appears when the last task ended without a verdict, with one-key marking, and says when that
// task saved or improved a piece. Both read `athos status --json` and stay silent where there is nothing to say.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Bar, Status } from '../types'

const snap = atom({ plugin: 'athos', key: 'snap' } as const, null)
const dismissed = atom({ plugin: 'athos', key: 'dismissed' } as const, null)

export function statusText(s: Status | null): string | undefined {
  if (!s) return undefined
  const parts = [`athos · ${s.pieces} piece${s.pieces === 1 ? '' : 's'}`, `${s.loaded.length} loaded here`]
  if (s.to_mark) parts.push(`${s.to_mark} to mark`)
  return parts.join(' · ')
}

export function savedText(s: Status | null): string {
  const last = s?.last
  if (!last) return ''
  const out: string[] = []
  if (last.saved.length) out.push(`saved ${last.saved.join(', ')}`)
  if (last.improved.length) out.push(`improved ${last.improved.join(', ')}`)
  return out.join(' · ')
}

const BAR_WIDTH = 20
const BAR_COLORS: Record<string, string> = { 'claude-code': '#d38b5d', codex: '#6fa8dc', 'muse-code': '#9b8cf2' }

const k = (n: number) =>
  n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${Math.round(n)}`

/** A bar filled by the success rate, and the words beside it; the same as `athos watch` prints. */
export function barText(b: Bar): { filled: string; empty: string; words: string } {
  const n = Math.round((b.success_rate ?? 0) * BAR_WIDTH)
  const words: string[] = []
  if (!b.uses) words.push('not used yet')
  else {
    words.push(b.evaluated ? `${b.ok}/${b.evaluated} good` : 'not marked yet')
    if (b.mean_tokens !== null) words.push(`${k(b.mean_tokens)} tokens`)
    if (b.tokens_saved !== null)
      words.push(b.tokens_saved >= 0 ? `${Math.round(b.tokens_saved * 100)}% fewer tokens`
        : `${Math.round(-b.tokens_saved * 100)}% more tokens`)
  }
  return { filled: '█'.repeat(n), empty: '░'.repeat(BAR_WIDTH - n), words: words.join(' · ') }
}

async function athos($: EngineInterface, args: string[]): Promise<string> {
  const r = await $.process.run(['python3', `${$.plugin.root}/bin/athos`, ...args], {
    cwd: await $.session.root(),
    timeoutMs: 15_000,
  })
  if (r.exitCode !== 0) throw new Error((r.stderr || r.stdout).trim().slice(0, 200))
  return r.stdout.trim()
}

async function refresh($: EngineInterface): Promise<void> {
  try {
    const s = JSON.parse((await athos($, ['status', '--json'])).split('\n').pop() || 'null') as Status | null
    await update($, snap, () => s)
    $.ui.status(statusText(s))
  } catch {
    $.ui.status(undefined)
  }
}

async function mark($: EngineInterface, key: 'g' | 'c' | 'f'): Promise<void> {
  try {
    $.ui.toast(`athos: ${await athos($, ['mark', key])}`)
  } catch (err) {
    $.ui.toast(`athos: ${String(err).slice(0, 120)}`)
  }
  await refresh($)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    await refresh($)
    return started
  })

  on('prompt.submit', async ($, e, next) => {
    const done = await next(e)
    void refresh($)
    return done
  }).catch(($, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    await refresh($)
    return done
  }).catch(($, e, next) => next(e))

  // Under the prompt: the engine's own line, then one bar per agent for the piece this project used last.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    const bars = (await read($, snap))?.bars
    if (e.surface !== 'terminal' || !bars?.agents.length) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const width = Math.max(...bars.agents.map(a => a.label.length))
    return (
      <Box flexDirection="column">
        <Text dimColor>{e.props.hint}</Text>
        <Text dimColor>{`  athos · ${bars.title}`}</Text>
        {bars.agents.map(a => {
          const t = barText(a)
          return (
            <Text key={a.platform}>
              <Text>{`  ${a.label.padEnd(width)} `}</Text>
              <Text color={BAR_COLORS[a.platform] ?? 'white'}>{t.filled}</Text>
              <Text dimColor>{t.empty}</Text>
              <Text>{`  ${t.words}`}</Text>
            </Text>
          )
        })}
      </Box>
    )
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, snap)
    const last = s?.last
    if (e.props.hasSurvey || !last || last.task_id === (await read($, dismissed))) return next(e)
    const unmarked = last.result === 'unevaluated'
    const saved = savedText(s)
    if (!unmarked && !saved) return next(e)

    const { Box, Button, Text } = $.ui.resolve(e)
    const hide = () => update($, dismissed, () => last.task_id)
    return (
      <Box>
        <Text color="cyan">athos </Text>
        {saved ? <Text>{saved}. </Text> : null}
        {unmarked ? <Text dimColor>How did this task go? </Text> : null}
        {unmarked ? <Button key="g" label="Good" onPress={() => mark($, 'g')} /> : null}
        {unmarked ? <Button key="c" label="Corrected" onPress={() => mark($, 'c')} /> : null}
        {unmarked ? <Button key="f" label="Failed" onPress={() => mark($, 'f')} /> : null}
        <Button key="hide" label={unmarked ? 'Skip' : 'OK'} onPress={hide} />
      </Box>
    )
  })
}
