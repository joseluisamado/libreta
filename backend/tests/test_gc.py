from __future__ import annotations

from pathlib import Path

import pygit2

from libreta.storage.gc import (
    commit_orphan_removal,
    find_orphans,
    referenced_basenames,
)


def test_referenced_basenames_picks_up_image_and_link() -> None:
    md = """
# Page

![alt](photo.jpg)
See [the spec](spec.pdf) and [external](https://example.com/x.pdf).
<img src="banner.png" />
"""
    refs = referenced_basenames(md)
    assert refs == {"photo.jpg", "spec.pdf", "banner.png"}


def test_referenced_basenames_handles_sidecar_prefix() -> None:
    md = "![](.foo.md/photo.jpg) [doc](.foo.md/spec.pdf)"
    assert referenced_basenames(md) == {"photo.jpg", "spec.pdf"}


def test_referenced_basenames_strips_query_and_fragment() -> None:
    md = "![](photo.jpg?v=2#fig1)"
    assert referenced_basenames(md) == {"photo.jpg"}


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    pygit2.init_repository(str(repo))
    return repo


def test_find_orphans_flags_unreferenced_files(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    page = repo / "page.md"
    page.write_text("# Page\n\n![](.page.md/keep.png)\n")
    sidecar = repo / ".page.md"
    sidecar.mkdir()
    (sidecar / "keep.png").write_bytes(b"k")
    (sidecar / "orphan.png").write_bytes(b"o")
    (sidecar / "stale.drawio.svg").write_bytes(b"s")

    results = find_orphans(repo)
    assert len(results) == 1
    md_file, orphans = results[0]
    assert md_file == page
    names = sorted(o.name for o in orphans)
    assert names == ["orphan.png", "stale.drawio.svg"]


def test_find_orphans_skips_pages_with_all_referenced(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    page = repo / "page.md"
    page.write_text("![](photo.jpg)")
    sidecar = repo / ".page.md"
    sidecar.mkdir()
    (sidecar / "photo.jpg").write_bytes(b"x")

    assert find_orphans(repo) == []


def test_find_orphans_ignores_dot_files_in_sidecar(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    page = repo / "page.md"
    page.write_text("# nothing")
    sidecar = repo / ".page.md"
    sidecar.mkdir()
    (sidecar / ".gitkeep").write_bytes(b"")

    assert find_orphans(repo) == []


def test_find_orphans_skips_hidden_directories(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    # A sidecar-shaped directory living under .meta/ should not be walked.
    meta = repo / ".meta" / ".x.md"
    meta.mkdir(parents=True)
    (meta / "leftover.bin").write_bytes(b"x")

    assert find_orphans(repo) == []


def test_commit_orphan_removal_unlinks_and_commits(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    page = repo / "page.md"
    page.write_text("![](.page.md/keep.png)\n")
    sidecar = repo / ".page.md"
    sidecar.mkdir()
    keep = sidecar / "keep.png"
    keep.write_bytes(b"k")
    orphan = sidecar / "orphan.png"
    orphan.write_bytes(b"o")

    # Stage + commit the initial state so HEAD exists
    pyrepo = pygit2.Repository(str(repo))
    pyrepo.index.add_all()
    pyrepo.index.write()
    tree = pyrepo.index.write_tree()
    sig = pygit2.Signature("test", "t@t")
    pyrepo.create_commit("HEAD", sig, sig, "init", tree, [])

    commit_orphan_removal(repo, page, [orphan])

    assert keep.exists()
    assert not orphan.exists()
    head = pyrepo.head.peel(pygit2.Commit)
    assert "gc: remove 1 orphan" in head.message
    assert "page.md" in head.message
