import type MarkdownIt from 'markdown-it'

// The collapsible `<details>` / `<summary>` block: the one raw-HTML *block*
// construct Libreta interprets (the inline one is `<br>`, see markdown.ts). It
// is plain CommonMark raw HTML, not new syntax (P4), and forges like Gitea and
// GitHub render it natively, so pages that use it stay portable.
//
// The allow-list is exact. A recognised run is a CommonMark HTML block (from
// its first line to the next blank line) in which every line is one of:
//
//   <details>                  optionally with a bare `open` and/or
//                              `name="[A-Za-z0-9_-]+"`, in any order, once each
//   <summary>text</summary>    only directly after a `<details>` line; the
//                              text is always HTML-escaped, never interpreted
//   </details>
//
// Any other line in the run (another tag, another attribute, an event handler)
// disqualifies the whole run, which then renders escaped as before (R6).
//
// Both the viewer (markdown.ts) and the editor (extensions/DetailsMarkup.ts)
// scan with this module, so they always agree on what counts as a run.

type Inst = InstanceType<typeof MarkdownIt>
type StateBlock = Parameters<Parameters<Inst['block']['ruler']['before']>[2]>[0]

export type DetailsLine =
  | { kind: 'open'; open: boolean; name: string | null; summary: string | null }
  | { kind: 'close' }

export interface DetailsRun {
  lines: DetailsLine[]
  // The run's source lines (leading indentation and container markers such as
  // a blockquote's `> ` stripped), joined with `\n`.
  raw: string
  // First line after the run.
  nextLine: number
}

const OPEN_TAG = /^<details((?:\s+[^\s>]+)*)\s*>$/i
const OPEN_ATTR = /^(?:(open)|name="([A-Za-z0-9_-]+)")$/i
const SUMMARY_TAG = /^<summary>(.*)<\/summary>$/i
const CLOSE_TAG = /^<\/details\s*>$/i

function matchOpen(line: string): Extract<DetailsLine, { kind: 'open' }> | null {
  const m = OPEN_TAG.exec(line)
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
  return { kind: 'open', open, name, summary: null }
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
  const lines: DetailsLine[] = []
  const raw: string[] = []
  let line = startLine
  for (; line < endLine; line++) {
    if (state.isEmpty(line)) break
    if (line > startLine && (state.sCount[line] ?? 0) < state.blkIndent) break
    const text = lineText(state, line)
    const prev = lines[lines.length - 1]
    const summary = SUMMARY_TAG.exec(text)
    if (summary && prev?.kind === 'open' && prev.summary === null) {
      prev.summary = summary[1] ?? ''
    } else {
      const parsed = CLOSE_TAG.test(text) ? ({ kind: 'close' } as const) : matchOpen(text)
      if (!parsed) return null
      lines.push(parsed)
    }
    raw.push(text)
  }
  if (lines.length === 0) return null
  return { lines, raw: raw.join('\n'), nextLine: line }
}
