# SECURITY-REVIEW.md — pre-1.0 review

This document records the manual security review carried out before the
v1.0 tag. It enumerates the surfaces that were audited, the findings, the
fixes applied, and the known limitations that operators should understand
before exposing Libreta to a network.

Scope: backend (`backend/src/libreta/`), frontend (`frontend/src/`),
runtime configuration, dependency lockfiles. Audit performed against
commit `main` on 2026-05-09.

---

## Threat model

Libreta v1.0 is a **single-user wiki** behind authentication terminated
by your reverse proxy (or your network's perimeter). There is no
in-application authentication or authorisation; M6 will introduce that.

The realistic adversaries are therefore:

- **Untrusted markdown content**, e.g. files imported from third-party
  systems (Apple Notes, Confluence) or pulled from a git remote that
  someone else can push to. Goal: keep that content from running JS in
  the editor's browser session.
- **A malicious or compromised git remote** that the operator
  intentionally configured. Goal: limit blast radius — a bad remote
  shouldn't read files outside its repo, and an MITM on the network path
  to that remote should be visible (caveat: see "Known limitations").
- **A casual web attacker** who can reach the Libreta HTTP surface,
  whether because the operator misconfigured exposure or because a
  reverse-proxy gate is misbehaving. Goal: no path-traversal reads, no
  unauthenticated writes that wouldn't already be reachable.

We explicitly **do not** model:

- An attacker with shell access on the host.
- An attacker who can modify the Docker volumes from outside the API.
- Multiple simultaneous users with different trust levels (M6).

---

## What was audited

| Surface | Files |
|---|---|
| Page-path validation | [`storage/paths.py`](../backend/src/libreta/storage/paths.py), [`storage/pagefile.py`](../backend/src/libreta/storage/pagefile.py) |
| Asset upload, dedup, replace | [`storage/assets.py`](../backend/src/libreta/storage/assets.py) |
| Source page/asset reads | [`storage/sources.py`](../backend/src/libreta/storage/sources.py), [`api/sources.py`](../backend/src/libreta/api/sources.py) |
| Watched-folder reads | [`storage/watched.py`](../backend/src/libreta/storage/watched.py), [`api/watch.py`](../backend/src/libreta/api/watch.py) |
| SSH credential handling | [`storage/ssh.py`](../backend/src/libreta/storage/ssh.py) |
| Markdown rendering / HTML output | [`frontend/src/markdown.ts`](../frontend/src/markdown.ts), `v-html` callsites |
| Upload size + content-type limits | [`api/sources.py`](../backend/src/libreta/api/sources.py), [`api/pages.py`](../backend/src/libreta/api/pages.py) |
| Search query handling | [`api/search.py`](../backend/src/libreta/api/search.py) |
| Dependency CVEs | `pip-audit` against backend, `pnpm audit` against frontend |

---

## Findings and fixes

Severity is **P1** = exploitable in the threat model and fixed in this
review; **P2** = exploitable but lower-impact; **P3** = hardening; **info**
= notable but not actionable here.

### 1. P1 — Stored XSS via mermaid fence content (FIXED)

The mermaid fence renderer in `frontend/src/markdown.ts` was emitting
user content directly into the HTML output:

```ts
return `<pre class="mermaid">${token.content}</pre>\n`
```

`MarkdownIt` is configured with `html: false`, which strips raw HTML
elsewhere — but the fence renderer is custom and bypassed that. A
markdown file containing

```
\`\`\`mermaid
A</pre><script>alert(1)</script>
\`\`\`
```

would inject and execute the script when rendered via `v-html`.

This violates **R6** (server-rendered HTML never executes user-supplied
JS).

**Fix** ([`markdown.ts`](../frontend/src/markdown.ts)): wrap
`token.content` in `md.utils.escapeHtml(...)`. Mermaid reads
`textContent`, so escaping does not affect the diagram render.

### 2. P1 — Hidden-file disclosure via `validate_path_segments` (FIXED)

`storage/pagefile.py::validate_path_segments` rejected `.` and `..` but
permitted any *other* segment starting with a dot. Combined with the
`(root / raw_path).resolve(); relative_to(root)` containment check, the
attacker could request files genuinely inside the root that shouldn't be
served — e.g. `.git/config`, `.git/hooks/pre-commit`, or any other
operator-internal hidden file.

This affected:
- `GET /api/v1/sources/{id}/assets/{path}` (via `pagefile.resolve_asset`)
- `GET /api/v1/watched/{label}/assets/{path}`
- The legacy `/api/v1/assets/{path}` route

`storage/sources.py::_validate_source_path` already had the right shape
(rejects hidden segments). The fix is to push that logic down into
`validate_path_segments`.

**Fix** ([`pagefile.py`](../backend/src/libreta/storage/pagefile.py)):
forbid any segment starting with `.git`, `.ssh`, or `.libreta`. Sidecar
asset directories (`.foo.md/`) remain accessible, since they don't share
those prefixes.

```python
_FORBIDDEN_HIDDEN_PREFIXES = (".git", ".ssh", ".libreta")
```

This is an allowlist-style block on known-sensitive prefixes rather than
a blanket "no leading dot," because the sidecar pattern depends on
leading dots. If new sensitive prefixes appear, append them here.

### 3. P1 — Source-id traversal in source routes (FIXED)

`storage/sources.py::_local_path(repos_dir, source_id)` returned
`repos_dir / source_id` without validating `source_id`. Source IDs
arriving via URL path parameters (`/api/v1/sources/{source_id}/...`)
could contain `..`. `(repos_dir / "..").resolve()` jumps to the parent
directory. Combined with finding 2 (now also fixed) or with the absent
hidden-path check on the resolved root, this allowed reading any file
under `/var/lib/libreta/`, including the meta directory's `sources.json`
(which contains repo URLs and SSH-key references).

**Fix** ([`storage/sources.py`](../backend/src/libreta/storage/sources.py)):
validate `source_id` against the same regex Pydantic enforces at create
time, raising `InvalidPathError` on mismatch. The validation is now
*inside* `_local_path`, so every callsite is automatically covered.

```python
_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
```

### 4. P1 — Git host-key verification disabled (PARTIALLY MITIGATED)

`storage/ssh.py::make_callbacks` returned `True` from `certificate_check`
unconditionally for both SSH and HTTP callbacks. For SSH, this disables
host-key verification entirely: an active MITM on the network path
between Libreta and a git remote can intercept clones, fetches, and
pushes.

A proper fix requires a known-hosts mechanism, which is non-trivial:
where does the file live, who manages it, what's the UX for the first
connection? That belongs in M6 alongside the rest of the auth model.

**Mitigation applied** ([`storage/ssh.py`](../backend/src/libreta/storage/ssh.py)):
log the host and `valid` flag at INFO on every git operation, so an
operator can spot unexpected host changes by tailing the API log. The
return value is still `True` — this is **explicitly** documented as a
v1.0 limitation below. Operators who care about active-MITM resistance
should run the git remote on a network path they trust (e.g. a private
network or behind a VPN).

### 5. P3 — SSH key tempfile leak (FIXED)

`make_callbacks` writes the private key to a `mkstemp`-created temp
file because `pygit2.Keypair` requires a path, then never removes it.
Across many sync operations these accumulate in `/tmp` — a few hundred
bytes each, but with 0600 mode on a multi-tenant host that's not great.

**Fix** ([`storage/ssh.py`](../backend/src/libreta/storage/ssh.py)):
register a `weakref.finalize(callbacks_instance, cleanup)` that
unlinks the tempfile when the callbacks object is collected.

### 6. Info — Frontend dev-only CVEs

`pnpm audit` reports two **moderate** advisories:

- `esbuild <=0.24.2` (GHSA-67mh-4wv8-2f99) — dev server can be queried
  cross-origin from any web page. Exploitable only if the developer
  is running `pnpm dev` *and* visits a hostile site at the same time.
- `vite <=6.4.1` (GHSA-4w7w-66w2-5vf9) — path traversal in the dev
  server's source-map handler.

Both vulnerabilities are in the **dev server** code paths. The
production frontend container builds a static `dist/` bundle and serves
it via nginx — esbuild and the vite dev server are not present in the
runtime path.

**Action**: not blocking v1.0. Bump `vite` from `^5.4.10` to `^6.4.2` in
a follow-up; this is a major-version bump (5 → 6) so it needs a build +
test pass on its own, not a quick patch. Tracked as a post-1.0 chore.

### 7. Info — Backend dependencies

`pip-audit` against `uv.lock`: **clean**, no known vulnerabilities in
fastapi, pygit2, pydantic, markdown-it-py, or any transitive dep.

---

## What I checked but found OK

- **MarkdownIt is configured with `html: false`** — raw HTML in markdown
  is escaped. The custom `link_open`, `image`, and (now-fixed) `fence`
  renderers don't bypass this elsewhere. Default URL validation
  (`javascript:` blocking) is in effect on links.
- **Frontmatter parsing** uses `python-frontmatter`, which uses PyYAML
  in safe-load mode — no arbitrary class instantiation.
- **Upload size limit** (25 MB) is enforced on every upload route. The
  Caddy overlay's `max_size 50MB` is a deliberate ceiling above this so
  the API can reject precisely.
- **Search query** is bound to a parameterised SQLite query; the API
  layer caps `q` at 500 chars via `Query(..., max_length=500)`.
- **Pydantic models** validate every request body. `GitSourceCreate.id`
  uses a regex that the storage layer now also enforces (finding 3).
- **Filename sanitisation** for uploads (`storage/assets.py::sanitize_filename`)
  strips path components, refuses `.md`, blocks null bytes, and
  collapses non-`[a-zA-Z0-9._-]` runs.
- **Watched-folder path resolution** (`storage/watched.py`) explicitly
  rejects hidden, `..`, and null-byte segments before any I/O — and
  re-checks containment via `relative_to`.
- **Drawio iframe origin** is configurable (`LIBRETA_DRAWIO_URL`) and
  the postMessage protocol verifies origin in the frontend before
  acting on a message.
- **CORS** is not enabled; the SPA and API are same-origin (nginx in
  front of FastAPI).

---

## Known limitations (deliberate, documented)

These are **not bugs** — they are limits of the v1.0 scope. Operators
who can't accept them should wait for M6 or apply external mitigations.

### L-1. No application-level authentication

Libreta v1.0 has no login, no sessions, no API tokens. Anyone who can
reach the HTTP surface can read and write content. Mitigations: front
with a reverse proxy that enforces auth (e.g. Caddy + basic auth, or
oauth2-proxy), or restrict access at the network level (VPN, private
network, IP allowlist). M6 will land first-party auth.

### L-2. No git host-key verification

See finding 4. Until M6, run git remotes on networks you trust. Watch
the `git remote host=...` log lines for unexpected changes.

### L-3. Trusting the content repository

Libreta renders the markdown in your git repo. If someone else can push
to that repo, they can write content that exercises the markdown
renderer. R6 (no JS execution from rendered markdown) is the boundary;
the HTML escape fix in finding 1 closes the only known gap. If you find
another way to inject script-executing markup, please report it.

### L-4. No outbound-URL allowlist for the editor

The drawio iframe and any image inside the markdown can be sourced from
arbitrary URLs (the markdown allows external `<img>` references via the
asset link rewriter). For self-hosted single-user use this is not a
problem; in a multi-user deployment it would be a soft data-exfiltration
vector worth a CSP. Out of scope for v1.0.

### L-5. No rate limiting

There's no per-route or per-IP rate limiter. A misconfigured exposure
plus a search loop can spike CPU. Mitigate via the reverse proxy.

---

## How to reproduce the review

Backend:

```bash
cd backend
uv run --with pip-audit pip-audit
uv run ruff check . && uv run mypy src && uv run pytest
```

Frontend:

```bash
cd frontend
pnpm install
pnpm audit
pnpm typecheck && pnpm test --run
```

For path-traversal regression:

```bash
# These should all return 4xx errors after the fixes:
curl -sf 'http://localhost:8080/api/v1/sources/foo/assets/.git/config'      # 400
curl -sf 'http://localhost:8080/api/v1/sources/../assets/meta/sources.json' # 400
curl -sf 'http://localhost:8080/api/v1/watched/notes/assets/.git/HEAD'      # 400
```

For the mermaid XSS regression: paste the `</pre><script>` payload into
a `\`\`\`mermaid` fence, save the page, view it. The DOM should contain
escaped entities, not a `<script>` element.

---

## Sign-off

The findings above were fixed in the same review pass. All pre-flight
checks pass:

- backend: 95 tests, ruff (apart from pre-existing housekeeping items
  unrelated to this review), mypy strict — green.
- frontend: 65 tests, vue-tsc — green.
- pip-audit: clean.
- pnpm audit: 2 moderate dev-only advisories (see finding 6).

Reviewer: agent (machine-assisted manual review).
Date: 2026-05-09.
