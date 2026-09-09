import { describe, it, expect, beforeAll, beforeEach, vi } from 'vitest'
import { useDraft } from '@/composables/useDraft'

const KEY = 'source/s1/foo/bar'
const STORAGE_KEY = `libreta:draft:${KEY}`

// jsdom in this setup doesn't expose a working localStorage; useDraft reads and
// writes window.localStorage. A minimal in-memory shim is enough.
beforeAll(() => {
  const store = new Map<string, string>()
  const shim = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  }
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: shim })
  Object.defineProperty(window, 'localStorage', { configurable: true, value: shim })
})

describe('useDraft', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.useRealTimers()
  })

  it('persists a draft after the debounce and exposes nothing until check', () => {
    vi.useFakeTimers()
    const d = useDraft(() => KEY)
    d.check('original')
    expect(d.pending.value).toBeNull()

    d.save('edited body')
    // Not written yet — debounced.
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
    vi.advanceTimersByTime(600)

    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) as string)
    expect(stored.body).toBe('edited body')
    expect(stored.baseBody).toBe('original')
    expect(typeof stored.savedAt).toBe('number')
  })

  it('surfaces a stored draft that differs from disk on check', () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ body: 'recovered', baseBody: 'original', savedAt: Date.now() }),
    )
    const d = useDraft(() => KEY)
    d.check('original')
    expect(d.pending.value?.body).toBe('recovered')
    expect(d.pendingIsStale.value).toBe(false)
  })

  it('marks the draft stale when the on-disk body changed since it was made', () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ body: 'recovered', baseBody: 'old-disk', savedAt: Date.now() }),
    )
    const d = useDraft(() => KEY)
    d.check('new-disk')
    expect(d.pending.value?.body).toBe('recovered')
    expect(d.pendingIsStale.value).toBe(true)
  })

  it('drops and does not surface a draft equal to the on-disk body', () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ body: 'same', baseBody: 'same', savedAt: Date.now() }),
    )
    const d = useDraft(() => KEY)
    d.check('same')
    expect(d.pending.value).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('clears the stored draft when the body returns to the on-disk value', () => {
    vi.useFakeTimers()
    const d = useDraft(() => KEY)
    d.check('original')
    d.save('edited')
    vi.advanceTimersByTime(600)
    expect(localStorage.getItem(STORAGE_KEY)).not.toBeNull()

    // User undoes everything back to disk state.
    d.save('original')
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('refuses to overwrite a stored draft while a recovery decision is pending', () => {
    vi.useFakeTimers()
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ body: 'recovered', baseBody: 'original', savedAt: Date.now() }),
    )
    const d = useDraft(() => KEY)
    d.check('original')
    expect(d.pending.value?.body).toBe('recovered')

    // The editor beneath the prompt is loaded with the on-disk body and may
    // emit an update before the user decides. That must not clobber the draft.
    d.save('original')
    vi.advanceTimersByTime(600)
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) as string)
    expect(stored.body).toBe('recovered')

    // Once the user continues (pending cleared), saves persist again.
    d.pending.value = null
    d.save('further edits')
    vi.advanceTimersByTime(600)
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) as string).body).toBe('further edits')
  })

  it('clear() removes the stored draft and the pending ref', () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ body: 'recovered', baseBody: 'original', savedAt: Date.now() }),
    )
    const d = useDraft(() => KEY)
    d.check('original')
    expect(d.pending.value).not.toBeNull()

    d.clear()
    expect(d.pending.value).toBeNull()
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('treats malformed stored JSON as no draft', () => {
    localStorage.setItem(STORAGE_KEY, '{not json')
    const d = useDraft(() => KEY)
    d.check('original')
    expect(d.pending.value).toBeNull()
  })
})
