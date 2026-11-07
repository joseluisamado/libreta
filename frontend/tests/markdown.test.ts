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

  it('adds a copy button and language label to fenced code', () => {
    const out = renderMarkdown('```python\nx = 1\n```')
    expect(out).toContain('class="code-copy"')
    expect(out).toContain('<span class="code-lang">python</span>')
  })

  it('adds a copy button to unlabelled code blocks (no language span)', () => {
    const out = renderMarkdown('```\nplain\n```')
    expect(out).toContain('class="code-copy"')
    expect(out).not.toContain('class="code-lang"')
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

  it('rewrites a relative .md page link to an in-app source route', () => {
    // Portable on-disk form `../fundamentals/caching.md`, rendered on a page in
    // interview/aws/storage → app route so clicks stay in the SPA.
    const out = renderMarkdown(
      '[caching](../fundamentals/caching.md)',
      'interview/aws/storage/s3.md',
      'work',
    )
    expect(out).toContain('href="/source/work/interview/aws/fundamentals/caching"')
    expect(out).not.toContain('.md"')
  })

  it('rewrites a same-directory .md page link', () => {
    const out = renderMarkdown('[iam](iam.md)', 'security/root.md', 'work')
    expect(out).toContain('href="/source/work/security/iam"')
  })

  it('preserves an anchor fragment on a page link', () => {
    const out = renderMarkdown('[sec](../ref/api.md#auth)', 'guide/setup.md', 'work')
    expect(out).toContain('href="/source/work/ref/api#auth"')
  })

  it('rewrites relative .md page links for watched folders', () => {
    const out = renderMarkdown('[sib](sibling.md)', 'notes/today.md', undefined, 'journal')
    expect(out).toContain('href="/watch/journal/notes/sibling"')
  })

  it('leaves .md links untouched when no source/watch context is known', () => {
    // Without a sourceId or watchedLabel there is no route to build; the plain
    // relative link is preserved rather than emitting a broken /source//… URL.
    const out = renderMarkdown('[x](foo.md)', 'top.md')
    expect(out).toContain('href="foo.md"')
    expect(out).not.toContain('/source/')
  })

  it('leaves absolute forge URLs (cross-repo) as external links', () => {
    const out = renderMarkdown(
      '[other repo](https://gitea.example.com/user/wiki/src/branch/main/page.md)',
      'a/b.md',
      'work',
    )
    expect(out).toContain('href="https://gitea.example.com/user/wiki/src/branch/main/page.md"')
    expect(out).toContain('target="_blank"')
    expect(out).not.toContain('/source/work/')
  })

  it('rewrites a repo-root-relative page link to an in-app source route', () => {
    // `/devops/platform/governance/ownership-models` means "from this repo's
    // root", not the site origin. It resolves within the current source.
    const out = renderMarkdown(
      '[ownership](/devops/platform/governance/ownership-models)',
      'faang/story-triggers-devops.md',
      'work',
    )
    expect(out).toContain('href="/source/work/devops/platform/governance/ownership-models"')
  })

  it('rewrites a repo-root-relative page link for watched folders', () => {
    const out = renderMarkdown(
      '[ownership](/devops/platform/governance/ownership-models)',
      'faang/story-triggers-devops.md',
      undefined,
      'libreta-mirror',
    )
    expect(out).toContain(
      'href="/watch/libreta-mirror/devops/platform/governance/ownership-models"',
    )
  })

  it('preserves an anchor on a repo-root-relative page link', () => {
    const out = renderMarkdown('[grid](/faang/interview#know-your-projects-cold)', 'a/b.md', 'work')
    expect(out).toContain('href="/source/work/faang/interview#know-your-projects-cold"')
  })

  it('strips a trailing .md on a repo-root-relative page link', () => {
    const out = renderMarkdown('[x](/devops/foo.md)', 'a/b.md', 'work')
    expect(out).toContain('href="/source/work/devops/foo"')
    expect(out).not.toContain('.md"')
  })

  it('routes a repo-root-relative asset through the assets endpoint', () => {
    const out = renderMarkdown('[dia](/diagrams/net.svg)', 'a/b.md', 'work')
    expect(out).toContain('href="/api/v1/sources/work/assets/diagrams/net.svg"')
  })

  it('resolves a repo-root-relative image from the repo root', () => {
    const out = renderMarkdown('![alt](/shared/logo.png)', 'deep/nested/page.md', 'work')
    expect(out).toContain('/api/v1/sources/work/assets/shared/logo.png')
  })

  it('leaves an already-formed in-app route untouched (no double-prefix)', () => {
    const out = renderMarkdown('[other](/source/work/foo/bar)', 'a/b.md', 'work')
    expect(out).toContain('href="/source/work/foo/bar"')
    expect(out).not.toContain('/source/work/source/')
  })

  it('leaves a repo-root-relative link untouched without source/watch context', () => {
    const out = renderMarkdown('[x](/devops/foo)', 'top.md')
    expect(out).toContain('href="/devops/foo"')
    expect(out).not.toContain('/source/')
    expect(out).not.toContain('/watch/')
  })

  it('leaves a protocol-relative URL as external', () => {
    const out = renderMarkdown('[x](//cdn.example.com/lib.js)', 'a/b.md', 'work')
    expect(out).toContain('href="//cdn.example.com/lib.js"')
    expect(out).not.toContain('/source/work/')
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

describe('renderMarkdown — <details> / <summary>', () => {
  const ACCORDION = [
    '<details name="faq" open>',
    '<summary>First question</summary>',
    '',
    '![one](.setup.md/one.png)',
    '',
    '</details>',
    '',
    '<details name="faq">',
    '<summary>Second question</summary>',
    '',
    '![two](.setup.md/two.png)',
    '',
    '</details>',
  ].join('\n')

  it('renders the shared-name accordion as two details blocks', () => {
    const out = renderMarkdown(ACCORDION, 'guides/setup', 'work')
    expect(out).toContain('<details open name="faq">\n<summary>First question</summary>')
    expect(out).toContain('<details name="faq">\n<summary>Second question</summary>')
    expect(out.match(/<\/details>/g)).toHaveLength(2)
    expect(out).not.toContain('&lt;details')
    // Never wrapped in a paragraph (invalid HTML the browser would have to repair).
    expect(out).not.toMatch(/<p>\s*<(\/)?details/)
  })

  it('keeps rendering Markdown inside the block', () => {
    const out = renderMarkdown(ACCORDION, 'guides/setup', 'work')
    expect(out).toContain('<img src="/api/v1/sources/work/assets/guides/.setup.md/one.png"')
    const list = renderMarkdown('<details>\n\n- **bold** item\n\n</details>')
    expect(list).toMatch(/<details>\n<ul>\n<li><strong>bold<\/strong> item<\/li>/)
  })

  it('accepts open and name in either order, and no attributes at all', () => {
    expect(renderMarkdown('<details open name="a-1_b">\n\nx\n\n</details>')).toContain(
      '<details open name="a-1_b">',
    )
    expect(renderMarkdown('<details name="a-1_b" open>\n\nx\n\n</details>')).toContain(
      '<details open name="a-1_b">',
    )
    expect(renderMarkdown('<details name="a">\n\nx\n\n</details>')).toContain('<details name="a">')
    expect(renderMarkdown('<details>\n\nx\n\n</details>')).toContain('<details>\n<p>x</p>')
  })

  it('escapes the summary text', () => {
    const out = renderMarkdown(
      '<details>\n<summary><b onclick="x()">X</b> & Y</summary>\n\n</details>',
    )
    expect(out).toContain('<summary>&lt;b onclick=&quot;x()&quot;&gt;X&lt;/b&gt; &amp; Y</summary>')
    expect(out).not.toContain('<b ')
  })

  it.each([
    ['an event handler', '<details onclick="evil()">'],
    ['a style attribute', '<details style="color:red">'],
    ['a class attribute', '<details class="x">'],
    ['an invalid name value', '<details name="a b">'],
    ['a quote-breaking name', '<details name="a"onclick="x">'],
    ['an unquoted name', '<details name=a>'],
    ['a valued open', '<details open="open">'],
    ['a repeated attribute', '<details open open>'],
  ])('keeps <details> with %s escaped', (_label, tag) => {
    const out = renderMarkdown(`${tag}\n\nbody\n\n</details>`)
    expect(out).not.toMatch(/<details[\s>]/)
    expect(out).toContain('&lt;details')
  })

  it('rejects the whole run when any line in it is not allow-listed', () => {
    const out = renderMarkdown(
      '<details>\n<summary>S</summary>\n<img src=x onerror="evil()">\n\n</details>',
    )
    expect(out).not.toMatch(/<details[\s>]/)
    expect(out).not.toContain('<img src=x')
  })

  it('keeps summary with attributes, or summary not right after <details>, escaped', () => {
    const attr = renderMarkdown('<details>\n<summary onclick="x()">S</summary>\n\n</details>')
    expect(attr).not.toContain('<summary')
    const stray = renderMarkdown('<summary>S</summary>')
    expect(stray).toContain('&lt;summary&gt;')
  })

  it('keeps <details> inside inline text escaped', () => {
    const out = renderMarkdown('Click <details open> to see')
    expect(out).toContain('<p>Click &lt;details open&gt; to see</p>')
  })

  it('shows an orphan </details> as text', () => {
    const out = renderMarkdown('Para.\n\n</details>\n\nMore.')
    expect(out).toContain('<p>&lt;/details&gt;</p>')
    expect(out).not.toContain('</details>\n')
  })

  it('shows an unclosed <details> as text instead of folding the rest away', () => {
    const out = renderMarkdown('<details>\n<summary>S</summary>\n\nRest of the page.')
    expect(out).not.toMatch(/<details[\s>]/)
    expect(out).toContain('&lt;details&gt;')
    expect(out).toContain('<p>Rest of the page.</p>')
  })

  it('does not pair tags across containers', () => {
    const out = renderMarkdown('> <details>\n\n</details>')
    expect(out).not.toMatch(/<details[\s>]/)
    expect(out).not.toContain('</details>\n')
  })

  it('pairs tags inside a blockquote, and nested blocks', () => {
    const quoted = renderMarkdown(
      '> <details open>\n> <summary>Q</summary>\n>\n> body\n>\n> </details>',
    )
    expect(quoted).toMatch(
      /<blockquote>\n<details open>\n<summary>Q<\/summary>\n<p>body<\/p>\n<\/details>\n<\/blockquote>/,
    )
    const nested = renderMarkdown('<details>\n\n<details>\n\ninner\n\n</details>\n\n</details>')
    expect(nested.match(/<details>/g)).toHaveLength(2)
    expect(nested.match(/<\/details>/g)).toHaveLength(2)
  })

  it('treats an indented tag line as code', () => {
    const out = renderMarkdown('    <details>\n\n</details>')
    expect(out).toContain('&lt;details&gt;')
  })
})
