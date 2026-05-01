# Libreta — Project Charter

## Vision

A self-hosted, single-user-first wiki that stores its content as plain markdown files in a git repository, rendered through a Confluence-quality web interface with a real WYSIWYG editor and proper diagrams.net integration.

Today's options force a choice: either you get markdown-on-disk + git versioning but a clunky editor (Wiki.js, Wikmd), or you get a great editor and integrated drawing tools but your content lives in a database (BookStack, Docmost). Libreta rejects that trade-off.

## Background

After surveying the self-hosted wiki landscape (Wiki.js, BookStack, Docmost, Wikmd, flatnotes, DokuWiki), no existing project simultaneously delivers:

- Markdown files as the canonical storage format
- Git-backed history as a first-class concern, not a sync afterthought
- A polished WYSIWYG editor
- Native, click-a-button diagrams.net integration
- Confluence-quality tables and rich content

Libreta fills that gap.

## Principles

These are decision rules, not aspirations. When a feature request conflicts with a principle, the principle wins; the feature is redesigned or dropped.

- **P1 — The filesystem is the source of truth.** User content lives as files in a git working tree. Indexes, caches, and derived state may live elsewhere, but must be fully regenerable from the filesystem alone.
- **P2 — Every save is a commit.** There is no "save without commit" code path on the server. Debouncing happens in the UI; the server-side save lifecycle always produces a commit.
- **P3 — The markdown round-trip is sacred.** Read → editor → save must be byte-identical on the fixture corpus. Any change that breaks this is a regression, regardless of test coverage elsewhere.
- **P4 — No custom markdown syntax.** CommonMark + GFM only. No proprietary directives, no `{% widget %}`, no `:::admonition`. Diagrams, callouts, and other rich content are expressed through standard markdown constructs (e.g. images, GitHub-flavoured callouts).
- **P5 — No reliance on public services at runtime.** The wiki must work fully offline. All required components (drawio, search, diagrams) ship with the stack.
- **P6 — Single-user-first.** v1 is designed for one author. Multi-user, auth, and ACLs are deliberately deferred until the single-user shape is solid (see `ROADMAP.md` M6).

## Goals

### Must have (v1.0)

- Pages stored as `.md` files on disk, organized in a hierarchy
- Every save is a git commit; full history visible in-app
- WYSIWYG editor with a markdown source mode
- diagrams.net integration: click a button, edit a diagram, save — all inline
- Image and arbitrary file uploads stored alongside content
- GitHub Flavored Markdown tables with an editing experience comparable to Confluence
- Mobile-friendly responsive UI
- One-command Docker Compose deployment
- Cross-platform (Linux/macOS/Windows via Docker)
- Single-user mode with the door left open for auth later

### Should have (v1.x)

- Full-text search
- Page templates
- Code blocks with syntax highlighting
- Mermaid diagrams (in addition to drawio)
- Callout/admonition blocks
- Page tree drag-and-drop reorganization

### Future (v2+)

- Multi-user with authentication (local + OIDC)
- Per-page or per-tree permissions
- Real-time collaborative editing
- Comments
- Export to PDF / static site
- Plugins / custom blocks

## Non-goals

- **Replacing Confluence as a corporate wiki.** Libreta is opinionated and lean. Approval workflows, dashboards, Jira integration, etc. are explicitly out of scope.
- **Being a public CMS.** Libreta is for private knowledge bases. Publishing public sites is a future consideration via static export.
- **Supporting wiki markup other than Markdown.** No MediaWiki syntax, no AsciiDoc, no reStructuredText.
- **Database-backed content.** SQLite may be used for indexes/cache, but the source of truth is always the filesystem.
- **Real-time collaboration in v1.** Single-author editing only initially.

## Functional requirements

| ID   | Requirement                                                | Priority |
| ---- | ---------------------------------------------------------- | -------- |
| F-01 | Pages stored as `.md` files with YAML frontmatter          | Must     |
| F-02 | Hierarchical page tree mapped to directory structure       | Must     |
| F-03 | Every save creates a git commit                            | Must     |
| F-04 | View history and diff between revisions in-app             | Must     |
| F-05 | WYSIWYG editor with markdown roundtrip                     | Must     |
| F-06 | Markdown source-mode editor with live preview              | Must     |
| F-07 | Embedded diagrams.net editor (self-hosted)                 | Must     |
| F-08 | Image upload (paste, drag-drop, file picker)               | Must     |
| F-09 | Arbitrary file attachment                                  | Must     |
| F-10 | GFM tables with WYSIWYG editing                            | Must     |
| F-11 | Code blocks with syntax highlighting                       | Should   |
| F-12 | Full-text search                                           | Should   |
| F-13 | Mobile-responsive UI                                       | Must     |
| F-14 | Dark/light theme                                           | Should   |
| F-15 | Wiki-style internal links (`[[Page Title]]`)               | Should   |
| F-16 | Optional sync with remote git (GitHub, Forgejo, self-host) | Should   |

## Non-functional requirements

- **Portability:** runs on any system with Docker Engine 24+. No native dependencies on the host.
- **Performance:** page loads under 200 ms on a Raspberry Pi 4. Search queries under 500 ms on a 1000-page corpus.
- **Footprint:** total memory usage under 512 MB at idle. Disk usage scales linearly with content.
- **Simplicity of deployment:** `docker compose up -d` and nothing else.
- **Data portability:** all content remains usable and editable without Libreta. A user can `git clone` the content repo and read it in any markdown viewer.
- **Backup-friendliness:** the content repo is the entire backup. No separate database dump required for content.

## Success criteria

Libreta v1.0 is successful when:

1. The single primary user (you) prefers it to all alternatives evaluated.
2. The content repo can be fully consumed outside Libreta (clone, read, edit in VS Code, push back) and Libreta reflects those changes on next sync.
3. Diagrams created in Libreta remain editable when the repo is opened on github.com or in VS Code's drawio extension.
4. A fresh deploy on a clean machine takes under 5 minutes end-to-end.
5. A 1000-page wiki imports, indexes, and renders without performance degradation.

## Out of scope

- iOS/Android native apps (mobile web is sufficient)
- Email notifications
- Wiki page approval workflows
- LDAP/SSO in v1
- Multi-tenancy
- WYSIWYG editing of raw HTML
- Conflict-free merge when editing the same page from multiple Libreta instances (single-instance model only in v1)
