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

## Before you start

- A running Libreta instance with at least one **git source** added (the
  admin UI at `/-/admin`). If `list_sources` comes back empty, you have no
  sources configured yet.
- The URL where Libreta is reachable. The MCP endpoint is that URL with
  `/mcp` on the end — e.g. `http://localhost:8080/mcp`, or
  `https://wiki.example.com/mcp` if you front it with TLS.

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
   `http://localhost:8080/mcp`.
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
         "args": ["-y", "mcp-remote", "http://localhost:8080/mcp"]
       }
     }
   }
   ```

   Replace the URL with your instance's address. If you already have other
   servers under `mcpServers`, add `libreta` alongside them.

3. **Restart Claude Desktop.** Open a new chat — Libreta's tools should
   appear, and Claude will ask permission the first time it uses one.

If the tools don't appear, see [Troubleshooting](#troubleshooting) below.

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
