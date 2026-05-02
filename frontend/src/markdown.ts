import MarkdownIt from 'markdown-it'
import taskLists from 'markdown-it-task-lists'
import hljs from 'highlight.js'

const md = new MarkdownIt({
  html: false, // P4/R6 — strip raw HTML at render. Save-side stripping comes with M2.
  linkify: true,
  typographer: false,
  breaks: false,
  highlight(str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang, ignoreIllegals: true }).value
      } catch {
        /* fall through */
      }
    }
    return ''
  },
}).use(taskLists, { enabled: false, label: false })

const ASSET_BASE = '/api/v1/assets'

function isAbsolute(url: string): boolean {
  return /^([a-z][a-z0-9+.-]*:)?\/\//i.test(url) || url.startsWith('/') || url.startsWith('data:')
}

function resolveAssetUrl(src: string, pagePath: string): string {
  if (isAbsolute(src) || src.startsWith('#')) return src
  // pagePath is the API path (e.g. "recipes/lasagna" or "index"). Drop the
  // last segment to get the directory, then resolve `src` against it.
  const parts = pagePath.split('/').filter(Boolean)
  const dir = parts.slice(0, -1)
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
  // pages live under content/pages/. Authors typically reference assets
  // either alongside the page (resolved above) or at the wiki root via "/".
  // We always serve from content_dir, so prefix with `pages/`.
  return `${ASSET_BASE}/pages/${out.join('/')}`
}

function patchRenderer(): void {
  const defaultImage =
    md.renderer.rules.image ??
    ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

  md.renderer.rules.image = (tokens, idx, options, env, self) => {
    const token = tokens[idx]
    if (token) {
      const srcIdx = token.attrIndex('src')
      const attr = token.attrs?.[srcIdx]
      if (srcIdx >= 0 && attr) {
        const pagePath = (env as { pagePath?: string }).pagePath ?? ''
        attr[1] = resolveAssetUrl(attr[1], pagePath)
      }
    }
    return defaultImage(tokens, idx, options, env, self)
  }
}

patchRenderer()

export function renderMarkdown(source: string, pagePath = ''): string {
  return md.render(source, { pagePath })
}
