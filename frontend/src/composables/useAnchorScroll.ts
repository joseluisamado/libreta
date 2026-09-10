// Region-preserving scroll across the viewer ↔ editor transition (and the
// editor's own rendered ↔ source toggle).
//
// A raw scrollTop is meaningless across panes: the rendered viewer (a .prose
// <div>), the WYSIWYG editor (a ProseMirror doc), and the raw-source view (a
// <pre>/<textarea>) lay the same content out at different pixel heights, and
// each pane has its own scroll container. What *is* stable across all of them
// is the sequence of headings — every pane renders <h1>–<h6> in document
// order. So we anchor on "the last heading at or above the viewport top, plus
// how far past it we've scrolled" and re-find that heading in the destination.
//
// The captured anchor lives at module scope so a component unmounting (leaving
// a route) can hand it to the component that mounts next. It is single-shot:
// whoever consumes it clears it, so it never leaks into an unrelated
// navigation.

export interface ScrollAnchor {
  // Index of the anchor heading among all headings in the pane, in document
  // order. Primary key for re-finding it.
  headingIndex: number
  // The heading's trimmed text, used to validate the index survived edits
  // (headings added/removed between capture and restore shift the index).
  headingText: string
  // Pixels the viewport top sits past the anchor heading's top edge, so we
  // land mid-section rather than snapping the heading to the very top.
  offsetPx: number
  // Fallback for pages with no headings at all: the raw fraction scrolled
  // (scrollTop / scrollHeight), applied to the destination's own height.
  fraction: number
  // Page identity (source/label + path) the anchor belongs to. The consumer
  // only applies an anchor whose key matches its own page, so a stale anchor
  // left by an abandoned view↔edit hop never mis-scrolls an unrelated page.
  key: string
}

let pending: ScrollAnchor | null = null

const HEADING_SELECTOR = 'h1, h2, h3, h4, h5, h6'

function headingsIn(scope: HTMLElement): HTMLElement[] {
  return Array.from(scope.querySelectorAll<HTMLElement>(HEADING_SELECTOR))
}

// Vertical offset of `el`'s top relative to the scroll container's content
// top (i.e. the scrollTop at which `el` would sit flush with the container's
// top edge). Uses bounding rects so it works regardless of nesting.
function offsetTopWithin(el: HTMLElement, container: HTMLElement): number {
  return (
    el.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop
  )
}

// Capture the current scroll position of `container` as a heading anchor.
// `scope` is the element containing the headings (the content root); it may be
// the container itself. Returns null when there is nothing meaningful to
// capture (empty/at-top with no headings), so callers can skip a no-op.
export function captureAnchor(
  container: HTMLElement,
  scope: HTMLElement,
  key: string,
): ScrollAnchor | null {
  const top = container.scrollTop
  const headings = headingsIn(scope)
  const fraction = container.scrollHeight > 0 ? top / container.scrollHeight : 0

  if (!headings.length) {
    if (top === 0) return null
    return { headingIndex: -1, headingText: '', offsetPx: 0, fraction, key }
  }

  // Find the last heading at or above the viewport top; that is the section
  // the user is currently reading.
  let idx = 0
  let anchorTop = offsetTopWithin(headings[0]!, container)
  for (let i = 0; i < headings.length; i++) {
    const t = offsetTopWithin(headings[i]!, container)
    if (t <= top + 1) {
      idx = i
      anchorTop = t
    } else {
      break
    }
  }

  return {
    headingIndex: idx,
    headingText: (headings[idx]!.textContent ?? '').trim(),
    offsetPx: top - anchorTop,
    fraction,
    key,
  }
}

// Store an anchor for the next pane to consume. Passing null clears it.
export function setPendingAnchor(anchor: ScrollAnchor | null): void {
  pending = anchor
}

// Take (and clear) the pending anchor, if any. When `key` is given, the
// anchor is only returned (and cleared) if it belongs to that page; an anchor
// for a different page is left untouched so it can't mis-scroll here.
export function takePendingAnchor(key?: string): ScrollAnchor | null {
  if (!pending) return null
  if (key !== undefined && pending.key !== key) return null
  const a = pending
  pending = null
  return a
}

// Resolve where an anchor lands in the destination pane, in scrollTop pixels.
// Returns null when the anchor can't be located (no matching heading and no
// usable fraction), so the caller can leave the scroll untouched.
function resolveTarget(
  anchor: ScrollAnchor,
  container: HTMLElement,
  scope: HTMLElement,
): number | null {
  const headings = headingsIn(scope)

  if (anchor.headingIndex >= 0 && headings.length) {
    // Prefer the same index; if the text no longer matches (page edited),
    // search for the nearest heading with the same text.
    let target = headings[anchor.headingIndex] ?? null
    const matches = (el: HTMLElement | null): boolean =>
      !!el && (el.textContent ?? '').trim() === anchor.headingText
    if (!matches(target) && anchor.headingText) {
      target = headings.find((h) => (h.textContent ?? '').trim() === anchor.headingText) ?? target
    }
    if (target) {
      return Math.max(0, offsetTopWithin(target, container) + anchor.offsetPx)
    }
  }

  // No headings to anchor to: fall back to the same scroll fraction.
  if (anchor.fraction > 0) {
    return Math.max(0, anchor.fraction * container.scrollHeight)
  }
  return null
}

// Apply an anchor to `container`, re-applying while the content is still
// growing (async markdown render, mermaid, highlight, editor mount) so the
// target doesn't get lost to a late reflow. Mirrors the settle-loop the
// router uses for history-restore. Resolves once the height stabilizes or the
// cap is hit.
export function restoreAnchor(
  container: HTMLElement,
  scope: HTMLElement,
  anchor: ScrollAnchor,
  maxMs = 1500,
): Promise<void> {
  return new Promise((resolve) => {
    const start = performance.now()
    let lastHeight = -1
    let stable = 0
    const tick = (): void => {
      const target = resolveTarget(anchor, container, scope)
      if (target !== null) container.scrollTop = target
      const h = container.scrollHeight
      if (h === lastHeight) {
        stable += 1
        if (stable >= 3) {
          if (target !== null) container.scrollTop = target
          resolve()
          return
        }
      } else {
        stable = 0
        lastHeight = h
      }
      if (performance.now() - start >= maxMs) {
        if (target !== null) container.scrollTop = target
        resolve()
        return
      }
      setTimeout(tick, 50)
    }
    tick()
  })
}
