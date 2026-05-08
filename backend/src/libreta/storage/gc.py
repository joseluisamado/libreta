"""Orphan-asset garbage collection.

An asset is an *orphan* when it lives in a page's sidecar directory
(``<dir>/.<name>.md/``) but is not referenced from the owning page's markdown
body. Orphans can accumulate from:

- failed saves (the upload reached disk before a UI error)
- deleted-then-recreated diagrams
- renamed pages whose sidecar got moved but stale links never got cleaned up

This module finds them and (optionally) deletes them with one git commit per
page. It does not look across pages — assets are page-scoped by design (see
ARCHITECTURE.md "Asset handling").
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

# Match references in markdown that could point at a sidecar asset:
#   ![alt](path)              standard image
#   [label](path)             standard link
#   src="path" / href="path"  inline HTML (rare but allowed by GFM)
#
# We extract whatever is between the parens / quotes and then take its
# basename. The owning page's body is small enough that a regex pass is
# adequate — we don't try to fully parse markdown.
_REF_RE = re.compile(
    r"""
    !?\[[^\]]*\]\(\s*<?([^)\s'"]+)>?  # markdown image/link
    |
    (?:src|href)\s*=\s*["']([^"']+)   # html attribute
    """,
    re.VERBOSE,
)


def _basename(ref: str) -> str:
    """Strip query/fragment and any leading directory components from a ref."""
    # Drop fragment and query
    cut = re.split(r"[?#]", ref, maxsplit=1)[0]
    # Take the trailing path segment
    return cut.rsplit("/", 1)[-1]


def referenced_basenames(md_body: str) -> set[str]:
    """All asset basenames referenced from a page body."""
    out: set[str] = set()
    for m in _REF_RE.finditer(md_body):
        ref = m.group(1) or m.group(2)
        if not ref:
            continue
        if ref.startswith(("http://", "https://", "//", "mailto:", "#")):
            continue
        out.add(_basename(ref))
    return out


def _iter_sidecars(repo_root: Path) -> Iterable[tuple[Path, Path]]:
    """Yield (md_file, sidecar_dir) for every page sidecar in *repo_root*.

    A sidecar is a directory named ``.<page-name>.md`` that sits next to a
    real ``<page-name>.md`` file.
    """
    for sidecar in repo_root.rglob(".*.md"):
        if not sidecar.is_dir():
            continue
        # Hidden ancestors (e.g. inside .git, .meta) are skipped
        if any(p.startswith(".") and p not in {sidecar.name} for p in sidecar.parts):
            # Allow the sidecar's own name, but not other dot-prefixed
            # ancestors. The sidecar name itself starts with '.', so we
            # accept it; we reject any *other* dot-prefixed segment.
            rel_parts = sidecar.relative_to(repo_root).parts
            if any(seg.startswith(".") and seg != sidecar.name for seg in rel_parts):
                continue
        page_name = sidecar.name[1:]  # strip leading dot
        md_file = sidecar.parent / page_name
        if md_file.is_file():
            yield md_file, sidecar


def commit_orphan_removal(
    repo_root: Path,
    md_file: Path,
    orphans: list[Path],
) -> None:
    """Delete *orphans* from disk and commit the removal as one commit.

    Path arguments must be absolute and inside *repo_root*. The commit
    message names the owning page so history is browsable.
    """
    import contextlib

    import pygit2

    repo = pygit2.Repository(str(repo_root))
    index = repo.index

    rel_md = md_file.relative_to(repo_root).as_posix()
    rel_orphans: list[str] = []
    for o in orphans:
        rel_orphans.append(o.relative_to(repo_root).as_posix())
        o.unlink()

    for rel in rel_orphans:
        with contextlib.suppress(KeyError, OSError):
            index.remove(rel)
    index.write()

    tree = index.write_tree()
    try:
        head = repo.head
        parents = [head.target]
    except (pygit2.GitError, KeyError):
        parents = []
    sig = pygit2.Signature("Libreta", "libreta@localhost")
    msg = f"gc: remove {len(rel_orphans)} orphan asset(s) from {rel_md}"
    repo.create_commit("HEAD", sig, sig, msg, tree, parents)


def find_orphans(repo_root: Path) -> list[tuple[Path, list[Path]]]:
    """Return ``[(md_file, [orphan_paths…]), …]`` for *repo_root*.

    Pages with no orphans are omitted. Orphan paths are absolute. The result
    is sorted by md_file path for deterministic output.
    """
    results: list[tuple[Path, list[Path]]] = []
    for md_file, sidecar in _iter_sidecars(repo_root):
        try:
            body = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        referenced = referenced_basenames(body)
        orphans: list[Path] = []
        for asset in sorted(sidecar.iterdir()):
            if not asset.is_file():
                continue
            if asset.name.startswith("."):
                continue
            if asset.suffix == ".md":
                continue
            if asset.name not in referenced:
                orphans.append(asset)
        if orphans:
            results.append((md_file, orphans))
    results.sort(key=lambda r: str(r[0]))
    return results
