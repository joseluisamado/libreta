// HTML-file rendering for the viewer and preview tiles.
//
// R6 (CLAUDE.md / PROJECT.md P-?) — server-rendered HTML never executes
// user-supplied JS. HTML *files* in a wiki repo are content like any other,
// so we render them, but we strip everything executable first: <script>,
// inline event handlers, javascript: URLs, and JS-bearing embeds. CSS and
// images are content, not code, so they survive — a stripped page shows its
// layout and text, just inert. This mirrors how the markdown renderer gets
// R6 for free via markdown-it's `html: false`; HTML files have no such
// gatekeeper, so we sanitize explicitly with DOMPurify (the standard,
// fully-offline — R5 — tool for this).

import DOMPurify from 'dompurify'

// Tags whose entire point is execution or embedding remote/active content.
// Removed outright (DOMPurify drops the element and its children for these).
const FORBID_TAGS = ['script', 'iframe', 'object', 'embed', 'noscript', 'base'] as const

// Resolve a relative URL referenced *inside* an HTML file (img src, link
// href, a href) to the asset endpoint for the file's source/watched folder,
// so sidecar artifacts (CSS, images, a co-located folder) load. Absolute
// URLs, data:, #anchors and mailto: are left untouched. Mirrors
// resolveAssetUrl() in markdown.ts.
function assetBase(sourceId?: string, watchedLabel?: string): string | null {
  if (watchedLabel) return `/api/v1/watch/${encodeURIComponent(watchedLabel)}/assets`
  if (sourceId) return `/api/v1/sources/${encodeURIComponent(sourceId)}/assets`
  return null
}

function isRerootable(url: string): boolean {
  if (!url) return false
  if (/^[a-z][a-z0-9+.-]*:/i.test(url)) return false // has a scheme (http:, data:, mailto:, javascript:)
  if (url.startsWith('//')) return false // protocol-relative
  if (url.startsWith('#')) return false // same-page anchor
  if (url.startsWith('/')) return false // already root-absolute
  return true
}

// Join the HTML file's parent directory with a relative reference, collapsing
// "." and ".." segments. `pagePath` is the file's path within the source.
function resolveRelative(ref: string, pagePath: string): string {
  const base = pagePath.split('/').filter(Boolean).slice(0, -1)
  const out = [...base]
  for (const seg of ref.split('/')) {
    if (seg === '' || seg === '.') continue
    if (seg === '..') {
      out.pop()
      continue
    }
    out.push(seg)
  }
  return out.map(encodeURIComponent).join('/')
}

export interface SanitizeContext {
  pagePath?: string
  sourceId?: string
  watchedLabel?: string
  // Thumbnail mode: drop non-visible head leftovers (title/link/style/meta)
  // so a small char budget reaches actual body content. A "Save Page As"
  // doc keeps dozens of <link rel=stylesheet> after sanitizing, which would
  // otherwise fill the whole snippet with invisible markup → blank tile.
  bodyOnly?: boolean
}

// Tags that survive sanitizing but render nothing visible on their own; in
// bodyOnly mode we strip them so the thumbnail shows body content.
const NON_VISIBLE_TAGS = new Set(['TITLE', 'LINK', 'STYLE', 'META', 'HEAD', 'BASE'])

// Sanitize an HTML document/fragment for safe rendering via v-html, and
// reroot relative asset references so co-located artifacts load. Returns a
// string with no executable content.
export function sanitizeHtmlFile(raw: string, ctx: SanitizeContext = {}): string {
  const base = assetBase(ctx.sourceId, ctx.watchedLabel)
  const pagePath = ctx.pagePath ?? ''

  // Reroot src/href on the way through. DOMPurify exposes a hook that runs
  // per-node after its own attribute sanitization, so javascript: URLs and
  // the like are already gone by the time we see them.
  const ATTRS = ['src', 'href', 'poster'] as const
  const hook = (node: Element): void => {
    // Thumbnail mode: strip head-only / non-visible elements so the snippet
    // budget reaches real body content.
    if (ctx.bodyOnly && NON_VISIBLE_TAGS.has(node.tagName)) {
      node.remove()
      return
    }
    // <link> is only safe as a stylesheet; drop preload/prefetch/import/etc.
    // (R5: no surprise remote fetches; R6: rel="import" could execute).
    if (node.tagName === 'LINK') {
      const rel = (node.getAttribute('rel') ?? '').toLowerCase().trim()
      if (rel !== 'stylesheet') {
        node.remove()
        return
      }
    }
    if (!base || !pagePath) return
    for (const attr of ATTRS) {
      const val = node.getAttribute?.(attr)
      if (val && isRerootable(val)) {
        node.setAttribute(attr, `${base}/${resolveRelative(val, pagePath)}`)
      }
    }
    // srcset (img/source) is a comma-separated list of "url descriptor".
    const srcset = node.getAttribute?.('srcset')
    if (base && pagePath && srcset) {
      const rerooted = srcset
        .split(',')
        .map((part) => {
          const t = part.trim()
          const sp = t.indexOf(' ')
          const url = sp === -1 ? t : t.slice(0, sp)
          const desc = sp === -1 ? '' : t.slice(sp)
          return isRerootable(url) ? `${base}/${resolveRelative(url, pagePath)}${desc}` : t
        })
        .join(', ')
      node.setAttribute('srcset', rerooted)
    }
  }

  DOMPurify.addHook('afterSanitizeAttributes', hook)
  try {
    return DOMPurify.sanitize(raw, {
      FORBID_TAGS: [...FORBID_TAGS],
      // DOMPurify already strips on* handlers and javascript: URLs by
      // default; FORBID_ATTR makes the JS-handler intent explicit and
      // covers the form-action / xlink:href vectors.
      FORBID_ATTR: ['formaction', 'xlink:href'],
      // Return a body fragment (not a full <html> we'd nest inside ours),
      // but FORCE_BODY keeps head-only elements like <link>/<style> in the
      // output so a page's stylesheets still apply when rendered inline.
      WHOLE_DOCUMENT: false,
      FORCE_BODY: true,
      ADD_TAGS: ['link', 'style'],
      ADD_ATTR: ['target', 'rel'],
    })
  } finally {
    DOMPurify.removeHook('afterSanitizeAttributes')
  }
}
