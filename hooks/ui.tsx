// Athos in the terminal. The status line counts the know-how ("N ways of working · K in use · M to mark"; the engine
// prefixes the plugin's name); the band above the prompt says when the last task saved or improved a piece and, while
// it has no verdict, offers one-key marking. Both read `athos status --json` and stay silent with nothing to say.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Bar, Status } from '../types'

const snap = atom({ plugin: 'athos', key: 'snap' } as const, null)
const dismissed = atom({ plugin: 'athos', key: 'dismissed' } as const, null)
const offered = atom({ plugin: 'athos', key: 'offered' } as const, null)
const misfired = atom({ plugin: 'athos', key: 'misfired' } as const, null)

// What the person reads, in the language they chose with `athos start` (English by default), in plain words.
const WORDS = {
  en: {
    ways: (n: number) => `${n} way${n === 1 ? '' : 's'} of working`, inUse: (n: number) => `${n} in use`,
    toMark: (n: number) => `${n} to mark`, following: 'following', steps: (n: number) => `${n} step${n === 1 ? '' : 's'}`,
    numbered: 'numbered steps', more: (n: number) => `+${n} more`, ready: 'ready in', saved: 'saved',
    improved: 'improved', good: 'good', notUsed: 'not used yet', notMarked: 'not marked yet',
    shorter: (p: number) => `${p}% shorter prompt`, longer: (p: number) => `${p}% longer prompt`,
    ask: 'How did this task go? ', ok: 'Good', corrected: 'Corrected', failed: 'Failed', skip: 'Skip',
    offerWork: 'This task can become a way of working. Save it? ',
    offerChecklist: 'This task followed a checklist. Save it as a way of working? ', save: 'Save', notNow: 'Not now',
    used: 'used', matched: 'matched', didntApply: "Didn't apply",
    record: (ok: number, marked: number, agents: string[]) =>
      `${ok}/${marked} good` + (agents.length ? ` in ${agents.join(', ')}` : ''),
    firstTime: 'first time',
  },
  es: {
    ways: (n: number) => `${n} forma${n === 1 ? '' : 's'} de trabajar`, inUse: (n: number) => `${n} en uso`,
    toMark: (n: number) => `${n} por marcar`, following: 'siguiendo', steps: (n: number) => `${n} paso${n === 1 ? '' : 's'}`,
    numbered: 'pasos numerados', more: (n: number) => `+${n} más`, ready: 'lista en', saved: 'guardé',
    improved: 'mejoré', good: 'bien', notUsed: 'sin usar todavía', notMarked: 'sin marcar todavía',
    shorter: (p: number) => `pedido ${p}% más corto`, longer: (p: number) => `pedido ${p}% más largo`,
    ask: '¿Cómo salió esta tarea? ', ok: 'Salió bien', corrected: 'Lo corregí', failed: 'Falló', skip: 'Omitir',
    offerWork: 'Esta tarea puede quedar como forma de trabajar. ¿La guardo? ',
    offerChecklist: 'Esta tarea siguió un checklist. ¿Lo guardo como forma de trabajar? ', save: 'Guardar',
    notNow: 'Ahora no', used: 'usó', matched: 'coincidió', didntApply: 'No aplicaba',
    record: (ok: number, marked: number, agents: string[]) =>
      `${ok}/${marked} bien` + (agents.length ? ` en ${agents.join(', ')}` : ''),
    firstTime: 'primera vez',
  },
}
export function words(s: Status | null) {
  return WORDS[s?.lang === 'es' ? 'es' : 'en']
}

/** How a piece has done so far, in a few words: "4/4 good in Claude Code, OpenCode", or "first time". */
export function recordText(r: { uses: number; ok: number; marked: number; agents: string[] } | undefined,
                           w: ReturnType<typeof words>): string {
  if (!r || r.uses <= 1 || !r.marked) return w.firstTime
  return w.record(r.ok, r.marked, r.agents)
}

/** The band's first row, kept to one line so the terminal never wraps it (a wrapped row lost its space after
 * "athos"): the piece, its record, and at most three of the words that loaded it. */
export function whyText(l: NonNullable<Status['loads']>[number], w: ReturnType<typeof words>): string {
  const shown = l.why.slice(0, 3).join(', ') + (l.why.length > 3 ? '…' : '')
  return `${w.used} «${l.title}» · ${recordText(l.record, w)} · ${w.matched}: ${shown}`
}

export function statusText(s: Status | null): string | undefined {
  if (!s) return undefined
  const w = words(s)
  const parts = [w.ways(s.pieces), w.inUse(s.loaded.length)]
  if (s.to_mark) parts.push(w.toMark(s.to_mark))
  return parts.join(' · ')
}

/** While a task runs: the know-how it follows, how big it is, and where else it is ready. */
export function followingText(s: Status | null): string | undefined {
  const f = s?.following?.[0]
  if (!f) return undefined
  const w = words(s)
  const size = f.wiki ? w.steps(f.steps) : w.numbered
  const more = (s?.following.length ?? 1) > 1 ? ` (${w.more(s!.following.length - 1)})` : ''
  return `athos · ${w.following} «${f.title}» v${f.version} · ${size}${more} · ${w.ready} ${f.platforms.join(' · ')}`
}

/** The steps of the piece being followed, in order: what the person taught, as a reminder while the task runs. */
export function stepsText(s: Status | null): string | undefined {
  const names = s?.following?.[0]?.step_names
  if (!names?.length) return undefined
  const more = (s!.following[0].steps ?? names.length) > names.length ? ' → …' : ''
  return names.map(n => `#${n}`).join(' → ') + more
}

/** The line shown above the prompt after a save: what, which version, and where it is ready. */
export function announceText(s: Status | null): string | undefined {
  const l = s?.last_saved
  if (!l) return undefined
  const w = words(s)
  const what = l.version > 1 ? `${w.improved} «${l.title}» → v${l.version}` : `${w.saved} «${l.title}»`
  return `${what} · ${w.ready} ${l.platforms.join(' · ')}`
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

/** A bar filled by the success rate, and the words beside it; the same as `athos watch` prints. */
export function barText(b: Bar, s: Status | null = null): { filled: string; empty: string; words: string } {
  const n = Math.round((b.success_rate ?? 0) * BAR_WIDTH)
  const w = words(s)
  const out: string[] = []
  if (!b.uses) out.push(w.notUsed)
  else {
    out.push(b.evaluated ? `${b.ok}/${b.evaluated} ${w.good}` : w.notMarked)
    if (b.prompt_saved !== null)
      out.push(b.prompt_saved >= 0 ? w.shorter(Math.round(b.prompt_saved * 100))
        : w.longer(Math.round(-b.prompt_saved * 100)))
  }
  return { filled: '█'.repeat(n), empty: '░'.repeat(BAR_WIDTH - n), words: out.join(' · ') }
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

  // After each answer: the task ended and may have saved a piece, which the band above the prompt announces.
  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    await refresh($)
    return done
  }).catch(($, e, next) => next(e))

  // Under the prompt: the engine's own line, then one bar per agent for the piece this project used last.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    const s = await read($, snap)
    const bars = s?.bars
    const card = e.props.isWorking ? followingText(s) : undefined
    const steps = e.props.isWorking ? stepsText(s) : undefined
    if (e.surface !== 'terminal' && e.surface !== 'desktop') return next(e)
    if (!card && !bars?.agents.length) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    if (card) {
      // While the task runs: one line saying which of the person's know-how it follows.
      return (
        <Box flexDirection="column">
          <Text dimColor>{e.props.hint}</Text>
          <Text color="cyan">{`  ${card}`}</Text>
          {steps ? <Text dimColor>{`    ${steps}`}</Text> : null}
        </Box>
      )
    }
    if (!bars?.agents.length) return next(e)
    const width = Math.max(...bars.agents.map(a => a.label.length))
    return (
      <Box flexDirection="column">
        <Text dimColor>{e.props.hint}</Text>
        <Text dimColor>{`  athos · ${bars.title}`}</Text>
        {bars.agents.map(a => {
          const t = barText(a, s)
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
    // The save is announced here and not under the answer: text a plugin adds there is drawn with an engine prefix.
    const savedNow = s?.last_saved && [...last.saved, ...last.improved].includes(s.last_saved.id)
    const saved = savedNow ? announceText(s) : undefined
    // Worth keeping: the person decides with one key, instead of the model being asked after every task.
    const offer = !saved && s?.offer?.task_id === last.task_id && (await read($, offered)) !== last.task_id
      ? s!.offer : null
    // Which of the person's know-how this task loaded and why, with one key to say it didn't fit.
    const load = s?.loads?.[0]
    const why = load && (await read($, misfired)) !== `${last.task_id}:${load.id}` ? load : null
    if (!unmarked && !saved && !offer && !why) return next(e)

    const { Box, Button, Text } = $.ui.resolve(e)
    const hide = () => update($, dismissed, () => last.task_id)
    const later = () => update($, offered, () => last.task_id)
    const keep = async () => {
      await update($, offered, () => last.task_id)
      // As the person's own words: one short line in the transcript, no "a plugin sent a message" frame.
      await $.prompt.submit({ text: s!.save_prompt || 'Athos · save: keep this task as a way of working', asUser: true })
    }
    const notIt = async () => {
      await update($, misfired, () => `${last.task_id}:${why!.id}`)
      try {
        $.ui.toast(`athos: ${await athos($, ['dismiss', why!.id])}`)
      } catch (err) {
        $.ui.toast(`athos: ${String(err).slice(0, 120)}`)
      }
    }
    const w = words(s)
    return (
      <Box flexDirection="column">
        {why ? (
          <Box>
            <Text color="cyan">athos </Text>
            <Text dimColor>{`${whyText(why, w)} `}</Text>
            <Button key="x" label={w.didntApply} onPress={notIt} />
          </Box>
        ) : null}
        {saved ? <Box><Text color="cyan">athos </Text><Text color="green">{saved}</Text></Box> : null}
        {offer ? (
          <Box>
            <Text color="cyan">athos </Text>
            <Text>{offer.reason === 'checklist' ? w.offerChecklist : w.offerWork}</Text>
            <Button key="s" label={w.save} onPress={keep} />
            <Button key="n" label={w.notNow} onPress={later} />
          </Box>
        ) : null}
        {unmarked ? (
          <Box>
            <Text color="cyan">athos </Text>
            <Text dimColor>{w.ask}</Text>
            <Button key="g" label={w.ok} onPress={() => mark($, 'g')} />
            <Button key="c" label={w.corrected} onPress={() => mark($, 'c')} />
            <Button key="f" label={w.failed} onPress={() => mark($, 'f')} />
            <Button key="hide" label={w.skip} onPress={hide} />
          </Box>
        ) : null}
      </Box>
    )
  })
}
