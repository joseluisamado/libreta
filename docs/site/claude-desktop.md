---
title: 'Claude Desktop integration'
---

# Using Libreta from Claude Desktop

Libreta exposes an [MCP](https://modelcontextprotocol.io) endpoint so
[Claude Desktop](https://claude.ai/download) can read and write your wiki
pages directly. Ask Claude to draft a page and it lands in your wiki as a
real commit; ask it to revise an existing page and it edits the file in
place — all through Libreta's normal save lifecycle, so every change is a
git commit just like editing in the web UI.

No plugin or local install is needed: the endpoint ships inside Libreta's
backend. You point Claude Desktop at a URL and you're done.

## What Claude can do

Once connected, Claude has four tools:

| Tool | What it does |
|---|---|
| `list_sources` | See which wikis (git sources) you have configured. |
| `list_pages` | List the pages in a wiki. |
| `read_page` | Read a page's current contents. |
| `write_page` | Create a new page **or** edit an existing one. |

Claude picks the right tools on its own — you just ask in plain language.
These tools are text-only; to add an **image or file** to a page you upload
the bytes to Libreta directly and let Claude reference them — see
[Adding images to a page](#adding-images-to-a-page).

## Before you start

- A running Libreta instance with at least one **git source** added (the
  admin UI at `/-/admin`). If `list_sources` comes back empty, you have no
  sources configured yet.
- The URL where Libreta is reachable, with `/mcp` on the end.

> **Claude Desktop requires `https://` (or `localhost`).** This is the part
> that trips most people up. Both ways of connecting below refuse a plain
> `http://` URL to a remote host:
>
> - The **Custom Connector** UI rejects it outright ("http is not supported").
> - The **`mcp-remote`** bridge refuses `http://` unless you pass
>   `--allow-http`, and even then mangles non-standard ports during its OAuth
>   discovery step.
>
> So unless Libreta is at `http://localhost:<port>/mcp` (e.g. via an SSH
> tunnel), you need an **HTTPS** endpoint. If your instance is on a LAN
> hostname a public CA can't issue for (like `wiki.lan`), see
> [HTTPS for a LAN deployment](#https-for-a-lan-deployment) below — it takes
> about five minutes and you only do it once per client machine.

> **Keep it on a network you trust.** The MCP endpoint is currently
> **unauthenticated** — anyone who can reach `/mcp` can read and write your
> pages. Use it on your LAN, over a VPN/Tailscale, or behind your own
> authenticating proxy. Don't expose `/mcp` to the open internet. (This
> matches Libreta's current pre-auth state; multi-user auth is on the
> roadmap.)

## Configure Claude Desktop

Libreta's `/mcp` endpoint speaks the Streamable HTTP transport. A quirk of
Claude **Desktop** matters here: unlike Claude Code, its
`claude_desktop_config.json` only understands `command`-style (stdio)
servers — if you paste a raw `{"url": ...}` entry it gets **silently
discarded** on startup. So use one of the two paths below instead. The
**Custom Connector** path is simplest; pick it unless you specifically want
everything in a config file.

### Option A — Custom Connector (recommended)

1. Open Claude Desktop → **Settings** → **Connectors**.
2. Click **Add custom connector**.
3. Give it a name (e.g. `Libreta`) and paste your endpoint URL — your
   instance's address with `/mcp` on the end, e.g.
   `https://wiki.lan:8091/mcp` (or `http://localhost:8080/mcp` if tunnelled
   to localhost). **A remote `http://` URL will be rejected** — see the HTTPS
   note above.
4. Save. Open a new chat; Libreta's tools should appear (the tools/plug icon
   in the message box). Claude asks your permission the first time it uses a
   tool.

### Option B — config file via the `mcp-remote` bridge

If you prefer the config file, you can't point it at the URL directly — you
wrap the URL with [`mcp-remote`](https://www.npmjs.com/package/mcp-remote),
a small stdio↔HTTP bridge Claude Desktop launches. This needs
[Node.js](https://nodejs.org) installed (it provides `npx`).

1. Open Settings → **Developer** → **Edit Config** to open
   `claude_desktop_config.json`:
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

2. Add a `libreta` entry under `mcpServers`:

   ```json
   {
     "mcpServers": {
       "libreta": {
         "command": "npx",
         "args": ["-y", "mcp-remote", "https://wiki.lan:8091/mcp"]
       }
     }
   }
   ```

   Replace the URL with your instance's address. Use an `https://` URL (or
   `http://localhost:…` if tunnelled) — `mcp-remote` refuses other `http://`
   URLs without `--allow-http`, and that flag has trouble with non-standard
   ports, so HTTPS is the reliable path. If you already have other servers
   under `mcpServers`, add `libreta` alongside them.

3. **Restart Claude Desktop.** Open a new chat — Libreta's tools should
   appear, and Claude will ask permission the first time it uses one.

If the tools don't appear, see [Troubleshooting](#troubleshooting) below.

## HTTPS for a LAN deployment

Claude Desktop needs an `https://` endpoint (or `localhost`). If Libreta runs
on a LAN box reached by a name a public certificate authority can't issue for
— e.g. `wiki.lan` — you can't use Let's Encrypt. Instead, generate a
locally-trusted certificate with [mkcert](https://github.com/FiloSottile/mkcert)
and serve it through the bundled Caddy reverse proxy.

The nice property of this approach: **you trust mkcert's CA once, and that
trust survives Libreta redeployments — even a hardware replacement.** The CA
lives on *your* machine, not in the deployment; the box only ever holds a leaf
certificate, which is regenerable at any time. So you never have to re-trust
anything when you rebuild or move the server.

### One time, on each client machine

Install mkcert and register its CA in your system trust store:

```bash
# macOS
brew install mkcert
mkcert -install
```

`mkcert -install` is what makes browsers and Claude Desktop trust certificates
mkcert signs. You do this once per machine that will connect — not once per
deployment.

### TLS is handled by `make release`

Once mkcert's CA is installed on your machine (above), **releases handle the
certificate for you** — there's no separate TLS step to remember. Every
`make release` / `make release-current`:

1. Checks that mkcert and its CA exist on your machine. If not, it stops and
   prints the `brew install mkcert` / `mkcert -install` steps — it won't deploy
   a half-configured TLS setup.
2. Checks the deployment host for a valid leaf certificate for
   `TLS_HOSTNAME`. If it's missing, expired, or for the wrong hostname, it
   generates a fresh one **locally** (signed by your CA — the one clients
   trust) and copies it over.
3. Brings the stack up **with the Caddy + mkcert overlay**, serving HTTPS on
   port **8091** (the same port the plain-HTTP frontend used).

So a normal release is all you need:

```bash
make release TLS_HOSTNAME=wiki.lan \
    DEPLOY_HOST=user@wiki-host DEPLOY_PATH=/srv/libreta
```

`TLS_HOSTNAME`, `DEPLOY_HOST`, and `DEPLOY_PATH` can be set once in `local.mk`
so you don't repeat them. Want HTTPS on a different port? Set
`LIBRETA_HTTPS_PORT` (it must match the port in `Caddyfile.mkcert`'s site
address). To provision/refresh the cert **without** a full release, run
`make setup-tls`.

After it finishes, Libreta is at `https://wiki.lan:8091/` and the MCP
endpoint at `https://wiki.lan:8091/mcp`. Point Claude Desktop there.

> The `certs/` directory and the generated `Caddyfile.mkcert` are gitignored —
> per-deployment material, and the key must never be committed. They don't need
> backing up: a release regenerates the leaf whenever it's missing. Only
> mkcert's **CA**, on your client machine, matters — and that's already in your
> trust store, independent of Libreta.

### When you redeploy or replace hardware

Just run `make release` (or `release-current`) again. It sees the new host has
no valid cert and provisions one automatically. **No client-side change is
needed**: your machine already trusts mkcert's CA, which signed the new leaf.
This is the whole point of mkcert over Caddy's auto-generated internal CA
(which would be reborn inside the deployment and force a re-trust on every
client).

## Example prompts

Once it's connected, talk to Claude normally. A few things to try:

**Discover what's there**

> What wikis do I have in Libreta, and what pages are in my "notes" wiki?

**Create a new page from a conversation**

> We just worked out the deployment steps. Write them up as a page called
> `runbooks/deploy.md` in my "ops" wiki, with a numbered checklist.

**Draft from scratch**

> Create a page `recipes/sourdough.md` in my "kitchen" wiki: a sourdough
> loaf recipe with ingredients, a timeline table, and step-by-step
> instructions.

**Edit an existing page**

> Read `meeting-notes/2026-q2.md` in my "work" wiki and add a "Decisions"
> section at the end summarising the action items.

**Reorganise / expand**

> Read all the pages under `projects/` in my "work" wiki and create a new
> `projects/index.md` that links to each one with a one-line summary.

**Tidy up**

> The page `notes/ideas.md` in my "personal" wiki is a mess of bullet
> points. Read it, group the ideas into themed sections, and save it back.

Tip: name the **source** ("my ops wiki") and the **path** you want
(`runbooks/deploy.md`) and Claude will get it right the first time. You can
always review the change afterward in Libreta's UI or with `git log` in the
source repo — every write is a commit.

## Adding images to a page

The MCP tools deliberately handle **text only** — there is no "upload an
image" tool. That's not an oversight: an MCP tool argument travels inside the
model's context, so passing a file's bytes through a tool would mean the model
generating the whole image as base64 (a 5 MB photo becomes well over a million
tokens). It can't afford that, and it can't produce bytes it doesn't already
hold.

So images go in the way the web editor does it — the **bytes are POSTed
straight to Libreta over plain HTTP**, never through the model — and then the
page's markdown just *references* the stored file. Two steps:

**1. Upload the file to the page's attachment endpoint.** The bytes go directly
to the backend as a normal multipart upload:

```bash
curl -F file=@diagram.png \
  https://wiki.lan:8091/api/v1/sources/wiki/pages/notes/ideas/assets
```

- Use the **same base URL as your `/mcp` endpoint**, but with
  `/api/v1/sources/…` instead of `/mcp` (here `https://wiki.lan:8091`). The
  bundled proxy forwards `/api/` to the backend on the same host and port you
  already use for MCP — you don't need to reach the backend's internal port.
- `sources/wiki` — your source id (from `list_sources`).
- `pages/notes/ideas` — the page path, **without** the `.md`.
- `file` — the multipart field name (must be exactly `file`).

The response tells you the path to reference:

```json
{ "filename": ".ideas.md/diagram.png", "size": 20153,
  "sha256": "…", "kind": "image", "deduped": false }
```

The file is now stored in the page's hidden sidecar directory
(`notes/.ideas.md/`) and **committed** — same as uploading through the web UI.
(Uploading identical bytes again is deduplicated: you get the same `filename`
back with `"deduped": true` and no second copy.)

**2. Ask Claude to reference it.** Give Claude the returned `filename` and let
it edit the page:

> I just uploaded `.ideas.md/diagram.png` to `notes/ideas` in my "wiki" wiki.
> Read the page and add the image under the "Architecture" heading.

Claude uses `write_page` to drop `![](.ideas.md/diagram.png)` into the body.
The image bytes never touched the conversation; only the short path did.

> If you're driving Libreta from **Claude Code** (not Desktop), Claude can run
> the `curl` itself, so the whole thing is one request: "upload
> `./diagram.png` to `notes/ideas` and embed it." Claude Desktop can't issue
> arbitrary HTTP, so there you run the upload yourself (or via a script) and
> hand Claude the returned path.

The same endpoint accepts any file type (PDFs, `.drawio.svg` diagrams, etc.),
not just images — `kind` in the response is `"image"` or `"file"` accordingly,
and Claude links non-images with `[text](.page.md/report.pdf)` instead of an
image embed.

## Good to know

- **Every write is a git commit.** Claude's edits go through the exact same
  save → commit → push path as the web editor. Nothing is special-cased or
  hidden from git history.
- **Editing replaces the whole page.** When Claude edits, it reads the
  current page, applies your change, and writes the full new version. If you
  have the *same* page open in Libreta's web editor at the same time,
  whoever saves last wins — so don't edit the same page in both places at
  once.
- **Page paths drop the `.md`.** Internally Libreta refers to
  `notes/ideas.md` as `notes/ideas`. Claude handles this for you; mentioning
  either form is fine.
- **It only sees git sources, not watched folders.** Watched folders are
  read-only territory Libreta doesn't own, so they're out of scope for
  writing.

## Troubleshooting

**The Libreta tools don't show up in Claude Desktop.**
Double-check the URL ends in `/mcp` and is reachable *from the machine
running Claude Desktop* (open it in a browser on that machine — you should
get a response, not a connection error). If you used the config file
(Option B), remember Claude Desktop ignores a plain `{"url": ...}` entry —
it must be the `npx … mcp-remote …` form, and the JSON must be valid (a
trailing comma or missing brace silently disables the whole `mcpServers`
section). Fully quit and reopen Claude Desktop after any config change. If
the file path approach keeps fighting you, switch to the Custom Connector
(Option A), which avoids the config-schema quirk entirely.

**"http is not supported" (Custom Connector) or "Server disconnected"
(`mcp-remote`).**
Both mean Claude Desktop won't talk to a plain `http://` remote endpoint. The
Custom Connector rejects it directly; `mcp-remote` exits with *"Non-HTTPS URLs
are only allowed for localhost or when --allow-http is provided"*, which Claude
surfaces as "Server disconnected." The fix is an HTTPS endpoint — see
[HTTPS for a LAN deployment](#https-for-a-lan-deployment). (`--allow-http` is
not a reliable workaround: it drops non-standard ports like `:8091` during its
OAuth-discovery step and then fails to connect.)

**`421 Misdirected Request` / "Invalid Host header" from `/mcp`.**
The MCP transport's DNS-rebinding protection rejected your `Host` header. This
is disabled in current Libreta builds; if you hit it, your backend is running
an older image — rebuild and redeploy it.

**`list_sources` returns nothing.**
You haven't added a git source yet, or it's still cloning. Open Libreta's
admin UI at `/-/admin` and add one; wait for the clone to finish.

**It works locally but not through my domain / reverse proxy.**
The MCP endpoint streams over a long-lived connection, so your proxy must
forward `/mcp` with response buffering off and a generous read timeout (and
HTTP/1.1). Libreta's bundled nginx already does this; if you front Libreta
with your own Caddy/Traefik/nginx, replicate those settings for the `/mcp`
path. See [`docs/DEPLOY.md`](../DEPLOY.md).

**Writes seem to succeed but I don't see them pushed to my remote.**
Commits are local first, then pushed asynchronously — the same as any save.
Give it a moment, or check the source's status dot in the sidebar.
