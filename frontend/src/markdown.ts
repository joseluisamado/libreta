import MarkdownIt from 'markdown-it'

// Derive markdown-it types from the imported constructor instance. The
// package's namespace exports are awkward to use under "esModuleInterop":
// these one-liners give us just what the renderer extensions need.
type Inst = InstanceType<typeof MarkdownIt>
type RenderRule = NonNullable<Inst['renderer']['rules']['image']>
type StateBlock = Parameters<Parameters<Inst['block']['ruler']['after']>[2]>[0]
type StateInline = Parameters<Parameters<Inst['inline']['ruler']['after']>[2]>[0]
import taskLists from 'markdown-it-task-lists'
import anchor from 'markdown-it-anchor'
import hljs from 'highlight.js'
import katex from 'katex'
import mermaid from 'mermaid'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github.css'
import { scanDetailsRun, type DetailsLine } from '@/lib/details'

mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'antiscript',
})

// Header bar rendered at the top of every code block: the (optional) language
// label plus a copy-to-clipboard button. The button is a real <button> so it
// can receive clicks (a CSS ::before pseudo-element can't); a single delegated
// listener installed below handles the copy. `lang` comes from the fence info
// string, so it's HTML-escaped before injection (R6).
function codeBlockHeader(lang: string): string {
  const label = lang ? `<span class="code-lang">${escapeHtmlText(lang)}</span>` : ''
  return (
    `<div class="code-header">${label}` +
    `<button type="button" class="code-copy" aria-label="Copy code" title="Copy code">` +
    COPY_ICON +
    `</button></div>`
  )
}

function escapeHtmlText(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// Inline SVGs so the button works fully offline (R5): a clipboard glyph for the
// idle state and a check for the transient "copied" confirmation.
const COPY_ICON =
  '<svg class="code-copy-idle" viewBox="0 0 24 24" width="14" height="14" fill="none" ' +
  'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
  '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>' +
  '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>' +
  '<svg class="code-copy-done" viewBox="0 0 24 24" width="14" height="14" fill="none" ' +
  'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
  '<polyline points="20 6 9 17 4 12"></polyline></svg>'

// One delegated listener for all rendered code blocks, regardless of which view
// mounted the HTML. Copies the block's raw text (the <code>'s textContent is the
// original source — highlighting only wraps it in <span>s) to the clipboard.
function installCopyHandler(): void {
  if (typeof document === 'undefined') return
  document.addEventListener('click', (ev) => {
    const target = ev.target
    if (!(target instanceof Element)) return
    const btn = target.closest('button.code-copy')
    if (!(btn instanceof HTMLElement)) return
    // Drop the focus a mouse click leaves on the button: some browsers apply
    // :focus-visible after a click, which would keep the button painted at full
    // opacity even after the pointer leaves the block. Keyboard focus (tabbing)
    // still shows it, since blur only fires here on an actual click.
    btn.blur()
    const pre = btn.closest('pre')
    const code = pre?.querySelector('code')
    if (!code) return
    const text = code.textContent ?? ''
    void navigator.clipboard
      .writeText(text)
      .then(() => flashCopied(btn))
      .catch(() => {
        /* clipboard unavailable (e.g. insecure context) — leave button as-is */
      })
  })
}

function flashCopied(btn: HTMLElement): void {
  btn.classList.add('copied')
  window.setTimeout(() => btn.classList.remove('copied'), 1500)
}

installCopyHandler()

const md = new MarkdownIt({
  html: false, // P4/R6 — strip raw HTML at render. Save-side stripping comes with M2.
  linkify: true,
  typographer: false,
  breaks: false,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        const html = hljs.highlight(str, { language: lang, ignoreIllegals: true }).value
        return `<pre class="hljs">${codeBlockHeader(lang)}<code class="hljs language-${lang}">${html}</code></pre>`
      } catch {
        /* fall through */
      }
    }
    const escaped = str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    return `<pre class="hljs">${codeBlockHeader('')}<code class="hljs">${escaped}</code></pre>`
  },
})
  .use(taskLists, { enabled: false, label: false })
  .use(anchor, { permalink: false, slugify: (s: string) => slugify(s) })

function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

export { slugify }

// --- KaTeX math plugin (supports inline `$x$` and block `$$ ... $$`) ---

function renderMath(src: string, displayMode: boolean): string {
  try {
    return katex.renderToString(src, {
      displayMode,
      throwOnError: false,
      output: 'html',
    })
  } catch {
    return `<code>${src}</code>`
  }
}

function inlineMath(state: StateInline, silent: boolean): boolean {
  if (state.src[state.pos] !== '$') return false
  // Don't match escaped `\$`
  if (state.pos > 0 && state.src[state.pos - 1] === '\\') return false
  // Don't match `$$` (block)
  if (state.src[state.pos + 1] === '$') return false
  const start = state.pos + 1
  let pos = start
  while (pos < state.src.length) {
    if (state.src[pos] === '$' && state.src[pos - 1] !== '\\') break
    pos++
  }
  if (pos >= state.src.length) return false
  // Must not be empty and must not start/end with whitespace (to avoid catching `$5 and $10`).
  const body = state.src.slice(start, pos)
  if (!body.trim()) return false
  if (/^\s|\s$/.test(body)) return false
  if (!silent) {
    const token = state.push('math_inline', 'math', 0)
    token.markup = '$'
    token.content = body
  }
  state.pos = pos + 1
  return true
}

function blockMath(
  state: StateBlock,
  startLine: number,
  endLine: number,
  silent: boolean,
): boolean {
  const begin = (state.bMarks[startLine] ?? 0) + (state.tShift[startLine] ?? 0)
  const max = state.eMarks[startLine] ?? 0
  if (state.src.slice(begin, begin + 2) !== '$$') return false

  // Find closing `$$`
  let nextLine = startLine
  let found = false
  let lastPos = 0
  // Single-line block: $$ x $$
  const firstLine = state.src.slice(begin + 2, max)
  const closeOnFirst = firstLine.lastIndexOf('$$')
  if (closeOnFirst >= 0) {
    found = true
    lastPos = begin + 2 + closeOnFirst
  } else {
    while (++nextLine < endLine) {
      const lineStart = (state.bMarks[nextLine] ?? 0) + (state.tShift[nextLine] ?? 0)
      const lineEnd = state.eMarks[nextLine] ?? 0
      const idx = state.src.slice(lineStart, lineEnd).lastIndexOf('$$')
      if (idx >= 0) {
        found = true
        lastPos = lineStart + idx
        break
      }
    }
  }
  if (!found) return false
  if (silent) return true

  const content = state.src.slice(begin + 2, lastPos).trim()
  const token = state.push('math_block', 'math', 0)
  token.block = true
  token.markup = '$$'
  token.content = content
  token.map = [startLine, nextLine + 1]
  state.line = nextLine + 1
  return true
}

md.inline.ruler.after('escape', 'math_inline', inlineMath)
md.block.ruler.after('blockquote', 'math_block', blockMath, {
  alt: ['paragraph', 'reference', 'blockquote', 'list'],
})
const renderInlineMath: RenderRule = (tokens, idx) => {
  const t = tokens[idx]
  return t ? renderMath(t.content, false) : ''
}
const renderBlockMath: RenderRule = (tokens, idx) => {
  const t = tokens[idx]
  return t ? `<div class="math-block">${renderMath(t.content, true)}</div>` : ''
}
md.renderer.rules.math_inline = renderInlineMath
md.renderer.rules.math_block = renderBlockMath

// Render a literal `<br>` as an actual line break, while keeping every other
// raw HTML tag escaped. With `html: false` the parser leaves `<br>` inside a
// `text` token, so the default text renderer escapes it to `&lt;br&gt;`. The
// editor emits `<br>` as the GFM line break inside a table cell (it cannot hold
// a second paragraph); the viewer must show it as a break, not as text.
//
// This is the only *inline* raw-HTML construct we render (the only block one is
// `<details>`, below). `<br>` is inert — no script, no attributes, no event
// handlers — so allowing it does not relax R6. We match
// `<br>`, `<br/>`, `<br />` (any inner spacing) case-insensitively; anything
// else, including `<br onload=…>` or any tag with attributes, stays escaped.
const BR_LITERAL = /<br\s*\/?>/i // non-global: `.split` still splits on every match
const defaultTextRule =
  md.renderer.rules.text ??
  ((tokens, idx, _options, _env, self) => self.renderToken(tokens, idx, _options))
md.renderer.rules.text = (tokens, idx, options, env, self) => {
  const content = tokens[idx]?.content ?? ''
  if (!BR_LITERAL.test(content)) {
    return defaultTextRule(tokens, idx, options, env, self)
  }
  // Split on the <br> literal, HTML-escape each segment, rejoin with real <br>.
  return content
    .split(BR_LITERAL)
    .map((segment) => md.utils.escapeHtml(segment))
    .join('<br>')
}

// Collapsible `<details>` / `<summary>` blocks. The allow-list lives in
// lib/details.ts. With `html: false` those tag lines would otherwise merge
// into a paragraph and escape, so a block rule claims them first and emits
// tokens whose HTML we build ourselves: only `open` and a validated `name`
// reach the output, and the summary text is always escaped (R6). The Markdown
// between an opening and a closing line renders as usual.
//
// A tag that doesn't pair up stays visible as escaped text, so an author's
// mistake shows instead of silently folding away the rest of the page. Pairs
// must open and close inside the same container (top level, one list item, one
// blockquote), which keeps the emitted HTML well nested.
function detailsBlock(
  state: StateBlock,
  startLine: number,
  endLine: number,
  silent: boolean,
): boolean {
  const run = scanDetailsRun(state, startLine, endLine)
  if (!run) return false
  if (silent) return true
  const rawLines = run.raw.split('\n')
  let line = 0
  for (const entry of run.lines) {
    const span = entry.kind === 'open' && entry.summary !== null ? 2 : 1
    const token = state.push(entry.kind === 'open' ? 'details_open' : 'details_close', '', 0)
    token.block = true
    token.meta = entry
    token.content = rawLines.slice(line, line + span).join('\n')
    token.map = [startLine + line, startLine + line + span]
    line += span
  }
  state.line = run.nextLine
  return true
}

// Pair `details_open` / `details_close` tokens; turn any leftover into a plain
// paragraph of its source text, which the inline pass then escapes.
type CoreState = Parameters<Parameters<Inst['core']['ruler']['after']>[2]>[0]
type Token = CoreState['tokens'][number]

function pairDetails(state: CoreState): void {
  const tokens = state.tokens
  const unpaired = new Set<number>()
  const stack: number[] = []
  tokens.forEach((t, i) => {
    if (t.nesting === -1) {
      // Leaving a container: whatever opened inside it can no longer close.
      while (stack.length && (tokens[stack[stack.length - 1] ?? 0]?.level ?? 0) > t.level) {
        unpaired.add(stack.pop() ?? 0)
      }
    }
    if (t.type === 'details_open') stack.push(i)
    if (t.type === 'details_close') {
      const top = stack[stack.length - 1]
      if (top !== undefined && tokens[top]?.level === t.level) stack.pop()
      else unpaired.add(i)
    }
  })
  for (const i of stack) unpaired.add(i)
  if (unpaired.size === 0) return

  const out: Token[] = []
  tokens.forEach((t, i) => {
    if (!unpaired.has(i)) {
      out.push(t)
      return
    }
    const open = new state.Token('paragraph_open', 'p', 1)
    const inline = new state.Token('inline', '', 0)
    const close = new state.Token('paragraph_close', 'p', -1)
    open.block = close.block = true
    open.map = t.map
    open.level = close.level = t.level
    inline.level = t.level + 1
    inline.content = t.content
    inline.map = t.map
    inline.children = []
    out.push(open, inline, close)
  })
  state.tokens = out
}

md.block.ruler.before('html_block', 'details_block', detailsBlock, {
  alt: ['paragraph', 'reference', 'blockquote', 'list'],
})
md.core.ruler.after('block', 'details_pair', pairDetails)
md.renderer.rules.details_open = (tokens, idx) => {
  const entry = tokens[idx]?.meta as DetailsLine | undefined
  if (entry?.kind !== 'open') return ''
  const open = entry.open ? ' open' : ''
  // `name` already matched [A-Za-z0-9_-]+; escape anyway as belt and braces.
  const name = entry.name !== null ? ` name="${md.utils.escapeHtml(entry.name)}"` : ''
  const summary =
    entry.summary !== null ? `<summary>${md.utils.escapeHtml(entry.summary)}</summary>\n` : ''
  return `<details${open}${name}>\n${summary}`
}
md.renderer.rules.details_close = () => '</details>\n'

const ASSET_BASE = '/api/v1/assets'

function isAbsolute(url: string): boolean {
  return /^([a-z][a-z0-9+.-]*:)?\/\//i.test(url) || url.startsWith('/') || url.startsWith('data:')
}

export function resolveAssetUrl(
  src: string,
  pagePath: string,
  sourceId?: string,
  watchedLabel?: string,
): string {
  // A true external/absolute URL (scheme, `//authority`, or `data:`) passes
  // through untouched. A leading-slash *path* (`/diagrams/x.svg`), however, is
  // repo-root-relative wiki content, not origin-relative — resolveRepoPath
  // roots it below. Anchors pass through.
  if (src.startsWith('#')) return src
  if (isAbsolute(src) && !looksLikeRootRelativePageLink(src)) return src
  // References include the sidecar prefix (e.g. ".saml.md/photo.png").
  // Resolve relative to the page's parent directory (or the repo root, if the
  // src is leading-slash).
  const resolved = resolveRepoPath(src, pagePath)
  if (watchedLabel) {
    return `/api/v1/watch/${encodeURIComponent(watchedLabel)}/assets/${resolved}`
  }
  if (sourceId) {
    return `/api/v1/sources/${sourceId}/assets/${resolved}`
  }
  return `${ASSET_BASE}/pages/${resolved}`
}

interface RenderEnv {
  pagePath?: string
  sourceId?: string
  watchedLabel?: string
}

// Resolve a relative path (`../foo/bar`, `./baz`, `sib`) against the parent
// directory of `pagePath`, returning the repo-root-relative result. Shared by
// asset and page-link resolution — the walk is identical, only the URL prefix
// differs.
//
// A leading `/` makes `rel` repo-root-relative (the GitHub/GitLab wiki
// convention: `/devops/foo` means "from the root of this repo", not "from the
// site origin"). In that case the walk starts from the repo root rather than
// the page's parent directory.
function resolveRepoPath(rel: string, pagePath: string): string {
  const parts = pagePath.split('/').filter(Boolean)
  const base = rel.startsWith('/') ? [] : parts.slice(0, -1) // root, or parent directory
  const out = [...base]
  for (const s of rel.split('/')) {
    if (s === '' || s === '.') continue
    if (s === '..') {
      out.pop()
      continue
    }
    out.push(s)
  }
  return out.join('/')
}

// Rewrite a relative link to another wiki page (`../foo/bar.md`) into the
// in-app route for that page, so the click-interceptor in router.ts routes it
// through Vue Router (document-only navigation) instead of a full-page reload.
//
// This is a *render-time only* rewrite: the stored markdown keeps the plain
// relative `.md` path, which is what GitHub/GitLab/Gitea resolve to the sibling
// file and what round-trips byte-identically (R1). Only the painted <a href>
// becomes an app route.
//
// The href may carry a trailing `#anchor` and/or `?query`; both are preserved
// so a link like `foo.md#section` lands on the right route + hash.
function resolvePageUrl(
  href: string,
  pagePath: string,
  sourceId?: string,
  watchedLabel?: string,
): string {
  const hashIdx = href.indexOf('#')
  const hash = hashIdx >= 0 ? href.slice(hashIdx) : ''
  const beforeHash = hashIdx >= 0 ? href.slice(0, hashIdx) : href
  const queryIdx = beforeHash.indexOf('?')
  const query = queryIdx >= 0 ? beforeHash.slice(queryIdx) : ''
  const pathPart = queryIdx >= 0 ? beforeHash.slice(0, queryIdx) : beforeHash

  const resolved = resolveRepoPath(pathPart.replace(/\.md$/i, ''), pagePath)
  if (watchedLabel) {
    return `/watch/${encodeURIComponent(watchedLabel)}/${resolved}${query}${hash}`
  }
  // sourceId is present for source pages; when neither is set we can't build a
  // route, so callers must gate on that (see isPageLink use in link_open).
  return `/source/${sourceId}/${resolved}${query}${hash}`
}

// A relative link is a wiki-page link when it targets a `.md` file (the shape
// the editor emits and the shape forges resolve). Absolute URLs, anchors,
// mailto:, and asset links are handled elsewhere.
function looksLikePageLink(href: string): boolean {
  if (isAbsolute(href) || href.startsWith('#') || href.startsWith('mailto:')) return false
  const pathPart = href.split('#')[0]?.split('?')[0] ?? ''
  return /\.md$/i.test(pathPart)
}

// App-route prefixes that the renderer itself emits (`/source/…`, `/watch/…`,
// their editor/media variants) and Libreta's own chrome (`/search`, `/-/…`).
// A leading-slash href already in one of these shapes is a formed in-app route,
// not repo content, so it must not be re-resolved as a repo-root path (that
// would double-prefix it). These never collide with real wiki paths.
const APP_ROUTE_PREFIXES = [
  '/source/',
  '/watch/',
  '/edit-source/',
  '/edit-watch/',
  '/pdf-source/',
  '/pdf-watch/',
  '/text-source/',
  '/text-watch/',
  '/html-source/',
  '/html-watch/',
  '/img-source/',
  '/img-watch/',
  '/video-source/',
  '/video-watch/',
  '/ebook-source/',
  '/ebook-watch/',
  '/search',
  '/-/',
]

// A leading-slash href with no scheme and no `//` authority is a
// repo-root-relative wiki path (the GitHub/GitLab wiki convention), not a
// browser origin-relative path. It resolves from the current repo's root, so
// when we know the source/watch we can route it into the SPA rather than
// letting the browser hit the site origin (which 404s). Protocol-relative
// `//host/…` URLs stay external, and already-formed app routes pass through
// untouched.
function looksLikeRootRelativePageLink(href: string): boolean {
  if (!href.startsWith('/') || href.startsWith('//')) return false
  return !APP_ROUTE_PREFIXES.some((p) => href.startsWith(p))
}

// Extensions we treat as "asset" downloads when they appear in a relative
// link href. Everything else is assumed to be either an external URL (handled
// in resolveAssetUrl), an in-app route (`/source/...`, `/watch/...`), or a
// same-page anchor.
const ASSET_LINK_EXTS = new Set([
  '.pdf',
  '.zip',
  '.tar',
  '.gz',
  '.bz2',
  '.7z',
  '.rar',
  '.png',
  '.jpg',
  '.jpeg',
  '.gif',
  '.svg',
  '.webp',
  '.ico',
  '.bmp',
  '.avif',
  '.heic',
  '.heif',
  '.tif',
  '.tiff',
  '.mp4',
  '.webm',
  '.mp3',
  '.ogg',
  '.wav',
  '.flac',
  '.mov',
  '.csv',
  '.tsv',
  '.xlsx',
  '.xls',
  '.ods',
  '.docx',
  '.doc',
  '.odt',
  '.pptx',
  '.ppt',
  '.odp',
  '.txt',
  '.json',
  '.xml',
  '.yaml',
  '.yml',
  '.toml',
  '.epub',
  '.mobi',
  '.pkg',
  '.dmg',
  '.iso',
  '.deb',
  '.rpm',
  '.exe',
  '.msi',
])

function looksLikeAssetHref(href: string): boolean {
  // A root-relative path (`/diagrams/x.svg`) is repo content, so it can be an
  // asset link — don't let the leading slash make isAbsolute() reject it. Only
  // a *true* external/absolute URL (scheme, `//authority`, `data:`) is exempt.
  if (isAbsolute(href) && !looksLikeRootRelativePageLink(href)) return false
  if (href.startsWith('#') || href.startsWith('mailto:')) return false
  const stripped = href.split('#')[0]?.split('?')[0] ?? ''
  const dot = stripped.lastIndexOf('.')
  if (dot < 0) return false
  return ASSET_LINK_EXTS.has(stripped.slice(dot).toLowerCase())
}

function patchRenderer(): void {
  // Mermaid fence blocks: emit <pre class="mermaid"> so the mermaid library
  // picks them up and replaces them with rendered SVG diagrams in view mode.
  const defaultFence: RenderRule =
    md.renderer.rules.fence ??
    ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
  md.renderer.rules.fence = (tokens, idx, options, env, self) => {
    const token = tokens[idx]
    if (token && token.info.trim() === 'mermaid') {
      // R6: must HTML-escape user content before injecting raw HTML — mermaid
      // re-reads `textContent` so the diagram still renders correctly.
      return `<pre class="mermaid">${md.utils.escapeHtml(token.content)}</pre>\n`
    }
    return defaultFence(tokens, idx, options, env, self)
  }

  const defaultImage: RenderRule =
    md.renderer.rules.image ??
    ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

  const imageRule: RenderRule = (tokens, idx, options, env, self) => {
    const token = tokens[idx]
    if (token) {
      const srcIdx = token.attrIndex('src')
      const attr = token.attrs?.[srcIdx]
      if (srcIdx >= 0 && attr) {
        const e = env as RenderEnv
        attr[1] = resolveAssetUrl(attr[1], e.pagePath ?? '', e.sourceId, e.watchedLabel)
      }
    }
    return defaultImage(tokens, idx, options, env, self)
  }
  md.renderer.rules.image = imageRule

  const fallbackLinkOpen: RenderRule = (tokens, idx, options, _env, self) =>
    self.renderToken(tokens, idx, options)
  const defaultLinkOpen: RenderRule = md.renderer.rules.link_open ?? fallbackLinkOpen

  function isExternalUrl(href: string): boolean {
    return /^https?:\/\//i.test(href)
  }

  const linkOpenRule: RenderRule = (tokens, idx, options, env, self) => {
    const token = tokens[idx]
    if (token) {
      const hrefIdx = token.attrIndex('href')
      const attr = token.attrs?.[hrefIdx]
      if (hrefIdx >= 0 && attr) {
        const e = env as RenderEnv
        if (looksLikePageLink(attr[1]) && (e.sourceId || e.watchedLabel)) {
          // Relative link to a sibling wiki page → in-app route, so navigation
          // stays inside the SPA (see resolvePageUrl). Stored markdown is
          // untouched; this only affects the rendered <a href>.
          attr[1] = resolvePageUrl(attr[1], e.pagePath ?? '', e.sourceId, e.watchedLabel)
        } else if (
          looksLikeRootRelativePageLink(attr[1]) &&
          !looksLikeAssetHref(attr[1]) &&
          (e.sourceId || e.watchedLabel)
        ) {
          // Repo-root-relative wiki link (`/devops/foo`) → in-app route within
          // the current source/watch. resolvePageUrl resolves it from the repo
          // root (leading slash), strips any `.md`, and preserves `#anchor` /
          // `?query`. Render-time only; stored markdown keeps the plain path.
          attr[1] = resolvePageUrl(attr[1], e.pagePath ?? '', e.sourceId, e.watchedLabel)
        } else if (looksLikeAssetHref(attr[1])) {
          attr[1] = resolveAssetUrl(attr[1], e.pagePath ?? '', e.sourceId, e.watchedLabel)
        } else if (isExternalUrl(attr[1])) {
          token.attrSet('target', '_blank')
          token.attrSet('rel', 'noopener noreferrer')
        }
      }
    }
    return defaultLinkOpen(tokens, idx, options, env, self)
  }
  md.renderer.rules.link_open = linkOpenRule
}

patchRenderer()

export function renderMarkdown(
  source: string,
  pagePath = '',
  sourceId?: string,
  watchedLabel?: string,
): string {
  return md.render(source, { pagePath, sourceId, watchedLabel })
}

export async function renderMermaidIn(container: HTMLElement): Promise<void> {
  const elements = container.querySelectorAll<HTMLElement>('.mermaid')
  if (elements.length > 0) {
    await mermaid.run({ nodes: Array.from(elements) })
  }
}
