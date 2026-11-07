import type MarkdownIt from 'markdown-it'

// The collapsible `<details>` / `<summary>` block: the one raw-HTML *block*
// construct Libreta interprets (the inline one is `<br>`, see markdown.ts). It
// is plain CommonMark raw HTML, not new syntax (P4), and forges like Gitea and
// GitHub render it natively, so pages that use it stay portable.
//
// The allow-list is exact. A recognised run is a CommonMark HTML block (from
// its first line to the next blank line) in which every line is one of:
//
//   <details>                       optionally with a bare `open` and/or
//                                   `name="[A-Za-z0-9_-]+"`, in any order,
//                                   once each
//   <details><summary>…</summary>   the same opener with its summary on the
//                                   same line (whitespace between allowed)
//   <summary>…</summary>            only directly after a `<details>` line
//                                   that has no summary yet
//   </details>                      one or more on a line, optionally
//                                   separated by whitespace; each closes one
//                                   level
//
// Any other line in the run (another tag, another attribute, an event handler)
// disqualifies the whole run, which then renders escaped as before (R6).
//
// The summary is never passed through. `renderSummary` rebuilds it from parsed
// pieces: text is HTML-escaped, and only bare, properly nested `<b>`,
// `<strong>`, `<i>`, `<em>` and `<code>` become tags (`<code>` content is
// literal text). Anything else in it — another tag, an attribute, an unclosed
// or mismatched tag — escapes the whole summary text instead.
//
// Both the viewer (markdown.ts) and the editor (extensions/DetailsMarkup.ts)
// scan with this module, so they always agree on what counts as a run.

type Inst = InstanceType<typeof MarkdownIt>
type StateBlock = Parameters<Parameters<Inst['block']['ruler']['before']>[2]>[0]

// One tag in a run. `line` is its line offset from the run's first line, and
// `span` the number of lines it covers (2 for an opener whose summary sits on
// the next line). `src` is that source text; closers on one line share a line
// and each carry just their own `</details>`.
export type DetailsTag =
  | {
      kind: 'open'
      open: boolean
      name: string | null
      summary: string | null
      line: number
      span: number
      src: string
    }
  | { kind: 'close'; line: number; span: 1; src: string }

export interface DetailsRun {
  tags: DetailsTag[]
  // The run's source lines (leading indentation and container markers such as
  // a blockquote's `> ` stripped), joined with `\n`.
  raw: string
  // First line after the run.
  nextLine: number
}

const OPEN_TAG = /^<details((?:\s+[^\s>]+)*)\s*>(?:\s*<summary>(.*)<\/summary>)?$/i
const OPEN_ATTR = /^(?:(open)|name="([A-Za-z0-9_-]+)")$/i
const SUMMARY_TAG = /^<summary>(.*)<\/summary>$/i
const CLOSE_LINE = /^<\/details\s*>(?:\s*<\/details\s*>)*$/i
const CLOSE_TAG = /<\/details\s*>/gi

function matchOpen(text: string, line: number): Extract<DetailsTag, { kind: 'open' }> | null {
  const m = OPEN_TAG.exec(text)
  if (!m) return null
  let open = false
  let name: string | null = null
  for (const attr of (m[1] ?? '').trim().split(/\s+/).filter(Boolean)) {
    const a = OPEN_ATTR.exec(attr)
    if (!a) return null
    if (a[1] !== undefined) {
      if (open) return null
      open = true
    } else {
      if (name !== null) return null
      name = a[2] ?? null
    }
  }
  return { kind: 'open', open, name, summary: m[2] ?? null, line, span: 1, src: text }
}

function matchClose(text: string, line: number): DetailsTag[] | null {
  if (!CLOSE_LINE.test(text)) return null
  return (text.match(CLOSE_TAG) ?? []).map((src) => ({ kind: 'close', line, span: 1, src }))
}

function lineText(state: StateBlock, line: number): string {
  const begin = (state.bMarks[line] ?? 0) + (state.tShift[line] ?? 0)
  return state.src.slice(begin, state.eMarks[line] ?? 0).trimEnd()
}

export function scanDetailsRun(
  state: StateBlock,
  startLine: number,
  endLine: number,
): DetailsRun | null {
  // Four or more columns of indentation is an indented code block.
  if ((state.sCount[startLine] ?? 0) - state.blkIndent >= 4) return null
  const tags: DetailsTag[] = []
  const raw: string[] = []
  let line = startLine
  for (; line < endLine; line++) {
    if (state.isEmpty(line)) break
    if (line > startLine && (state.sCount[line] ?? 0) < state.blkIndent) break
    const text = lineText(state, line)
    const offset = line - startLine
    const prev = tags[tags.length - 1]
    const summary = SUMMARY_TAG.exec(text)
    if (summary && prev?.kind === 'open' && prev.summary === null && prev.line === offset - 1) {
      prev.summary = summary[1] ?? ''
      prev.span = 2
      prev.src += '\n' + text
    } else {
      const parsed = matchClose(text, offset) ?? matchOpen(text, offset)
      if (!parsed) return null
      tags.push(...(Array.isArray(parsed) ? parsed : [parsed]))
    }
    raw.push(text)
  }
  if (tags.length === 0) return null
  return { tags, raw: raw.join('\n'), nextLine: line }
}

const SUMMARY_TAGS = new Set(['b', 'strong', 'i', 'em', 'code'])

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// The summary's inner HTML, safe to inject. A `<` starts a tag only when a
// letter, `/`, `!` or `?` follows (as in HTML); a lone `<` (as in `a < b`) is
// text.
export function renderSummary(content: string): string {
  const out: string[] = []
  const stack: string[] = []
  const tagStart = /<[A-Za-z/!?]/g
  let pos = 0
  while (pos < content.length) {
    tagStart.lastIndex = pos
    const hit = tagStart.exec(content)
    if (!hit) {
      out.push(escapeHtml(content.slice(pos)))
      break
    }
    out.push(escapeHtml(content.slice(pos, hit.index)))
    const tag = /^<(\/?)([A-Za-z]+)>/.exec(content.slice(hit.index))
    const name = tag?.[2]?.toLowerCase() ?? ''
    if (!tag || !SUMMARY_TAGS.has(name)) return escapeHtml(content)
    pos = hit.index + tag[0].length
    if (tag[1]) {
      if (stack.pop() !== name) return escapeHtml(content)
      out.push(`</${name}>`)
    } else if (name === 'code') {
      // Literal up to the matching close: no tags are recognised inside.
      const end = content.toLowerCase().indexOf('</code>', pos)
      if (end < 0) return escapeHtml(content)
      out.push(`<code>${escapeHtml(content.slice(pos, end))}</code>`)
      pos = end + '</code>'.length
    } else {
      stack.push(name)
      out.push(`<${name}>`)
    }
  }
  return stack.length === 0 ? out.join('') : escapeHtml(content)
}
