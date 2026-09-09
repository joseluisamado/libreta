import { computed, ref, type Ref } from 'vue'

// Per-page draft buffer backed by localStorage.
//
// While a page is being edited, every change is written (debounced) to
// localStorage so that closing the tab or refreshing the page does not lose
// unsaved work. This is a *recovery buffer*, not a source of truth: the
// filesystem / git repo remains authoritative (PROJECT.md P1). On a successful
// save — or an explicit discard — the draft is cleared. Because it lives purely
// in the browser it works identically for git-source pages and watched pages.

const PREFIX = 'libreta:draft:'
const DEBOUNCE_MS = 500

interface Draft {
  // The unsaved markdown body.
  body: string
  // The on-disk body this draft was started from. Lets us detect that the file
  // changed on disk since the draft was made (a "stale" draft) and warn before
  // continuing would clobber those newer changes.
  baseBody: string
  // ms since epoch when the draft was last written.
  savedAt: number
}

export interface DraftHandle {
  // A stored draft that differs from the current on-disk body, if any. Cleared
  // once the user continues or discards.
  pending: Ref<Draft | null>
  // True when the pending draft was based on an older on-disk body than the one
  // now loaded — continuing it will overwrite the newer on-disk changes.
  pendingIsStale: Ref<boolean>
  // Human-readable "how long ago" for the pending draft, for the banner.
  pendingAgeLabel: Ref<string>
  // Read the stored draft for `key` and, if it differs from `currentBody`,
  // expose it as `pending`. Call once after the page loads.
  check: (currentBody: string) => void
  // Persist the given body as a draft for `key` (debounced). No-op when the body
  // equals the on-disk base (nothing to recover).
  save: (body: string) => void
  // Drop the stored draft and clear `pending`.
  clear: () => void
}

function keyFor(id: string): string {
  return PREFIX + id
}

function ageLabel(savedAt: number): string {
  const secs = Math.max(0, Math.round((Date.now() - savedAt) / 1000))
  if (secs < 60) return 'just now'
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`
  const days = Math.round(hours / 24)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

// `key` is a reactive identifier for the page being edited (e.g.
// "source/<id>/<path>"). It is read lazily so the same handle survives page
// navigation within one editor view.
export function useDraft(key: () => string): DraftHandle {
  const pending = ref<Draft | null>(null)
  // The on-disk body the currently-loaded page was opened with. Used both to
  // skip writing a no-op draft and to decide whether a stored draft is stale.
  const base = ref('')

  const pendingIsStale = computed(
    () => pending.value !== null && pending.value.baseBody !== base.value,
  )
  const pendingAgeLabel = computed(() => (pending.value ? ageLabel(pending.value.savedAt) : ''))

  let timer: ReturnType<typeof setTimeout> | null = null

  function read(): Draft | null {
    try {
      const raw = window.localStorage.getItem(keyFor(key()))
      if (!raw) return null
      const parsed = JSON.parse(raw) as Partial<Draft>
      if (typeof parsed.body !== 'string') return null
      return {
        body: parsed.body,
        baseBody: typeof parsed.baseBody === 'string' ? parsed.baseBody : '',
        savedAt: typeof parsed.savedAt === 'number' ? parsed.savedAt : Date.now(),
      }
    } catch {
      // Malformed JSON, or localStorage disabled — treat as no draft.
      return null
    }
  }

  function check(currentBody: string): void {
    base.value = currentBody
    const draft = read()
    if (draft && draft.body !== currentBody) {
      pending.value = draft
    } else {
      // A draft equal to what is on disk carries nothing to recover; drop it.
      if (draft) clear()
      pending.value = null
    }
  }

  function save(body: string): void {
    if (pending.value !== null) {
      // A recovered draft is still awaiting the continue/discard decision. The
      // editor beneath the prompt is loaded with the on-disk body, and any
      // update it emits before the user decides would otherwise clobber the
      // stored draft. Refuse to write until the decision is made (continue,
      // which clears `pending`, or discard, which removes the draft).
      return
    }
    if (body === base.value) {
      // Body matches disk again (e.g. the user undid everything) — no draft to
      // keep. Clear any stale one and stop.
      clear()
      return
    }
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      timer = null
      const draft: Draft = { body, baseBody: base.value, savedAt: Date.now() }
      try {
        window.localStorage.setItem(keyFor(key()), JSON.stringify(draft))
      } catch {
        // Quota exceeded or storage disabled — nothing we can do; the in-editor
        // buffer is still intact, only the recovery guarantee is lost.
      }
    }, DEBOUNCE_MS)
  }

  function clear(): void {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    pending.value = null
    try {
      window.localStorage.removeItem(keyFor(key()))
    } catch {
      // ignore
    }
  }

  return { pending, pendingIsStale, pendingAgeLabel, check, save, clear }
}
