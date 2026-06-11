import { describe, it, expect } from 'vitest'
import { renderMarkdown } from '@/markdown'

describe('renderMarkdown', () => {
  it('renders headings with stable slug ids', () => {
    const out = renderMarkdown('# Hello')
    expect(out).toMatch(/<h1 id="hello"[^>]*>Hello<\/h1>/)
  })

  it('renders GFM tables', () => {
    const out = renderMarkdown('| a | b |\n|---|---|\n| 1 | 2 |')
    expect(out).toContain('<table>')
    expect(out).toContain('<th>a</th>')
  })

  it('strips raw HTML (P4/R6)', () => {
    const out = renderMarkdown('<script>alert(1)</script>')
    expect(out).not.toContain('<script>')
  })

  it('renders a literal <br> in a table cell as a line break', () => {
    const out = renderMarkdown('| A | B |\n| --- | --- |\n| RAM | 32 GB<br>16 GB Crucial |')
    expect(out).toContain('32 GB<br>16 GB Crucial')
    expect(out).not.toContain('&lt;br&gt;')
  })

  it('renders <br/> and <br /> variants too', () => {
    const out = renderMarkdown('a<br/>b<br />c')
    expect(out).toContain('a<br>b<br>c')
  })

  it('still escapes other raw HTML even next to a <br>', () => {
    // The <br> is rendered, but a sibling tag with attributes must stay escaped
    // so the narrow <br> allowance does not become a raw-HTML hole (R6).
    const out = renderMarkdown('x<br><b onmouseover="evil()">y</b>')
    expect(out).toContain('x<br>')
    expect(out).not.toContain('<b onmouseover')
    expect(out).toContain('&lt;b onmouseover')
  })

  it('renders task lists', () => {
    const out = renderMarkdown('- [x] done\n- [ ] todo')
    expect(out).toContain('type="checkbox"')
  })

  it('highlights fenced code', () => {
    const out = renderMarkdown('```python\nx = 1\n```')
    expect(out).toContain('<pre class="hljs">')
    expect(out).toContain('language-python')
  })

  it('rewrites relative image URLs to the source assets endpoint', () => {
    const out = renderMarkdown('![alt](images/foo.png)', 'recipes/lasagna', 'work')
    expect(out).toContain('/api/v1/sources/work/assets/recipes/images/foo.png')
  })

  it('leaves absolute image URLs alone', () => {
    const out = renderMarkdown('![alt](https://example.com/x.png)', 'recipes/lasagna', 'work')
    expect(out).toContain('https://example.com/x.png')
  })

  it('resolves ../ in image URLs', () => {
    const out = renderMarkdown('![alt](../shared/x.png)', 'recipes/lasagna', 'work')
    expect(out).toContain('/api/v1/sources/work/assets/shared/x.png')
  })

  it('resolves images relative to the page parent dir', () => {
    // Page path devel/concepts/saml → saml is the slug, assets live in devel/concepts/
    const out = renderMarkdown('![alt](foo.png)', 'devel/concepts/saml', 'work')
    expect(out).toContain('/api/v1/sources/work/assets/devel/concepts/foo.png')
  })

  it('rewrites relative PDF/zip links through the source assets endpoint', () => {
    const out = renderMarkdown('[doc](report.pdf)', 'housing/espana/cancer', 'work')
    expect(out).toContain('href="/api/v1/sources/work/assets/housing/espana/report.pdf"')
  })

  it('leaves in-app route links alone', () => {
    const out = renderMarkdown('[other](/source/work/foo/bar)', 'housing/espana/cancer', 'work')
    expect(out).toContain('href="/source/work/foo/bar"')
    expect(out).not.toContain('/assets/')
  })

  it('leaves anchor and external links alone', () => {
    const out = renderMarkdown('[a](#x) [b](https://x.com/y.pdf)', 'foo')
    expect(out).toContain('href="#x"')
    expect(out).toContain('href="https://x.com/y.pdf"')
  })

  it('renders inline math', () => {
    const out = renderMarkdown('Energy $E = mc^2$ is iconic.')
    expect(out).toContain('class="katex"')
    expect(out).toContain('mathnormal') // KaTeX glyph class
  })

  it('renders block math', () => {
    const out = renderMarkdown('$$\n\\sum_{i=0}^{n} i\n$$')
    expect(out).toContain('math-block')
    expect(out).toContain('katex')
  })

  it('does not catch dollar amounts', () => {
    const out = renderMarkdown('It costs $5 and $10.')
    expect(out).not.toContain('katex')
  })
})
