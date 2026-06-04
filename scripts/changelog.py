"""Generate and update CHANGELOG.md from Conventional Commit history.

This is the *entry point* for cutting a release version. It:

  1. parses the Conventional Commit subjects since the last release tag,
     groups them into Keep-a-Changelog sections (Added / Changed / Fixed / …),
  2. bumps the ``VERSION`` file (``--level major|minor|patch`` or an explicit
     ``--set X.Y.Z``) and propagates it (frontend/package.json) via
     ``sync_version``,
  3. inserts the grouped entries as a new dated section at the top of
     ``CHANGELOG.md`` (creating the file if absent).

This script owns the version bump; ``make release`` orchestrates around it
(check → cut → build → commit → tag → deploy) and reverts the cut if the build
fails. Normally you invoke it via ``make release``, not directly. The usual
flow:

  1. commit your code changes
  2. make release            → prompts for LEVEL, then runs this script, builds,
                               commits VERSION+CHANGELOG, tags, deploys
  3. git push --follow-tags

Modes (mutually exclusive):
  --level / --set   cut a version (prompts for level if neither given)
  --check           exit 0 if there are commits since the last tag, else 1
  --revert          restore VERSION/CHANGELOG/package.json to HEAD (undo a cut)
  --backfill        reseed the whole changelog from every tag (one-off)

Usage:
    python scripts/changelog.py --level minor          # bump + changelog
    python scripts/changelog.py                        # prompt for level
    python scripts/changelog.py --set 2.1.0            # explicit version
    python scripts/changelog.py --level patch --dry-run
    python scripts/changelog.py --check                # any unreleased commits?
    python scripts/changelog.py --revert               # undo an aborted cut
    python scripts/changelog.py --backfill             # seed from all tags
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# sync_version lives alongside this script; reuse its bump + propagate logic so
# the single-source-of-truth rules (semver validation, package.json sync) stay
# in one place.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_version

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"

# Conventional Commit type → changelog section. Anything unmapped (chore,
# build, ci, test, style, refactor without a user-facing effect) is dropped
# from the changelog by default — those aren't release notes.
TYPE_SECTION: dict[str, str] = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Changed",
    "refactor": "Changed",
    "docs": "Documentation",
    "deprecate": "Deprecated",
    "revert": "Removed",
}

# Section display order in the output.
SECTION_ORDER = [
    "Added",
    "Changed",
    "Deprecated",
    "Removed",
    "Fixed",
    "Security",
    "Documentation",
]

# `type(scope)!: subject`  — scope and the breaking `!` are optional.
COMMIT_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s*(?P<subject>.+)$"
)

HEADER = """\
# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries are generated from [Conventional Commits](https://www.conventionalcommits.org)
by `scripts/changelog.py` at release time.
"""


@dataclass
class Section:
    """A parsed set of changelog entries grouped by section name."""

    entries: dict[str, list[str]] = field(default_factory=dict)
    breaking: list[str] = field(default_factory=list)

    def add(self, section: str, line: str) -> None:
        self.entries.setdefault(section, []).append(line)

    def is_empty(self) -> bool:
        return not self.entries and not self.breaking


def _run(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _tags_chronological() -> list[str]:
    """All ``vX.Y.Z`` tags, oldest first."""
    out = _run(
        "for-each-ref", "--sort=creatordate", "--format=%(refname:short)", "refs/tags"
    )
    return [t for t in out.splitlines() if re.match(r"^v\d+\.\d+\.\d+$", t)]


def _commits_between(old: str | None, new: str) -> list[str]:
    """Commit subjects in (old, new]; if old is None, everything up to new."""
    rev = f"{old}..{new}" if old else new
    out = _run("log", "--no-merges", "--format=%s", rev)
    return [line for line in out.splitlines() if line.strip()]


def parse_commits(subjects: list[str]) -> Section:
    """Group Conventional Commit subjects into changelog sections."""
    section = Section()
    for subj in subjects:
        m = COMMIT_RE.match(subj)
        if not m:
            continue
        ctype = m.group("type")
        scope = m.group("scope")
        bang = m.group("bang")
        text = m.group("subject").strip()
        # Prefix the scope so readers know which surface changed.
        line = f"**{scope}:** {text}" if scope else text
        if bang:
            section.breaking.append(line)
        target = TYPE_SECTION.get(ctype)
        if target:
            section.add(target, line)
    return section


def _last_tag() -> str | None:
    tags = _tags_chronological()
    return tags[-1] if tags else None


def unreleased_commits() -> list[str]:
    """Commit subjects since the last release tag (all of them, not just CC)."""
    return _commits_between(_last_tag(), "HEAD")


def render_section(version: str, when: str, section: Section) -> str:
    """Render one ``## [version] - date`` block."""
    lines = [f"## [{version}] - {when}"]
    if section.breaking:
        lines.append("")
        lines.append("### ⚠ BREAKING CHANGES")
        lines.append("")
        lines.extend(f"- {b}" for b in section.breaking)
    for name in SECTION_ORDER:
        items = section.entries.get(name)
        if not items:
            continue
        lines.append("")
        lines.append(f"### {name}")
        lines.append("")
        lines.extend(f"- {item}" for item in items)
    if section.is_empty():
        lines.append("")
        lines.append("_No user-facing changes._")
    lines.append("")
    return "\n".join(lines)


def _read_existing_body() -> str:
    """Return the changelog content below the header, or '' if no file."""
    if not CHANGELOG.exists():
        return ""
    text = CHANGELOG.read_text(encoding="utf-8")
    # Everything from the first '## ' onward is prior release blocks.
    idx = text.find("\n## ")
    return text[idx + 1 :] if idx != -1 else ""


def write_changelog(new_block: str, *, prepend_to_existing: bool) -> None:
    body = _read_existing_body() if prepend_to_existing else ""
    parts = [HEADER, "", new_block.rstrip(), ""]
    if body.strip():
        parts.append(body.rstrip() + "\n")
    CHANGELOG.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def backfill() -> int:
    """Reconstruct the whole changelog from every tag. Does not touch VERSION."""
    tags = _tags_chronological()
    if not tags:
        raise SystemExit("no version tags found to backfill from")
    blocks: list[str] = []
    prev: str | None = None
    for tag in tags:
        version = tag.lstrip("v")
        when = _run("log", "-1", "--format=%ad", "--date=short", tag)
        section = parse_commits(_commits_between(prev, tag))
        blocks.append(render_section(version, when, section))
        prev = tag
    # Newest first.
    body = "\n".join(reversed(blocks))
    CHANGELOG.write_text(HEADER + "\n" + body.rstrip() + "\n", encoding="utf-8")
    print(f"backfilled {len(tags)} versions into {CHANGELOG.relative_to(ROOT)}")
    return 0


# Files the version cut touches; reverted together if a release build fails.
RELEASE_FILES = ["VERSION", "CHANGELOG.md", "frontend/package.json"]


def prompt_level(current: str) -> str:
    """Ask the user which level to bump, showing the resulting version."""
    print(f"current version: {current}")
    print("select the next version:")
    for short, key in (("p", "patch"), ("m", "minor"), ("j", "major")):
        print(f"  {short}) {key:<6} → {sync_version.bump(current, key)}")
    aliases = {
        "p": "patch",
        "patch": "patch",
        "m": "minor",
        "minor": "minor",
        "j": "major",  # 'major' shares its first letter with 'minor'; use 'j'
        "major": "major",
    }
    while True:
        choice = input("level — patch / minor / major (or q): ").strip().lower()
        if choice in ("q", "quit", ""):
            raise SystemExit("aborted")
        if choice in aliases:
            return aliases[choice]
        print("  please answer patch / minor / major (or q)")


def check() -> int:
    """Exit 0 if there are commits since the last tag, 1 otherwise."""
    commits = unreleased_commits()
    last = _last_tag() or "(repo start)"
    if commits:
        print(f"{len(commits)} commit(s) since {last}:")
        for c in commits:
            print(f"  - {c}")
        return 0
    print(f"no commits since {last} — nothing to release")
    return 1


def _is_tracked(path: str) -> bool:
    """True if *path* is tracked in git (vs. untracked / not yet committed)."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def revert() -> int:
    """Undo an aborted cut: restore each release file to its pre-cut state.

    Tracked files are checked out from HEAD; an untracked file (e.g. the very
    first CHANGELOG.md) is removed, since "before the cut" means it didn't
    exist. Handling them separately matters — ``git checkout -- <untracked>``
    errors and would otherwise abort the whole revert.
    """
    done: list[str] = []
    for f in RELEASE_FILES:
        if _is_tracked(f):
            _run("checkout", "HEAD", "--", f)
            done.append(f)
        elif (ROOT / f).exists():
            (ROOT / f).unlink()
            done.append(f"{f} (removed)")
    print(f"reverted: {', '.join(done) or '(nothing to revert)'}")
    return 0


def cut(level: str | None, set_to: str | None, dry_run: bool) -> int:
    current = sync_version.read_version()
    if set_to:
        if not sync_version.SEMVER_RE.match(set_to):
            raise SystemExit(f"--set value {set_to!r} is not semver")
        new = set_to
    elif level:
        new = sync_version.bump(current, level)
    else:
        # No level given — ask interactively (the single-command release flow).
        new = sync_version.bump(current, prompt_level(current))

    section = parse_commits(_commits_between(_last_tag(), "HEAD"))
    block = render_section(new, date.today().isoformat(), section)

    print(f"VERSION: {current} → {new}")
    print(f"--- new CHANGELOG section ---\n{block}")
    if dry_run:
        print("(dry-run: no files written)")
        return 0

    sync_version.write_version(new)
    sync_version.update_package_json(new)
    write_changelog(block, prepend_to_existing=True)
    print(f"wrote VERSION, frontend/package.json, {CHANGELOG.relative_to(ROOT)}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--level", choices=["major", "minor", "patch"], help="bump level")
    g.add_argument("--set", dest="set_to", metavar="X.Y.Z", help="explicit version")
    g.add_argument(
        "--backfill", action="store_true", help="seed changelog from all tags"
    )
    g.add_argument(
        "--check", action="store_true", help="exit 0 if commits since last tag, else 1"
    )
    g.add_argument(
        "--revert",
        action="store_true",
        help="restore VERSION/CHANGELOG/package.json to HEAD",
    )
    p.add_argument("--dry-run", action="store_true", help="print, don't write")
    args = p.parse_args()

    if args.backfill:
        return backfill()
    if args.check:
        return check()
    if args.revert:
        return revert()
    return cut(args.level, args.set_to, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
