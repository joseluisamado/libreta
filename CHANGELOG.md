# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries are generated from [Conventional Commits](https://www.conventionalcommits.org)
by `scripts/changelog.py` at release time.


## [2.3.2] - 2026-06-05

### Fixed

- **editor:** accept HEIC/HEIF and other extension-only images on insert

## [2.3.1] - 2026-06-05

### Fixed

- **assets:** serve page-scoped attachments from pages/ subdir

## [2.3.0] - 2026-06-05

### Added

- **listing:** .webloc bookmarks as first-class external links
- **listing:** e-book viewer + cover thumbnails (EPUB, MOBI, AZW3, FB2, CBZ)

### Fixed

- **build:** make docker-compose.dev.local.yml overlay optional

### Documentation

- **roadmap:** add M11 thumbnail strategy (XDG cache + quickthumb)

## [2.2.0] - 2026-06-04

### Added

- **listing:** text/html/video as first-class children; HEIC + video viewers
- **listing:** images are first-class children, not "other files"
- **frontend:** image viewer, text-thumbnail highlighting, sandboxed HTML render, combined folder pagination
- **frontend:** render images/diagrams in previews + JS-stripped HTML viewer
- Close gaps when previewing markdown files with images or mermaid, drawio diagrams.
- local volume overrides.

### Fixed

- **frontend:** HTML thumbnail showed head, not body (still-blank fix)
- **frontend:** HTML preview tile no longer blank for head-heavy files
- **docker:** make frontend dev image rebuild reliably with current deps

### Documentation

- **claude:** commit to main directly during solo dev
- update README + DEPLOY for 2.0 and the new release flow

## [2.1.0] - 2026-06-04

### Added

- **frontend:** add preview/grid view mode + fix scanned-PDF rendering

### Fixed

- **ssh:** honor allowed_types in git SSH credentials callback

## [2.0.0] - 2026-06-03

Major cleanup release. The original single-content-repo "main wiki" — which had
been superseded by git sources and watched folders, no longer held content, and
surfaced as a confusing empty entity — is removed entirely, and the now-misnamed
`content_dir` setting is renamed to `meta_dir`. See ARCHITECTURE.md D-11.

### ⚠ BREAKING CHANGES

- The main wiki, the `/pages` and `/assets` HTTP APIs, and the `/w/` and
  `/edit/` routes are removed. Wiki content lives in git sources and watched
  folders.
- The `LIBRETA_CONTENT_DIR` env var is removed; set `LIBRETA_META_DIR` instead
  (same value as before — `meta_dir` holds Libreta's own state: the sources
  registry, watched config, and search index).
- Inline image/diagram attachments now require editing inside a git source.

### Removed

- Backend: `api/pages.py`, `api/assets.py`, `storage/pages.py`, the main-wiki
  `resolve_asset`, and the dead single-page index/reindex helpers (search is
  sources-only now).
- Frontend: `PageView` / `EditorView` / `HistoryView` / `DiffView`, the
  `stores/tree.ts` store, and the `/w/ /edit/ /pdf/ /text/ /history/ /diff/`
  routes (the `-source` / `-watch` variants remain).

### Changed

- Renamed the `content_dir` setting to `meta_dir` throughout (config, `/info`,
  `cli reindex --meta-dir`, docker-compose, Dockerfile, Makefile). `cli gc` now
  requires `--source` / `--repo`.

## [1.14.0] - 2026-06-03

_No user-facing changes._

## [1.13.0] - 2026-06-03

### Documentation

- **readme:** add home screen screenshot

## [1.12.0] - 2026-06-02

_No user-facing changes._

## [1.11.0] - 2026-06-02

_No user-facing changes._

## [1.10.0] - 2026-06-02

_No user-facing changes._

## [1.9.0] - 2026-06-02

### Added

- **files:** upload arbitrary files into folders; repo-root navigation

### Fixed

- **files:** delete of an uploaded folder file no longer 404s

## [1.8.0] - 2026-06-01

_No user-facing changes._

## [1.7.0] - 2026-05-31

_No user-facing changes._

## [1.6.1] - 2026-05-31

### Fixed

- **sources:** serialise per-source clone/fetch; show cloning progress
- **admin:** refetch settings on tab refocus; surface load errors

## [1.6.0] - 2026-05-31

### Added

- **admin:** default the browse-repos owner to the server's username
- **admin:** edit support for sources/servers/folders/keys + repo select-all
- **sources:** bulk-import Gitea repos via remembered server credentials

### Fixed

- **sources:** clone private repos without checkout_branch; self-heal empty husks
- **admin:** refresh new source tree on clone, allow removing imported repos
- **sources:** fall back to user repos on 403 and surface Gitea's error message

## [1.5.1] - 2026-05-30

_No user-facing changes._

## [1.4.2] - 2026-05-13

_No user-facing changes._

## [1.4.1] - 2026-05-13

_No user-facing changes._

## [1.4.0] - 2026-05-13

_No user-facing changes._

## [1.3.0] - 2026-05-13

_No user-facing changes._

## [1.2.0] - 2026-05-13

_No user-facing changes._

## [1.0.0] - 2026-05-10

Initial release: a self-hosted wiki over a git repository of markdown files —
FastAPI backend, Vue 3 + Tiptap editor with a byte-identical markdown
round-trip, every save a git commit, drawio diagrams, and full-text search.

_(Commits before this tag predate Conventional Commits, so per-change entries
aren't reconstructed.)_
