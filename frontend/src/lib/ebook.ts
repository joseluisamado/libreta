// Centralised foliate-js setup so the full viewer (EbookView) and the folder
// cover thumbnails (PreviewTile) share one import path and can't drift.
//
// foliate-js ships as raw ES modules (package.json `exports: { './*.js':
// './*.js' }`), so we import deep paths. `view.js` exports `makeBook` and, as a
// side effect of import, registers the <foliate-view> custom element.
//
// R6 (server-rendered HTML never executes user-supplied JS) — IMPORTANT:
// foliate's EPUB loader defaults to `allowScript = false` and strips every
// script-type resource from the book while rewriting its assets (see
// foliate-js/epub.js: `if (isScript && !this.allowScript) return null`). MOBI,
// KF8, FB2 and CBZ have no script concept at all. The content iframe carries
// `sandbox="allow-same-origin allow-scripts"`, but that is only for foliate's
// own injected pagination runtime — book-supplied JS never reaches it because
// it was already dropped at load. Do NOT set `allowScript = true` anywhere: it
// would let publisher JavaScript execute and break R6.
import { makeBook } from 'foliate-js/view.js'

// Supported formats, for documentation/reference. foliate sniffs the concrete
// format from the bytes; we never branch on it ourselves.
//   EPUB, MOBI, KF8/AZW3, FB2 (+.fb2.zip), CBZ.
export type FoliateBook = {
  metadata?: { title?: string }
  toc?: unknown[]
  dir?: 'ltr' | 'rtl'
  getCover?: () => Promise<Blob | null>
}

/** Build a foliate book object from a URL or Blob. Throws on unsupported type. */
export async function openBook(src: string | Blob): Promise<FoliateBook> {
  return (await makeBook(src)) as FoliateBook
}

/**
 * Extract a book's cover as an object URL, or null if it has none (common for
 * plain MOBI/FB2). The caller owns the returned URL and must revoke it.
 */
export async function coverObjectUrl(src: string | Blob): Promise<string | null> {
  const book = await openBook(src)
  const blob = await book.getCover?.()
  return blob ? URL.createObjectURL(blob) : null
}
