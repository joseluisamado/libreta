# PERFORMANCE.md — measured numbers vs targets

Libreta's non-functional requirements live in [`PROJECT.md`](./PROJECT.md):

> **Performance:** page loads under 200 ms on a Raspberry Pi 4. Search
> queries under 500 ms on a 1000-page corpus.
>
> **Footprint:** total memory usage under 512 MB at idle. Disk usage
> scales linearly with content.

This document reports a **smoke benchmark** — a quick sanity check that
nothing is catastrophically slow on a developer-class machine. It is not
a substitute for measuring on the actual deployment hardware.

For real-corpus-on-target-hardware numbers, run the same script on the
machine where Libreta will live and compare.

---

## Reproducing

```bash
bash scripts/smoke_bench.sh
```

Reads three env vars (all optional):

| Var | Default | Meaning |
|---|---|---|
| `LIBRETA_BASE` | `http://localhost:8092` | API root |
| `LIBRETA_SOURCE` | `libreta-data` | Source id whose tree/page is queried |
| `LIBRETA_SEARCH_TERM` | `the` | Search query (high-frequency token) |
| `N` | `10` | Samples per measurement |

Each measurement reports min / median / max in milliseconds plus a
`docker stats` snapshot of the API container's memory.

---

## Results — 2026-05-09

Hardware: Apple M-series laptop, dev profile (`docker compose --profile dev`),
two real git sources cloned locally (95 + 102 pages = 197 markdown files).

| Endpoint | Median | Max | Target |
|---|---:|---:|---|
| `GET /healthz` | 2.6 ms | 7.5 ms | n/a (baseline) |
| `GET /sources/libreta-data/tree?depth=10` | 9.5 ms | 33.2 ms | < 200 ms (page load proxy) |
| `GET /search?q=the` | 6.2 ms | 22.8 ms | **< 500 ms** |
| `GET /sources/libreta-data/pages/aaa/a-diagram` | 2.2 ms | 2.6 ms | **< 200 ms** |

Idle memory: **81 MiB** (target: **< 512 MiB**).

All four numbers are at least an order of magnitude under target. The
caveat is the corpus size: 197 pages, well under the 1000-page target
in PROJECT.md. Larger corpora may stress the tree walk and search
differently — see "What this doesn't measure" below.

---

## What this doesn't measure

- **Pi 4 numbers.** The 200 ms / 500 ms targets are calibrated to the
  Raspberry Pi 4. On laptop-class hardware, anything that fits in a
  cache or hits an SSD will look fast. Re-run on the deployment box
  before claiming the targets are met.

- **1000-page corpus.** The smoke run uses ~200 pages. To stress-test
  search and tree-walk, point the script at a source containing 1000+
  markdown files (e.g. clone the linux-kernel docs or generate fixtures
  with `scripts/import_apple_notes.py`).

- **Save latency.** `PUT /sources/<id>/pages/<path>` triggers a pygit2
  commit + FTS5 index update + push enqueue. Worth measuring on the
  Pi 4; the smoke script doesn't cover writes (they mutate state and
  would dirty the working tree).

- **Cold start.** All numbers above are warm — the API has been running
  for >40 minutes when measured. Cold-start latency (first request after
  container boot) is typically 2–5× the warm number. Important if you're
  scaling to zero in some serverless way; not relevant for the supported
  deployment.

- **Concurrent load.** The script is sequential. Libreta is async-first
  but single-process; a real concurrency benchmark would matter for a
  multi-user deployment, which is M6 territory.

- **Frontend rendering.** SPA TTI, paint times, mermaid/KaTeX render
  cost are all client-side and not in scope for this script.

---

## How to extend the smoke bench

If a future change introduces a new perf-sensitive endpoint, add a
`bench` line to `scripts/smoke_bench.sh`:

```bash
bench "label" "$BASE/api/v1/your/endpoint?args"
```

Each `bench` call samples `$N` times and prints min/median/max. Keep
the script under ~100 lines — if benchmarking grows real teeth, fold
it into a proper harness (locust, k6, or pytest-benchmark) instead.

---

## Low-spec / homelab notes

A deployment on a 2 GB-RAM 4-core ARM SBC (NanoPi-class) with ~2 GB of
working-tree content across two git sources surfaced latency issues
that don't show up on a developer Mac. Fixes that landed in this
corpus:

- **Backend image footprint**. Multi-stage Dockerfile + reliance on
  pygit2's manylinux wheel (statically bundles libgit2, openssl,
  libssh2, pcre) dropped the image from **586 MB → 206 MB**. No
  `libgit2-dev` or `build-essential` survives into the runtime image;
  only `ca-certificates` is added.
- **Sync click latency**. Each fetch used to run `repo.status()` on
  the working tree (or, later, `index.diff_to_workdir()`) to gate the
  fast-forward. After an `rsync`-style migration the index stat cache
  was invalidated, so libgit2 re-hashed every tracked file — 1.2 GB on
  the affected box, ~73 s of CPU per sync. The pre-flight scan was
  removed entirely; the FF now uses `pygit2.CheckoutStrategy.SAFE` and
  lets libgit2 itself refuse the checkout if any file in the diff has
  uncommitted local changes (same semantics as `git pull`, but only
  the files that would change get hashed). Sync click dropped from
  ~60 s to a few seconds on a clean tree.
- **Push: no more auto-stage**. The push path used to call
  `repo.status()` to auto-stage anything dirty before pushing. Since
  Libreta commits on every page write, the auto-stage only ever caught
  external edits — which are now the user's responsibility to commit.
  Skipping the scan eliminates a per-push working-tree hash.
- **Startup reindex**. The FTS5 reindex used to read every `.md` body
  on every restart. It now compares the recorded
  `sources_meta.indexed_head` against the current HEAD; equal → skip
  the source entirely. If HEAD moved, only the files in the git diff
  are reindexed. On a quiet repo, restart consumes <0.1 s of CPU.
- **Startup is non-blocking**. Reindex and source sync run as
  background tasks inside the FastAPI lifespan instead of awaiting in
  the lifespan body, so the HTTP server accepts requests within
  ~30 s (Python startup) instead of waiting minutes for sync.
- **Sync parallelism cap**. `startup_sync` and the periodic loop share
  a 2-permit semaphore. Fanning out one fetch per source in parallel
  on a low-core host pegs every core through contention (libgit2 pack
  resolution is CPU-bound and single-threaded per call). `next_sync`
  is also seeded so the first periodic tick after startup doesn't
  re-fetch what `startup_sync` just did.

These changes only matter on slow / low-core hardware. On a developer
Mac with cache-warm SSD, all of them were invisible.

---

## When to re-run

- Before tagging a release.
- After any change to: `storage/pagefile.py`, `storage/sources.py`,
  `storage/search.py`, the FTS5 schema, the markdown serializer.
- After bumping FastAPI, pygit2, or markdown-it-py.

If a number regresses by >2× without a known cause, investigate before
merging. The current numbers are a long way under target, so a 2×
regression is still inside the budget — but it's a useful early-warning
threshold.
