import { describe, expect, it } from 'vitest'
import { sanitizeHtmlFile } from '@/lib/html'

// R6: server-rendered HTML never executes user-supplied JS. These tests are
// the contract for the HTML-file viewer/thumbnail sanitizer. Treat them like
// a security boundary — do not weaken to make a feature pass.

describe('sanitizeHtmlFile — R6 (no executable content)', () => {
  it('removes <script> elements and their contents', () => {
    const out = sanitizeHtmlFile('<p>hi</p><script>alert(1)</script>')
    expect(out).toContain('hi')
    expect(out.toLowerCase()).not.toContain('<script')
    expect(out).not.toContain('alert(1)')
  })

  it('strips inline event handlers', () => {
    const out = sanitizeHtmlFile('<img src="x" onerror="alert(1)">')
    expect(out.toLowerCase()).not.toContain('onerror')
    expect(out).not.toContain('alert(1)')
  })

  it('strips javascript: URLs', () => {
    const out = sanitizeHtmlFile('<a href="javascript:alert(1)">x</a>')
    expect(out.toLowerCase()).not.toContain('javascript:')
  })

  it('removes <iframe>, <object>, <embed>', () => {
    const out = sanitizeHtmlFile(
      '<iframe src="evil"></iframe><object data="x"></object><embed src="y">',
    )
    expect(out.toLowerCase()).not.toContain('<iframe')
    expect(out.toLowerCase()).not.toContain('<object')
    expect(out.toLowerCase()).not.toContain('<embed')
  })

  it('keeps a stylesheet <link> but drops other rels (preload/import)', () => {
    const ctx = { pagePath: 'd/index.html', sourceId: 'club-x' }
    const out = sanitizeHtmlFile(
      '<link rel="stylesheet" href="a.css"><link rel="preload" href="b.js" as="script"><link rel="import" href="c.html">',
      ctx,
    )
    expect(out).toContain('a.css')
    expect(out).not.toContain('b.js')
    expect(out).not.toContain('c.html')
  })

  it('keeps inline <style> (CSS is content, not code)', () => {
    const out = sanitizeHtmlFile('<style>.q{color:red}</style><p class="q">x</p>')
    expect(out).toContain('<style>')
    expect(out).toContain('.q{color:red}')
  })

  it('keeps benign markup, text, and styling', () => {
    const out = sanitizeHtmlFile('<h1>Title</h1><p class="lead" style="color:red">body</p>')
    expect(out).toContain('<h1>Title</h1>')
    expect(out).toContain('body')
    expect(out).toContain('class="lead"')
  })
})

describe('sanitizeHtmlFile — artifact rerooting', () => {
  const ctx = { pagePath: 'sample tests/index.html', sourceId: 'club-x' }

  it('reroots relative img src to the source assets endpoint', () => {
    const out = sanitizeHtmlFile('<img src="artifacts/q1.png">', ctx)
    expect(out).toContain('/api/v1/sources/club-x/assets/sample%20tests/artifacts/q1.png')
  })

  it('reroots relative stylesheet href', () => {
    const out = sanitizeHtmlFile('<link rel="stylesheet" href="style.css">', ctx)
    expect(out).toContain('/api/v1/sources/club-x/assets/sample%20tests/style.css')
  })

  it('resolves .. segments against the file directory', () => {
    const out = sanitizeHtmlFile('<img src="../shared/logo.png">', ctx)
    expect(out).toContain('/api/v1/sources/club-x/assets/shared/logo.png')
  })

  it('leaves absolute and data URLs untouched', () => {
    const out = sanitizeHtmlFile(
      '<img src="https://cdn.example/x.png"><img src="data:image/png;base64,AAAA">',
      ctx,
    )
    expect(out).toContain('https://cdn.example/x.png')
    expect(out).toContain('data:image/png;base64,AAAA')
  })

  it('uses the watched endpoint when given a label', () => {
    const out = sanitizeHtmlFile('<img src="a.png">', {
      pagePath: 'd/index.html',
      watchedLabel: 'My Notes',
    })
    expect(out).toContain('/api/v1/watch/My%20Notes/assets/d/a.png')
  })
})
