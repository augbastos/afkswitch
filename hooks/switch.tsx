import type { EngineInterface, Register } from 'claude-code'

type Status = 'available' | 'afk'
type Cache = {
  initialized: boolean
  lastGood: Status | null
  readable: boolean
  pending: boolean
  failed: boolean
  revision: number
}

// Mirror parse_since/context_problem/problems_v1/problems_v2 in the state helper.
const validSince = (value: unknown): boolean => {
  if (typeof value !== 'string') return false
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-](\d{2}):(\d{2}))$/.exec(value)
  if (!parts || parts[0] !== value) return false
  const [, y, m, d, h, minute, s, zone, oh, om] = parts
  const year = Number(y), month = Number(m), day = Number(d)
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1] &&
    Number(h) < 24 && Number(minute) < 60 && Number(s) < 60 &&
    (zone === 'Z' || Number(oh) * 60 + Number(om) < 1440)
}

const validContext = (value: unknown): boolean => value === null ||
  (typeof value === 'string' && [...value].length <= 2048 &&
    !/[\u0000-\u0008\u000b-\u001f\u007f-\u009f\ud800-\udfff]/u.test(value))

const readStatus = async ($: EngineInterface): Promise<Status | null> => {
  const override = await $.env.get('AFKSWITCH_STATE_DIR')
  const home = override ? undefined : (await $.env.get('HOME')) || (await $.env.get('USERPROFILE'))
  const directory = override || (home ? `${home}/.afkswitch` : undefined)
  if (!directory) return null

  try {
    const text = await $.fs.read(`${directory.replace(/[\\/]+$/, '')}/state.json`)
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
    return state.status
  } catch {
    // Missing, unreadable, malformed and future state are neutral, never present.
    return null
  }
}

const refresh = async ($: EngineInterface, cache: Cache): Promise<Status | null> => {
  const request = ++cache.revision
  try {
    const status = await readStatus($)
    if (request === cache.revision) {
      cache.initialized = true
      cache.readable = status !== null
      if (status !== null) cache.lastGood = status
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
export const register: Register = on => {
  const cache: Cache = {
    initialized: false, lastGood: null, readable: false,
    pending: false, failed: false, revision: 0,
  }

  on('session.start', async ($, e, next) => {
    await refresh($, cache)
    cache.failed = false
    $.ui.invalidate('ui.render')
    return next(e)
  }).catch(($, e, next) => next(e))

  on('prompt.submit', async ($, e, next) => {
    await refresh($, cache)
    $.ui.invalidate('ui.render')
    return next(e)
  }).catch(($, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    await refresh($, cache)
    cache.failed = false
    $.ui.invalidate('ui.render')
    return next(e)
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    // This release advertises the terminal only; remote paint is not verified.
    if (e.surface !== 'terminal') return next(e)
    if (!cache.initialized) await refresh($, cache)

    const status = cache.readable ? cache.lastGood : null
    const cells = status === 'afk' ? '■□' : status === 'available' ? '□■' : '□□'
    // Capture explicit intent from this drawing; never toggle a later disk value.
    const intended: Status | null = status === 'available' ? 'afk' : status === 'afk' ? 'available' : null
    const { Box, Text, Button } = $.ui.resolve(e)
    const original = await next(e)

    const press = async () => {
      // The synchronous guard also covers two presses of an old drawing.
      if (cache.pending || intended === null) return
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
        const result = intended === 'afk'
          ? await $.command.run({ command: 'afkswitch:afk' })
          : await $.command.run({ command: 'afkswitch:back' })
        const confirmed = await refresh($, cache)
        cache.failed = (result.exitCode !== undefined && result.exitCode !== 0) || confirmed !== intended
      } catch {
        cache.failed = true
        // Show disk truth even if command dispatch or completion failed.
        try { await refresh($, cache) } catch { cache.readable = false }
      } finally {
        cache.pending = false
        // A redraw error must not escape a button handler into the host.
        try { $.ui.invalidate('ui.render') } catch { /* text commands still work */ }
      }
    }

    return (
      <Box flexDirection="column">
        {original}
        <Box flexDirection="row" alignSelf="flex-start" borderStyle="single" paddingX={1} flexShrink={0}>
          <Text color={status === 'afk' ? '#F28C28' : undefined} dimColor={status !== 'afk'}>AFK</Text>
          <Text>{'  '}</Text>
          {cache.pending || intended === null
            ? <Text dimColor={status !== 'afk'}>{cells}</Text>
            : <Button key="afkswitch-toggle" label={cells} plain onPress={press} />}
          {cache.failed ? <Text color="#F28C28">!</Text> : null}
        </Box>
      </Box>
    )
  }).catch(($, e, next) => next(e))
}
