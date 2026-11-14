import { atom, read, update } from 'claude-code'
import type { Color, EngineInterface, Register } from 'claude-code'

import type { Bubble, ChatLine, Turn } from '../types'
import { SPRITES, type Band } from './sprites'

const percent = atom({ plugin: 'clawd-meter', key: 'percent' } as const, 0)
const history = atom({ plugin: 'clawd-meter', key: 'history' } as const, [])
const turn = atom({ plugin: 'clawd-meter', key: 'turn' } as const, {
  working: false, startedAt: 0, endedAt: 0, tools: 0, lastTool: '',
})
const bubble = atom({ plugin: 'clawd-meter', key: 'bubble' } as const, {
  text: 'hi! fresh context, plenty of room.', source: 'note', turn: 0,
})
const tick = atom({ plugin: 'clawd-meter', key: 'tick' } as const, 0)
const seen = atom({ plugin: 'clawd-meter', key: 'seen' } as const, [])
const chat = atom({ plugin: 'clawd-meter', key: 'chat' } as const, [])
const chatBusy = atom({ plugin: 'clawd-meter', key: 'chatBusy' } as const, false)

// ── scale (same as the compact statusline) ────────────────────────────────
const SCALE: Array<[number, Band, string, Color]> = [
  [40, 'sharp', '(^‿^)', 'success'],
  [60, 'coasting', '(•‿•)', 'suggestion'],
  [75, 'foggy', '(•_•)', 'warning'],
  [90, 'cooked', '(x_x)', 'error'],
  [101, 'dumb', '(°﹃°)', 'claude'],
]
const THRESHOLDS: Array<[number, Band]> = [[40, 'coasting'], [60, 'foggy'], [75, 'cooked'], [90, 'dumb']]

function bandOf(p: number): { band: Band; face: string; color: Color } {
  for (const [limit, band, face, color] of SCALE) {
    if (p < limit) return { band, face, color }
  }
  return { band: 'dumb', face: '(°﹃°)', color: 'claude' }
}

// ── what the mascot says ──────────────────────────────────────────────────
const QUIPS: Record<Band, string[]> = {
  sharp: ['context is crisp. let\'s build.', 'fresh brain, who dis', 'plenty of room in here', 'sharp as a tack (^‿^)'],
  coasting: ['cruising.', 'still got room', 'humming along', 'all systems nominal'],
  foggy: ['getting a little foggy in here...', 'I remember most of it. probably.', 'a /compact soon wouldn\'t hurt'],
  cooked: ['I\'m cooked. /compact?', 'my context runneth over', 'save a memory before I forget'],
  dumb: ['duhh... /compact pls', 'what were we doing?', 'brain full. (°﹃°)'],
}
const NUDGES: Partial<Record<Band, string>> = {
  foggy: 'getting foggy (60%). good time to wrap up a thread.',
  cooked: 'cooked (75%). /compact soon, or save what matters to memory.',
  dumb: 'past 90%. /compact or /clear before I start forgetting.',
}
// Slash commands whose printed output the bubble repeats: none by default (/btw,
// /insights and "You should know" don't print command output). CLAWD_METER_CAPTURE
// names some (comma-separated, no slash); CLAWD_METER_DEBUG=1 repeats every
// command's output with its name, to find out what a command is called.
const KEEP_TURNS = 3 // a captured or nudge message outlives this many turns before quips resume

// /ask and the heads-up watcher both fork the session's own transcript (served from
// the prompt cache), as /btw does, at low effort, and say the answer in the bubble.
const ASK_PROMPT = (q: string) =>
  'Side question from the user, asked with /ask while you keep working. Answer it directly from ' +
  'what is in this conversation, in at most two short sentences (under 200 characters), plain text, ' +
  "no markdown, no preamble. If the conversation doesn't say, answer that in one line.\n\nQuestion: " + q
const HEADSUP_PROMPT =
  "Side check, not a request to act. You're watching this session on the user's behalf. Based on the " +
  'most recent turn, is there anything the user should know right now but could easily miss: a risk, ' +
  'a failure that went by quietly, an assumption made without asking them, something left unfinished, ' +
  'or an action that might surprise them? If nothing is clearly worth their attention, reply with ' +
  'exactly NONE. Otherwise reply with one heads-up of at most 110 characters, plain text, no markdown, ' +
  'no preamble.'
const EXPLAIN_PROMPT = (headsUp: string) =>
  'The user pressed "explain" on this heads-up you gave them: "' + headsUp + '". Explain it for someone ' +
  'without context: what it is about, why it matters, and what they could do. At most 300 characters, ' +
  'plain text, no markdown, no preamble.'
const CHAT_PROMPT = (thread: ChatLine[]) =>
  'Side conversation with the user in a small panel next to the session. It is separate from the main ' +
  "task: don't act or change anything, just answer from what is in this conversation. The side " +
  'conversation so far:\n\n' + thread.map(l => `${l.who}: ${l.text}`).join('\n') +
  "\n\nReply to the user's last message as clawd. At most 600 characters, plain text, no markdown, " +
  'no preamble.'
const PANE = 'clawd-chat'
// Buttons draw with their chrome, `[ dismiss ]`: 11 columns for the longest label.
const BUTTON_COL = 11
const HEADSUP_MIN_GAP_MS = 180_000 // at most one heads-up check every 3 minutes
const HEADSUP_MIN_TOOLS = 3 // ...and only after a turn with real work in it
const HEADSUP_MIN_TURN_MS = 60_000

let mode: 'image' | 'raster' = 'raster'
let capture = new Set<string>()
let debug = false
let headsupOn = true
let lastHeadsupAt = 0
let lastHeadsup = ''
let stopTicker: (() => void) | undefined

function hash(s: string): string {
  let acc = 5381
  for (let i = 0; i < s.length; i++) acc = ((acc << 5) + acc + s.charCodeAt(i)) | 0
  return (acc >>> 0).toString(36)
}

function plain(md: string): string {
  return md.replace(/```[\s\S]*?```/g, ' ').replace(/[*_`#>]+/g, '').replace(/\s+/g, ' ').trim()
}

function fmt(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  return s >= 60 ? `${Math.floor(s / 60)}m${String(s % 60).padStart(2, '0')}s` : `${s}s`
}

/** Wrap to at most `lines` lines of `width`, ending in … when cut. */
function wrap(text: string, width: number, lines: number): string[] {
  const out: string[] = []
  let cur = ''
  for (const word of text.split(' ')) {
    const next = cur ? `${cur} ${word}` : word
    if (next.length <= width) { cur = next; continue }
    if (cur) out.push(cur)
    cur = word.length > width ? word.slice(0, width) : word
    if (out.length === lines) break
  }
  if (out.length < lines && cur) out.push(cur)
  const cut = out.join(' ').length < text.length
  const kept = out.slice(0, lines)
  const last = kept[kept.length - 1]
  if (cut && last !== undefined) {
    kept[kept.length - 1] = (last.length >= width ? last.slice(0, width - 1) : last) + '…'
  }
  return kept
}

/** Open the side-chat pane seeded with `seed`; optionally ask `firstQuestion` right away. */
async function openChat($: EngineInterface, seed: string, viewportColumns: number, firstQuestion?: string) {
  await update($, chat, list => (list[0]?.text === seed ? list : [{ who: 'clawd' as const, text: seed }]))
  await $.ui.open({
    id: PANE, title: 'clawd', focus: true, closeOnEscape: true,
    columns: Math.max(36, Math.round(viewportColumns / 4)), rows: 12,
  })
  if (firstQuestion) await askChat($, firstQuestion)
}

/** Add the person's message to the side chat and the fork's reply after it. */
async function askChat($: EngineInterface, question: string) {
  const q = question.trim()
  if (!q || (await read($, chatBusy))) return
  const thread = await update($, chat, list => [...list, { who: 'you' as const, text: q }].slice(-40))
  await update($, chatBusy, () => true)
  try {
    const reply = await $.model.fork({ prompt: CHAT_PROMPT(thread), effort: 'low' })
    const text = reply.isAnswered ? plain(reply.text) : `(no reply: ${reply.reason})`
    await update($, chat, list => [...list, { who: 'clawd' as const, text }].slice(-40))
  } finally {
    await update($, chatBusy, () => false)
  }
}

const SPARK = '▁▂▃▄▅▆▇█'

function trendText(hist: number[], p: number): { eta: string; rate: string } {
  const pts = [...hist.slice(-6)]
  if (pts[pts.length - 1] !== p) pts.push(p)
  const first = pts[0] ?? p
  const slope = pts.length >= 2 ? (p - first) / (pts.length - 1) : 0
  const rate = pts.length >= 2 ? `${slope >= 0 ? '+' : ''}${slope.toFixed(1)}%/turn` : 'measuring...'
  if (p >= 90) return { eta: 'past the edge', rate }
  if (slope < 0.3) return { eta: 'holding steady', rate }
  const next = THRESHOLDS.find(([t]) => t > p)
  if (!next) return { eta: 'holding steady', rate }
  const turns = Math.max(1, Math.ceil((next[0] - p) / slope))
  return { eta: `~${turns} turn${turns === 1 ? '' : 's'} to ${next[1]}`, rate }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const forced = await $.env.get('CLAWD_METER_MODE')
    const term = (await $.env.get('TERM')) ?? ''
    mode = forced === 'image' || forced === 'raster' ? forced : /ghostty|kitty/.test(term) ? 'image' : 'raster'
    const extra = (await $.env.get('CLAWD_METER_CAPTURE')) ?? ''
    capture = new Set(extra.split(',').map(s => s.trim().replace(/^\//, '')).filter(Boolean))
    debug = (await $.env.get('CLAWD_METER_DEBUG')) === '1'
    headsupOn = (await $.env.get('CLAWD_METER_HEADSUP')) !== '0'
    await $.command.register({
      name: 'ask',
      description: 'Ask the mascot a quick side question; the answer lands in its speech bubble',
      argumentHint: '<question>',
      immediate: true,
    })
    const { context } = await $.session.usage()
    await update($, percent, () => context.percent ?? 0)

    return next(e)
  })

  on('session.measure', async ($, e, next) => {
    const result = await next(e)
    const p = e.context.percent
    if (p === undefined) return result
    const before = await read($, percent)
    await update($, percent, () => p)
    if (before - p >= 15) {
      // context dropped a lot: a compaction (or /clear) happened
      await update($, history, () => [p])
      const n = (await read($, history)).length
      await update($, bubble, () => ({ text: `ahh, fresh context. (${before}% → ${p}%)`, source: 'note', turn: n }))
    }

    return result
  })

  // These two sit in the path of the person's prompts and tool calls: bookkeeping
  // here must never throw into them, so each failure is swallowed.
  on('prompt.submit', async ($, e, next) => {
    try {
      const now = await $.clock.now()
      await update($, turn, () => ({ working: true, startedAt: now, endedAt: 0, tools: 0, lastTool: '' }))
      stopTicker?.()
      const timer = $.clock.every(1000, () => { update($, tick, t => t + 1).catch(() => undefined) })
      stopTicker = () => timer.cancel()
    } catch {
      // the band just misses this turn's timer
    }

    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    await update($, turn, t => ({ ...t, tools: t.tools + 1, lastTool: e.tool })).catch(() => undefined)

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    stopTicker?.()
    stopTicker = undefined
    const now = await $.clock.now()
    const t = await update($, turn, t => ({ ...t, working: false, endedAt: now }))
    const p = await read($, percent)
    const prev = (await read($, history)).slice(-1)[0]
    const hist = await update($, history, list => [...list, p].slice(-60))
    const n = hist.length
    const was = prev === undefined ? undefined : bandOf(prev).band
    const { band } = bandOf(p)
    const current = await read($, bubble)
    const stale = current.source === 'quip' || n - current.turn >= KEEP_TURNS
    let said: Bubble | undefined
    if (was !== undefined && was !== band && NUDGES[band] && SCALE.findIndex(s => s[1] === band) > SCALE.findIndex(s => s[1] === was)) {
      said = { text: NUDGES[band] ?? '', source: 'nudge', turn: n }
    } else if (stale && t.endedAt - t.startedAt > 120_000) {
      said = { text: `that one took ${fmt(t.endedAt - t.startedAt)} and ${t.tools} tool calls. phew.`, source: 'note', turn: n }
    } else if (stale) {
      const q = QUIPS[band]
      said = { text: q[n % q.length] ?? 'hm.', source: 'quip', turn: n }
    }
    if (said) {
      const s = said
      await update($, bubble, () => s)
    }

    // Heads-up watcher: in the background, so the turn ends without waiting on it.
    const busy = t.tools >= HEADSUP_MIN_TOOLS || t.endedAt - t.startedAt >= HEADSUP_MIN_TURN_MS
    if (headsupOn && busy && now - lastHeadsupAt >= HEADSUP_MIN_GAP_MS) {
      lastHeadsupAt = now
      void (async () => {
        const reply = await $.model.fork({ prompt: HEADSUP_PROMPT, effort: 'low' })
        if (!reply.isAnswered) return
        const text = plain(reply.text).replace(/^["']|["']$/g, '')
        if (!text || /^NONE\b/i.test(text) || text === lastHeadsup) return
        lastHeadsup = text
        const at = (await read($, history)).length
        await update($, bubble, () => ({ text: `heads-up: ${text}`, source: 'headsup', turn: at }))
      })().catch(() => undefined)
    }

    return next(e)
  })

  on('command.run', { command: 'ask' }, async ($, e) => {
    const question = e.args.trim()
    if (!question) return { text: 'Usage: /ask <question>' }
    const at = (await read($, history)).length
    await update($, bubble, () => ({ text: 'hmm, let me think...', source: 'ask', turn: at }))
    const reply = await $.model.fork({ prompt: ASK_PROMPT(question), effort: 'low' })
    const answer = reply.isAnswered ? plain(reply.text) : `couldn't answer (${reply.reason})`
    await update($, bubble, () => ({ text: answer, source: 'ask', turn: at }))

    return { text: `clawd: ${answer}` }
  })

  // Repeat what chosen slash commands printed (e.g. /btw) in the bubble.
  on('ui.render', { component: 'CommandOutput' }, async ($, e, next) => {
    const { command, text, isErrored } = e.props
    if (!isErrored && text && command !== 'ask' && (debug || capture.has(command))) {
      const id = hash(`${command}\n${text}`)
      const known = await read($, seen)
      if (!known.includes(id)) {
        await update($, seen, list => [...list, id].slice(-80))
        const n = (await read($, history)).length
        const body = plain(text)
        await update($, bubble, () => ({ text: debug ? `/${command}: ${body}` : body, source: 'capture', turn: n }))
      }
    }

    return next(e)
  })

  // The side-chat pane: the full message, a short conversation, an input for follow-ups.
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Input, Text } = $.ui.resolve(e)
    const thread = await read($, chat)
    const busy = await read($, chatBusy)
    const width = Math.max(10, e.props.bodyColumns - 1)
    const lines: Array<{ who: ChatLine['who']; text: string; first: boolean }> = []
    for (const l of thread) {
      wrap(l.text, width - 2, 200).forEach((t, i) => lines.push({ who: l.who, text: t, first: i === 0 }))
    }
    const room = Math.max(3, (e.viewport?.rows ?? 24) - 6)

    return (
      <Box flexDirection="column">
        {lines.slice(-room).map((l, i) => (
          <Box key={`l${i}`}>
            <Text color={l.who === 'clawd' ? 'claude' : 'suggestion'}>{l.first ? (l.who === 'clawd' ? '▌ ' : '› ') : '  '}</Text>
            <Text dimColor={l.who === 'you'}>{l.text}</Text>
          </Box>
        ))}
        {busy ? <Text dimColor>clawd is thinking...</Text> : null}
        <Input key="q" placeholder="ask a follow-up..." submitLabel="ask" autoFocus
          onSubmit={value => { askChat($, value).catch(() => undefined) }} />
        <Box gap={1}>
          <Button key="clear" label="clear" dimColor onPress={() => { update($, chat, list => list.slice(0, 1)).catch(() => undefined) }} />
          <Button key="close" label="close" dimColor onPress={() => { $.ui.close({ id: PANE }).catch(() => undefined) }} />
        </Box>
      </Box>
    )
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.surface !== 'terminal' || e.props.hasSurvey) {
      return next(e)
    }
    const { Box, Button, Image, Raster, Text } = $.ui.resolve(e)
    await read($, tick) // redraw every second while a turn runs
    const p = await read($, percent)
    const { band, face, color } = bandOf(p)
    const hist = await read($, history)
    const t: Turn = await read($, turn)
    const said: Bubble = await read($, bubble)
    const now = await $.clock.now()
    const cols = e.props.bodyColumns

    // Not enough rows for the 4-row layout (e.g. a phone with its keyboard up
    // squeezes the band): one right-aligned line, the bubble cut to fit and the
    // band's face, instead of a cropped sprite behind a "↓ more" scroller.
    if (e.props.maxRows < 4) {
      const room = Math.max(0, cols - face.length - 1)
      const line = room >= 8 ? (wrap(said.text, room, 1)[0] ?? '') : ''
      return (
        <Box width={cols} justifyContent="flex-end">
          {line ? <Text dimColor>{`${line} `}</Text> : null}
          <Text color={color} bold>{face}</Text>
        </Box>
      )
    }

    const sprite = SPRITES[band]

    const picture =
      mode === 'image' ? (
        <Image key="clawd" source={{ png: sprite.png }} columns={12} rows={4} alt={face} />
      ) : (
        <Raster key="clawd" columns={12} rows={4} cells={sprite.cells} />
      )

    // Narrowing drops one block at a time, as the statusline does: activity
    // first, then the trend, then the bubble; the mascot always stays.
    // Mascot 12 + tail 1, trend 24+2, activity 22+2, bubble at least ~20.
    const showActivity = cols >= 84
    const showTrend = cols >= 60
    const showBubble = cols >= 32

    // ── trend ──
    const points = [...hist.slice(-17), p]
    const trend = trendText(hist, p)
    const trendBox = (
      <Box flexDirection="column" width={24} marginRight={2}>
        <Box>
          <Text dimColor>ctx </Text>
          {points.map((v, i) => (
            <Text key={`s${i}`} color={bandOf(v).color}>{SPARK[Math.min(7, Math.floor((v / 100) * 8))]}</Text>
          ))}
        </Box>
        <Text color={color} bold>{`${p}% ${band}`}</Text>
        <Text>{trend.eta}</Text>
        <Text dimColor>{trend.rate}</Text>
      </Box>
    )

    // ── activity ──
    const elapsed = fmt((t.working ? now : t.endedAt) - t.startedAt)
    const activityBox = (
      <Box flexDirection="column" width={22} marginRight={2}>
        {t.working ? <Text color="claude" bold>{`● working ${elapsed}`}</Text> : <Text dimColor>{t.startedAt ? `last turn ${elapsed}` : 'no turns yet'}</Text>}
        <Text>{`${t.tools} tool call${t.tools === 1 ? '' : 's'}`}</Text>
        <Text dimColor>{t.working ? (t.lastTool ? `now: ${t.lastTool}` : 'thinking...') : 'idle'}</Text>
        <Text> </Text>
      </Box>
    )

    // ── bubble ──
    // An outlined speech bubble that stretches across whatever the trend and activity
    // blocks leave, 2 lines of text inside; its buttons stack to its left. Only a
    // message too long for it is cut, and `more` opens it whole in the side pane.
    const bar: Color =
      said.source === 'headsup' || said.source === 'explain' ? 'warning'
      : said.source === 'ask' || said.source === 'capture' ? 'suggestion'
      : 'inactive'
    const setBubble = (fn: (b: Bubble) => Bubble) => { update($, bubble, fn).catch(() => undefined) }
    const quipNow = QUIPS[band][said.turn % QUIPS[band].length] ?? 'hm.'
    const viewportColumns = e.viewport?.columns ?? cols + 5
    const isMessage = said.source !== 'quip' && said.source !== 'nudge'
    const canExplain = said.source === 'headsup'
    const roomBase = cols - 13 - (showTrend ? 26 : 0) - (showActivity ? 24 : 0)
    // Two passes: the buttons column only takes room when there are buttons.
    const fitsWithout = wrap(said.text, Math.max(8, roomBase - 4), 200).length <= 2
    const hasButtons = isMessage || canExplain || !fitsWithout
    const avail = roomBase - (hasButtons ? BUTTON_COL + 1 : 0)
    const inner = Math.max(8, avail - 4) // border + padding
    const cut = wrap(said.text, inner, 200).length > 2
    const shown = wrap(said.text, inner, 2)
    const buttons = []
    if (cut) {
      const seed = said.text
      buttons.push(
        <Button key="more" label="more" dimColor
          onPress={() => { openChat($, seed, viewportColumns).catch(() => undefined) }} />,
      )
    }
    if (canExplain) {
      const original = said.text.replace(/^heads-up: /, '')
      buttons.push(
        <Button key="explain" label="explain" dimColor
          onPress={() => {
            setBubble(b => ({ ...b, text: 'explaining...', source: 'explain' }))
            void (async () => {
              const reply = await $.model.fork({ prompt: EXPLAIN_PROMPT(original), effort: 'low' })
              const text = reply.isAnswered ? plain(reply.text) : `couldn't explain (${reply.reason})`
              setBubble(b => ({ ...b, text, source: 'explain' }))
            })().catch(() => undefined)
          }} />,
      )
    }
    if (isMessage) {
      buttons.push(
        <Button key="dismiss" label="dismiss" dimColor
          onPress={() => setBubble(b => ({ text: quipNow, source: 'quip', turn: b.turn }))} />,
      )
    }
    const bubbleBox = (
      <Box flexDirection="row" alignItems="flex-end" flexGrow={1} justifyContent="flex-end">
        {buttons.length ? (
          <Box flexDirection="column" width={BUTTON_COL} marginRight={1} justifyContent="flex-end">
            {buttons}
          </Box>
        ) : null}
        <Box borderStyle="single" borderColor={bar} paddingX={1} flexGrow={1} flexDirection="column">
          {shown.map((l, i) => <Text key={`b${i}`}>{l}</Text>)}
        </Box>
        <Text color={bar}>▶</Text>
      </Box>
    )

    return (
      <Box width={cols} flexDirection="row" justifyContent="flex-end" alignItems="flex-end">
        {showTrend ? trendBox : null}
        {showActivity ? activityBox : null}
        {showBubble ? bubbleBox : <Box flexGrow={1} />}
        {picture}
      </Box>
    )
  })
}
