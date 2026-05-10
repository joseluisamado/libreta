#!/usr/bin/env bash
#
# smoke_bench.sh — quick performance sanity check against a running Libreta.
#
# Measures three things, ten times each, against the live API:
#
#   1. /api/v1/healthz          — baseline round-trip latency.
#   2. /api/v1/sources/<id>/tree — page-tree walk (proxy for "page list" UI).
#   3. /api/v1/search?q=<term>   — full-text search query.
#   4. PUT /api/v1/sources/<id>/pages/<path> — page save (commit + index).
#
# Targets (from docs/PROJECT.md "Non-functional requirements"):
#   - page load   < 200 ms (on a Pi 4; we report what we measure here)
#   - search      < 500 ms (1000-page corpus)
#   - idle memory < 512 MB
#
# Reports min/median/max in ms. Doesn't exit non-zero on a slow run —
# this is a smoke test, not a CI gate.

set -euo pipefail

BASE="${LIBRETA_BASE:-http://localhost:8092}"
SOURCE="${LIBRETA_SOURCE:-libreta-data}"
SEARCH="${LIBRETA_SEARCH_TERM:-the}"
N="${N:-10}"

ms() {
  # Read N stdin floats (curl-format seconds), print min/median/max in ms.
  python3 -c '
import sys, statistics
xs = sorted(float(x) * 1000 for x in sys.stdin if x.strip())
if not xs:
    print("(no samples)"); raise SystemExit
print(f"  min {xs[0]:6.1f} ms   median {statistics.median(xs):6.1f} ms   max {xs[-1]:6.1f} ms   (n={len(xs)})")
'
}

bench() {
  local label="$1"; shift
  echo "$label"
  for _ in $(seq 1 "$N"); do
    curl -sf -o /dev/null -w "%{time_total}\n" "$@"
  done | ms
}

echo "→ Libreta smoke benchmarks against $BASE (n=$N each)"
echo

bench "healthz" "$BASE/api/v1/healthz"
bench "tree (source=$SOURCE)" "$BASE/api/v1/sources/$SOURCE/tree?depth=10"
bench "search q=$SEARCH" "$BASE/api/v1/search?q=$SEARCH"

# Pick the first .md file in the source as a read target.
sample_path=$(curl -sf "$BASE/api/v1/sources/$SOURCE/tree?depth=10" \
  | python3 -c '
import json, sys
def first_page(nodes):
    for n in nodes:
        if not n.get("is_directory"): return n["path"]
        r = first_page(n.get("children", []))
        if r: return r
    return None
print(first_page(json.load(sys.stdin)) or "")
')

if [[ -n "$sample_path" ]]; then
  bench "page read $sample_path" \
    "$BASE/api/v1/sources/$SOURCE/pages/$sample_path"
fi

# Memory snapshot of the api container, if running.
if command -v docker >/dev/null 2>&1; then
  echo
  echo "→ docker stats (api):"
  docker stats --no-stream --format \
    'CPU {{.CPUPerc}}  MEM {{.MemUsage}}  ({{.Name}})' libreta-api-1 2>/dev/null \
    || echo "  (api container not running under that name; skipped)"
fi
