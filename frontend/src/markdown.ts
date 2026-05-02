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
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github.css'

const md = new MarkdownIt({
  html: false, // P4/R6 — strip raw HTML at render. Save-side stripping comes with M2.
  linkify: true,
  typographer: false,
  breaks: false,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        const html = hljs.highlight(str, { language: lang, ignoreIllegals: true }).value
        return `<pre class="hljs"><code class="hljs language-${lang}" data-lang="${lang}">${html}</code></pre>`
      } catch {
        /* fall through */
      }
    }
    const escaped = str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    return `<pre class="hljs"><code class="hljs">${escaped}</code></pre>`
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

const ASSET_BASE = '/api/v1/assets'

function isAbsolute(url: string): boolean {
  return /^([a-z][a-z0-9+.-]*:)?\/\//i.test(url) || url.startsWith('/') || url.startsWith('data:')
}

function resolveAssetUrl(src: string, pagePath: string, isIndex: boolean): string {
  if (isAbsolute(src) || src.startsWith('#')) return src
  // pagePath is the API path (e.g. "recipes/lasagna" or "devel/concepts/saml").
  // Determine the directory the page is stored in:
  //   - leaf page  (foo/bar.md):    drop last segment → "foo/"
  //   - index page (foo/bar/index.md): keep all segments → "foo/bar/"
  const parts = pagePath.split('/').filter(Boolean)
  const dir = isIndex ? [...parts] : parts.slice(0, -1)
  const segments = src.split('/')
  const out = [...dir]
  for (const s of segments) {
    if (s === '' || s === '.') continue
    if (s === '..') {
      out.pop()
      continue
    }
    out.push(s)
  }
  return `${ASSET_BASE}/pages/${out.join('/')}`
}

interface RenderEnv {
  pagePath?: string
  isIndex?: boolean
}

// Extensions we treat as "asset" downloads when they appear in a relative
// link href. Everything else is assumed to be either an external URL (handled
// in resolveAssetUrl), a route into the wiki (`/w/...`), or a same-page
// anchor.
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
  if (isAbsolute(href) || href.startsWith('#') || href.startsWith('mailto:')) return false
  const stripped = href.split('#')[0]?.split('?')[0] ?? ''
  const dot = stripped.lastIndexOf('.')
  if (dot < 0) return false
  return ASSET_LINK_EXTS.has(stripped.slice(dot).toLowerCase())
}

function patchRenderer(): void {
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
        attr[1] = resolveAssetUrl(attr[1], e.pagePath ?? '', e.isIndex ?? false)
      }
    }
    return defaultImage(tokens, idx, options, env, self)
  }
  md.renderer.rules.image = imageRule

  const fallbackLinkOpen: RenderRule = (tokens, idx, options, _env, self) =>
    self.renderToken(tokens, idx, options)
  const defaultLinkOpen: RenderRule = md.renderer.rules.link_open ?? fallbackLinkOpen

  const linkOpenRule: RenderRule = (tokens, idx, options, env, self) => {
    const token = tokens[idx]
    if (token) {
      const hrefIdx = token.attrIndex('href')
      const attr = token.attrs?.[hrefIdx]
      if (hrefIdx >= 0 && attr && looksLikeAssetHref(attr[1])) {
        const e = env as RenderEnv
        attr[1] = resolveAssetUrl(attr[1], e.pagePath ?? '', e.isIndex ?? false)
      }
    }
    return defaultLinkOpen(tokens, idx, options, env, self)
  }
  md.renderer.rules.link_open = linkOpenRule
}

patchRenderer()

export function renderMarkdown(source: string, pagePath = '', isIndex = false): string {
  return md.render(source, { pagePath, isIndex })
}
