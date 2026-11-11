import type { EngineInterface, Register } from 'claude-code'

type Status = 'available' | 'afk'
type ReadStatus = Status | 'missing' | null

let showOnboarding = false
// The AbovePrompt band is drawn on these surfaces; every other one passes through.
const drawn = (surface: unknown): boolean => surface === 'terminal' || surface === 'desktop'
type Cache = {
  initialized: boolean
  lastGood: ReadStatus
  readable: boolean
  pending: boolean
  awaiting: Status | null
  started: boolean
  failed: boolean
  revision: number
  context: string | null
  ticks: number
  idle: string | null
  timer: { cancel(): void } | null
  blinkOff: boolean
  shown: boolean
  arm: (() => { cancel(): void }) | null
}

// A short label beside the switch while away. It names a kind of absence found in the
// AFK context by keyword; the context text itself is never drawn.
// Plain keyword hits, not understanding: the earliest hit in the text wins, then row order.
// The lists are narrow on purpose: an /afk note is often about the agent's work, not the human's.
const KINDS: [RegExp, string][] = [
  [/(?:^\s*work(?:ing)?\s*$|\b(?:(?:at|to|from|for|after|before|off)\s+work|night shift|shift work|meetings?|(?<!post |box |out of )office(?! hours)|trabalh\w*|turnos?|reuni\w*|escrit[oó]rio|expediente|emprego)\b)/i, '💼 at work'],
  [/\b(?:sleep(?!\s*mode)(?:s|ing|y)?|asleep|slept|nap(?:s|ping|ped)?|bedtime|(?:go|going|off) to bed|in bed|good ?night|dorm(?:ir|indo|i|e)\w*|sono|soneca|cochil\w*|cama|boa noite)\b/i, '💤 sleeping'],
  [/\b(?:(?<!coffee )shop(?:s|ping|ped)?|grocer(?:y|ies)|supermarket|mall|(?:super)?mercado(?! (?:livre|pago|financeiro|de trabalho))|compras?|compr(?:ar|ando|ei))\b/i, '🛒 shopping'],
  [/\b(?:travel(?:s|ing|ling|ed|led)?|trip to|(?:business|road|weekend|day|work)[ -]trips?|flights?(?! sim)|fly(?:ing)?|flew|airport|vacation|holidays?|viag(?:em|ens)|viaj\w*|v[oô]os?|aeroportos?|f[eé]rias|feriado|rodovi[aá]ria)\b/i, '🛫 traveling'],
]
// With no note at all, one of these shows now and then: on every third prompt or finished
// turn, for IDLE_MS, then it is gone. Two timers run only meanwhile; nothing polls.
const IDLE = [
  '🌳 at the park', '💃 dancing', '💬 chatting', '☕ coffee break',
  '🚶 out for a walk', '🎧 listening to music', '🍜 grabbing a bite', '📚 reading',
  '🦆 arguing with a duck', '🧦 hunting the other sock', '🍕 negotiating with a pizza',
  '🐈 being ignored by a cat', '🪴 talking to the plants',
]
// About one idle label in twenty comes from this list instead.
const RARE = ['🛸 abducted, back soon', '👻 haunting the hallway', '🌀 stuck in a time loop']
const RARE_CHANCE = 0.05
// Exported for the tests, which pass fixed numbers in place of the two dice.
export const pickIdle = (pool = Math.random(), which = Math.random()): string => {
  const from = pool < RARE_CHANCE ? RARE : IDLE
  return from[Math.floor(which * from.length)]
}
const IDLE_EVERY = 3
const IDLE_MS = 8000
const BLINK_MS = 600
const BLINK_FOR_MS = 3000  // then the label holds still until IDLE_MS

function kindOf(context: string | null): string | null {
  if (context === null) return null
  let best: string | null = null
  let at = Infinity
  for (const [words, label] of KINDS) {
    const found = context.search(words)
    if (found >= 0 && found < at) { at = found; best = label }
  }
  return best
}

function stopIdle(cache: Cache): void {
  cache.timer?.cancel()
  cache.timer = null
  cache.idle = null
  cache.blinkOff = false
}

function tick($: EngineInterface, cache: Cache): void {
  if (!cache.readable) return  // an unreadable state is unknown, not a return: leave things as they are
  // Idle labels are for an absence with no note, on a surface that draws the switch.
  if (cache.lastGood !== 'afk' || cache.context !== null || !cache.shown) {
    cache.ticks = 0
    stopIdle(cache)
    return
  }
  cache.ticks += 1
  if (cache.ticks % IDLE_EVERY !== 0) return  // a label already showing keeps its own clock
  stopIdle(cache)
  try {
    // Prefer the timers armed from session.start; ones started from a later event are the fallback.
    cache.timer = cache.arm ? cache.arm() : showIdle($, cache)
    cache.idle = pickIdle()
  } catch {
    stopIdle(cache)  // no timer, no label: a label must never outlive its clock
  }
}

// While an idle label shows, its emoji blinks for BLINK_FOR_MS; after IDLE_MS the label is gone
// and every timer has stopped.
function showIdle($: EngineInterface, cache: Cache): { cancel(): void } {
  let beats = 0
  const blink = $.clock.every(BLINK_MS, () => {
    beats += 1
    cache.blinkOff = beats * BLINK_MS < BLINK_FOR_MS ? !cache.blinkOff : false
    if (beats * BLINK_MS >= BLINK_FOR_MS) blink.cancel()
    $.ui.invalidate('ui.render')
  })
  try {
    const hide = $.clock.after(IDLE_MS, () => {
      blink.cancel()
      cache.timer = null
      cache.idle = null
      cache.blinkOff = false
      $.ui.invalidate('ui.render')
    })
    return { cancel: () => { blink.cancel(); hide.cancel() } }
  } catch (error) {
    blink.cancel()
    throw error
  }
}

// Mirror parse_since/context_problem/problems_v1/problems_v2 in the state helper.
function validSince(value: unknown): boolean {
  if (typeof value !== 'string') return false
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-](\d{2}):(\d{2}))$/.exec(value)
  if (!parts || parts[0] !== value) return false
  const [, y, m, d, hour, minute, s, zone, oh, om] = parts
  const year = Number(y), month = Number(m), day = Number(d)
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1] &&
    Number(hour) < 24 && Number(minute) < 60 && Number(s) < 60 &&
    (zone === 'Z' || Number(oh) * 60 + Number(om) < 1440)
}

const validContext = (value: unknown): boolean => value === null ||
  (typeof value === 'string' && [...value].length <= 2048 &&
    !/[\u0000-\u0008\u000b-\u001f\u007f-\u009f\ud800-\udfff]/u.test(value))

async function readStatus($: EngineInterface, out: { context: string | null }): Promise<ReadStatus> {
  out.context = null
  try {
    const override = await $.env.get('AFKSWITCH_STATE_DIR')
    // Mirror Python's Path.home(), which the helper uses: on Windows it reads USERPROFILE and ignores HOME.
    const windows = !override && (await $.env.get('OS')) === 'Windows_NT'
    const profile = override ? undefined : await $.env.get('USERPROFILE')
    const posix = override ? undefined : await $.env.get('HOME')
    const home = windows ? profile || posix : posix || profile
    const directory = override || (home ? `${home}/.afkswitch` : undefined)
    if (!directory) return null
    const path = `${directory.replace(/[\\/]+$/, '')}/state.json`
    if (await $.fs.exists(path) === false) return 'missing'
    const text = await $.fs.read(path)
    const value: unknown = JSON.parse(text.replace(/^\uFEFF/, ''))
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return null
    const state = value as Record<string, unknown>
    const keys = state.version === 1
      ? ['version', 'status', 'since', 'context']
      : ['version', 'status', 'since', 'context', 'generation']
    if (Object.keys(state).length !== keys.length || !keys.every(key => Object.hasOwn(state, key))) return null
    if (state.version !== 1 && state.version !== 2) return null
    if (state.status !== 'afk' && state.status !== 'available') return null
    if (!validSince(state.since) || !validContext(state.context)) return null
    if (state.version === 2 &&
      (typeof state.generation !== 'number' || !Number.isInteger(state.generation) || state.generation < 1 ||
        (state.status === 'available' && state.context !== null))) return null
    if (state.status === 'afk') out.context = state.context as string | null
    return state.status
  } catch {
    // Unreadable, malformed and future state are unknown, never present.
    return null
  }
}

async function refresh($: EngineInterface, cache: Cache): Promise<ReadStatus> {
  const request = ++cache.revision
  try {
    const read = { context: null as string | null }
    const status = await readStatus($, read)
    if (request === cache.revision) {
      cache.context = read.context
      cache.initialized = true
      cache.readable = status !== null
      if (status !== null) cache.lastGood = status
      if (cache.awaiting && status === cache.awaiting) {
        cache.pending = false
        cache.awaiting = null
        cache.started = false
        cache.failed = false
      }
    }
    return status
  } catch (error) {
    if (request === cache.revision) {
      cache.initialized = false
      cache.readable = false
    }
    throw error
  }
}

// A drawing cache only: the helper used by the skills remains the single writer.
// A hook that throws is skipped by the engine and the chain continues without it.
export const register: Register = on => {
  const cache: Cache = {
    initialized: false, lastGood: null, readable: false,
    pending: false, awaiting: null, started: false, failed: false, revision: 0,
    context: null, ticks: 0, idle: null, timer: null, blinkOff: false, shown: false, arm: null,
  }

  on('session.start', async ($, e, next) => {
    cache.arm = () => showIdle($, cache)
    cache.shown = drawn(e.surface)
    showOnboarding = false
    try {
      // Spend the one-time onboarding only where it is shown.
      const seen = drawn(e.surface) ? await $.store.get('onboardingVersion') : 1
      if (!(typeof seen === 'number' && seen >= 1)) {
        showOnboarding = true
        await $.store.set('onboardingVersion', 1)
      }
    } catch { showOnboarding = false }
    await refresh($, cache)
    cache.failed = false
    $.ui.invalidate('ui.render')
    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    showOnboarding = false
    $.ui.invalidate('ui.render')
    await refresh($, cache)
    tick($, cache)
    $.ui.invalidate('ui.render')
    return next(e)
  })

  on('command.run', ($, e, next) => {
    if (cache.awaiting && e.origin?.kind === 'plugin' && e.origin.name === 'afkswitch' &&
      (e.command === 'afkswitch:afk' || e.command === 'afkswitch:back')) cache.started = true
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    await refresh($, cache)
    if (cache.awaiting) {
      if (cache.started) {
        cache.pending = false
        cache.awaiting = null
        cache.started = false
        cache.failed = true
      }
    } else cache.failed = false
    tick($, cache)
    $.ui.invalidate('ui.render')
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    cache.shown = drawn(e.surface)
    if (!cache.shown) return next(e)
    if (!cache.initialized) await refresh($, cache)

    const status = cache.readable ? cache.lastGood : null
    const cells = status === 'afk' ? '■□' : status === 'available' ? '□■' : '□□'
    // Capture explicit intent from this drawing; never toggle a later disk value.
    const intended: Status | null = status === 'available' || status === 'missing' ? 'afk' : status === 'afk' ? 'available' : null
    const kind = status === 'afk' ? kindOf(cache.context) : null
    // Only idle labels blink: on the off beat the emoji gives way to two spaces, so the words stay put.
    const idle = cache.idle && cache.blinkOff ? cache.idle.replace(/^\S+/, '  ') : cache.idle
    // Not while a press is pending or has just failed: that row already has its own text.
    const indicator = status === 'afk' && !cache.pending && !cache.failed ? kind ?? idle : null
    const { Box, Text, Button } = $.ui.resolve(e)
    const original = await next(e)

    const press = async () => {
      // The synchronous guard also covers two presses of an old drawing.
      if (cache.pending || intended === null) return
      showOnboarding = false
      cache.pending = true
      cache.failed = false
      try {
        $.ui.invalidate('ui.render')
        const current = await refresh($, cache)
        if (current === intended) return
        // Do not act from a file we cannot currently understand.
        if (current === null) {
          cache.failed = true
          return
        }
        // Set before running: an idle session fires command.run inside this call.
        cache.awaiting = intended
        cache.started = false
        intended === 'afk'
          ? await $.command.run({ command: 'afkswitch:afk' })
          : await $.command.run({ command: 'afkswitch:back' })
      } catch {
        cache.awaiting = null
        cache.started = false
        cache.failed = true
        // Show disk truth even if command dispatch or completion failed.
        try { await refresh($, cache) } catch { cache.readable = false }
      } finally {
        cache.pending = cache.awaiting !== null
        // A redraw error must not escape a button handler into the host.
        try { $.ui.invalidate('ui.render') } catch { /* text commands still work */ }
      }
    }

    return (
      <Box flexDirection="column">
        {original}
        {/* A Box takes no clicks, so while the switch can be pressed the whole inside of
            the border is one Button (padding in its label). A Button has no color, so
            "away" shows on the border instead of the word. */}
        <Box flexDirection="row" alignSelf="flex-start" alignItems="center">
        <Box
          flexDirection="row"
          borderStyle="single"
          borderColor={status === 'afk' ? '#F28C28' : undefined}
          paddingX={cache.pending || intended === null ? 1 : 0}
          flexShrink={0}
        >
          {cache.pending || intended === null
            ? <Text color={status === 'afk' ? '#F28C28' : undefined} dimColor={status !== 'afk'}>AFK</Text>
            : <Button key="afkswitch-toggle" label={` AFK  ${cells} `} plain dimColor={status !== 'afk'} onPress={press} />}
          {cache.pending || intended === null ? <Text>{'  '}</Text> : null}
          {cache.pending || intended === null ? <Text dimColor={status !== 'afk'}>{cells}</Text> : null}
          {cache.pending || cache.failed ? <Text>{' '}</Text> : null}
          {cache.pending ? <Text dimColor>saving…</Text> : null}
          {cache.failed ? <Text color="#F28C28">not switched — try /afk or /back</Text> : null}
        </Box>
        {indicator ? <Text key="afkswitch-indicator" dimColor>{` ${indicator}`}</Text> : null}
        </Box>
        {showOnboarding ? <Box flexDirection="column">
          <Text dimColor>{"AFKSwitch is ready — [ AFK □■ ] means you're here."}</Text>
          <Text dimColor>{"Click it when you leave; click again when you're back."}</Text>
          <Text dimColor>Use /afk [note] or /back [note] for optional context.</Text>
        </Box> : null}
      </Box>
    )
  })
}
