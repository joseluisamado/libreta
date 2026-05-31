"""Tests for the git-source fast-forward sync path.

Regression coverage for the bug where ``fetch_and_ff_sync`` advanced the
branch ref with ``set_target`` *before* checking out, which on a pure-add
fast-forward could leave the new files in HEAD but absent from the index and
working tree (git status: ``INDEX_DELETED``).
"""

from __future__ import annotations

import threading
from pathlib import Path

import pygit2

from libreta.storage import sources as src_store
from libreta.storage.sources import clone_source_sync, fetch_and_ff_sync


def _commit_all(repo: pygit2.Repository, message: str) -> pygit2.Oid:
    repo.index.add_all()
    repo.index.write()
    tree = repo.index.write_tree()
    sig = pygit2.Signature("Tester", "tester@example.com")
    parents = [] if repo.head_is_unborn else [repo.head.target]
    return repo.create_commit("HEAD", sig, sig, message, tree, parents)


def _make_remote(tmp_path: Path) -> Path:
    """Create a bare-ish remote with one initial commit on main."""
    remote_work = tmp_path / "remote_work"
    remote_work.mkdir()
    repo = pygit2.init_repository(str(remote_work), initial_head="main")
    (remote_work / "intro.md").write_text("# Intro\n", encoding="utf-8")
    _commit_all(repo, "initial")
    return remote_work


def test_fast_forward_materialises_new_files(tmp_path: Path) -> None:
    """A pure-add fast-forward must write the new files to disk and the index."""
    remote = _make_remote(tmp_path)

    repos_dir = tmp_path / "repos"
    ssh_keys_dir = tmp_path / "ssh"
    gitea_dir = tmp_path / "gitea"
    repos_dir.mkdir()
    ssh_keys_dir.mkdir()
    gitea_dir.mkdir()

    entry = {
        "id": "work",
        "remote_url": str(remote),
        "branch": "main",
        "ssh_key_id": None,
        "http_username": None,
        "http_password": None,
    }

    # First sync clones.
    fetch_and_ff_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)
    local = repos_dir / "work"
    assert (local / "intro.md").exists()

    # Upstream adds new files under a nested dir, including a non-ASCII /
    # em-dash filename like the one that triggered the original bug.
    remote_repo = pygit2.Repository(str(remote))
    nested = remote / "EPSO books"
    nested.mkdir()
    (nested / "Ch2 Verbal Reasoning — Summary & Gotchas.md").write_text(
        "# Verbal\n", encoding="utf-8"
    )
    (nested / "numerical warm-ups.txt").write_text("warmups\n", encoding="utf-8")
    _commit_all(remote_repo, "More materials.")

    # Second sync fast-forwards.
    fetch_and_ff_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)

    # The new files must exist on disk...
    assert (local / "EPSO books" / "Ch2 Verbal Reasoning — Summary & Gotchas.md").exists()
    assert (local / "EPSO books" / "numerical warm-ups.txt").exists()

    # ...and the working tree must be clean (no INDEX_DELETED / WT_DELETED).
    local_repo = pygit2.Repository(str(local))
    assert local_repo.status() == {}, "working tree diverges from HEAD after fast-forward"


def test_fast_forward_heals_desynced_index(tmp_path: Path) -> None:
    """A repo left in the INDEX_DELETED state (a file in HEAD but missing from
    index + working tree, as the old buggy checkout produced) must self-heal on
    the next sync rather than staying permanently stuck."""
    remote = _make_remote(tmp_path)

    repos_dir = tmp_path / "repos"
    ssh_keys_dir = tmp_path / "ssh"
    gitea_dir = tmp_path / "gitea"
    repos_dir.mkdir()
    ssh_keys_dir.mkdir()
    gitea_dir.mkdir()

    entry = {
        "id": "work",
        "remote_url": str(remote),
        "branch": "main",
        "ssh_key_id": None,
        "http_username": None,
        "http_password": None,
    }
    fetch_and_ff_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)
    local = repos_dir / "work"

    # Upstream adds a file; sync it down normally.
    remote_repo = pygit2.Repository(str(remote))
    (remote / "added.md").write_text("# Added\n", encoding="utf-8")
    _commit_all(remote_repo, "add file")
    fetch_and_ff_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)
    assert (local / "added.md").exists()

    # Corrupt into the INDEX_DELETED state: drop the file from index + workdir
    # while HEAD still references it — exactly what the old buggy checkout left.
    local_repo = pygit2.Repository(str(local))
    (local / "added.md").unlink()
    idx = local_repo.index
    idx.remove("added.md")
    idx.write()
    assert local_repo.status().get("added.md", 0) & pygit2.GIT_STATUS_INDEX_DELETED

    # Push one more upstream commit so there is something to fast-forward to.
    (remote / "another.md").write_text("# Another\n", encoding="utf-8")
    _commit_all(remote_repo, "another file")

    # The next sync must restore the previously-missing file AND apply the new one.
    fetch_and_ff_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)
    assert (local / "added.md").exists()
    assert (local / "another.md").exists()
    assert local_repo.status() == {}


def test_fast_forward_preserves_local_uncommitted_changes(tmp_path: Path) -> None:
    """If a tracked file has local edits in the FF diff, the SAFE checkout
    aborts without moving the ref (no half-applied state)."""
    remote = _make_remote(tmp_path)

    repos_dir = tmp_path / "repos"
    ssh_keys_dir = tmp_path / "ssh"
    gitea_dir = tmp_path / "gitea"
    repos_dir.mkdir()
    ssh_keys_dir.mkdir()
    gitea_dir.mkdir()

    entry = {
        "id": "work",
        "remote_url": str(remote),
        "branch": "main",
        "ssh_key_id": None,
        "http_username": None,
        "http_password": None,
    }
    fetch_and_ff_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)
    local = repos_dir / "work"

    # Upstream modifies intro.md.
    remote_repo = pygit2.Repository(str(remote))
    (remote / "intro.md").write_text("# Intro changed upstream\n", encoding="utf-8")
    _commit_all(remote_repo, "upstream edit")

    # Locally, the same file has an uncommitted edit.
    (local / "intro.md").write_text("# Local uncommitted edit\n", encoding="utf-8")
    local_repo = pygit2.Repository(str(local))
    head_before = local_repo.head.target

    fetch_and_ff_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)

    # Ref did not move and the local edit survived.
    assert local_repo.head.target == head_before
    assert (local / "intro.md").read_text(encoding="utf-8") == "# Local uncommitted edit\n"


def test_sync_reclones_incomplete_husk(tmp_path: Path) -> None:
    """A .git husk left by a clone that failed partway (no refs, unborn HEAD)
    must be re-cloned on the next sync, not treated as 'already cloned' and
    left empty forever."""
    remote = _make_remote(tmp_path)

    repos_dir = tmp_path / "repos"
    ssh_keys_dir = tmp_path / "ssh"
    gitea_dir = tmp_path / "gitea"
    repos_dir.mkdir()
    ssh_keys_dir.mkdir()
    gitea_dir.mkdir()

    entry = {
        "id": "work",
        "remote_url": str(remote),
        "branch": "main",
        "ssh_key_id": None,
        "http_username": None,
        "http_password": None,
    }

    # Simulate the broken state: a bare-init repo (a .git dir with an unborn
    # HEAD and no remote refs) sitting where the clone should be — exactly what
    # an interrupted clone leaves behind.
    local = repos_dir / "work"
    pygit2.init_repository(str(local), initial_head="main")
    husk = pygit2.Repository(str(local))
    assert husk.head_is_unborn
    assert "refs/remotes/origin/main" not in list(husk.references)

    # Sync must detect the husk and re-clone it.
    fetch_and_ff_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)

    assert (local / "intro.md").exists()
    healed = pygit2.Repository(str(local))
    assert not healed.head_is_unborn
    assert "refs/remotes/origin/main" in list(healed.references)
    assert healed.status() == {}


def test_clone_lands_on_configured_non_default_branch(tmp_path: Path) -> None:
    """The clone no longer passes checkout_branch (it breaks authenticated
    Gitea over HTTP). When the configured branch is NOT the remote default,
    the post-clone checkout must still move HEAD to it with files materialised."""
    remote = _make_remote(tmp_path)  # default branch: main
    remote_repo = pygit2.Repository(str(remote))

    # Add a second branch 'docs' with a file that doesn't exist on main.
    main_tip = remote_repo.head.peel(pygit2.Commit)
    remote_repo.branches.local.create("docs", main_tip)
    remote_repo.checkout("refs/heads/docs")
    (remote / "guide.md").write_text("# Guide\n", encoding="utf-8")
    _commit_all(remote_repo, "docs-only file")
    # Leave the remote's HEAD on main so the clone's default is main, not docs.
    remote_repo.checkout("refs/heads/main")

    repos_dir = tmp_path / "repos"
    ssh_keys_dir = tmp_path / "ssh"
    gitea_dir = tmp_path / "gitea"
    repos_dir.mkdir()
    ssh_keys_dir.mkdir()
    gitea_dir.mkdir()

    entry = {
        "id": "docs-src",
        "remote_url": str(remote),
        "branch": "docs",
        "ssh_key_id": None,
        "http_username": None,
        "http_password": None,
    }
    fetch_and_ff_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)

    local = repos_dir / "docs-src"
    repo = pygit2.Repository(str(local))
    assert repo.head.name == "refs/heads/docs"
    # The docs-only file is present (HEAD really moved to docs), tree is clean.
    assert (local / "guide.md").exists()
    assert repo.status() == {}


def test_concurrent_clone_of_same_source_does_not_race(tmp_path: Path) -> None:
    """Two clones of the same source must not run at once — the second must
    skip rather than rmtree the first's in-flight directory. Regression for the
    homelab failure where a slow clone outlived the sync interval and the next
    tick deleted the working directory mid-clone ('failed to create locked
    file ...lock')."""
    remote = _make_remote(tmp_path)
    repos_dir = tmp_path / "repos"
    ssh_keys_dir = tmp_path / "ssh"
    gitea_dir = tmp_path / "gitea"
    repos_dir.mkdir()
    ssh_keys_dir.mkdir()
    gitea_dir.mkdir()

    entry = {
        "id": "work",
        "remote_url": str(remote),
        "branch": "main",
        "ssh_key_id": None,
        "http_username": None,
        "http_password": None,
    }

    # Hold the source's sync lock as if a clone were already in flight, then
    # confirm a second clone returns immediately without touching the dir.
    lock = src_store._get_sync_lock("work")
    assert lock.acquire(blocking=False)
    try:
        clone_source_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)
        # The guarded call skipped — nothing was cloned.
        assert not (repos_dir / "work" / ".git").exists()
    finally:
        lock.release()

    # With the lock free, the clone proceeds normally.
    clone_source_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)
    assert (repos_dir / "work" / "intro.md").exists()


def test_sync_lock_released_after_failed_clone(tmp_path: Path) -> None:
    """A clone that raises must still release the per-source lock, or the
    source would be wedged 'in progress' forever and never retry."""
    repos_dir = tmp_path / "repos"
    ssh_keys_dir = tmp_path / "ssh"
    gitea_dir = tmp_path / "gitea"
    repos_dir.mkdir()
    ssh_keys_dir.mkdir()
    gitea_dir.mkdir()

    entry = {
        "id": "bad",
        "remote_url": str(tmp_path / "does-not-exist"),
        "branch": "main",
        "ssh_key_id": None,
        "http_username": None,
        "http_password": None,
    }

    # First fetch attempts a clone of a bogus remote and fails (swallowed by
    # the caller in production; here it raises out of the locked impl).
    try:
        fetch_and_ff_sync(repos_dir, ssh_keys_dir, gitea_dir, entry)
    except Exception:
        pass

    # The lock must be free again and the in-progress flag cleared.
    lock = src_store._get_sync_lock("bad")
    assert lock.acquire(blocking=False), "sync lock not released after a failed clone"
    lock.release()
    assert not src_store.sync_in_progress("bad")
