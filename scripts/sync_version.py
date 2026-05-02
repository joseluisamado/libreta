"""Synchronise the canonical VERSION file across the project.

The single source of truth is the top-level ``VERSION`` file (plain text,
contents are a single semver string). This script propagates that value to:

  - backend/pyproject.toml  (the [project] version field)
  - frontend/package.json   (the "version" field)

It can also bump the version per ``--bump {major,minor,patch}`` and write the
result back to ``VERSION`` before propagating.

Usage:
    uv run python scripts/sync_version.py                # propagate current
    uv run python scripts/sync_version.py --bump patch   # bump then propagate
    uv run python scripts/sync_version.py --set 0.2.0    # set explicit value
    uv run python scripts/sync_version.py --print        # print current

The script is idempotent and safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
PYPROJECT = ROOT / "backend" / "pyproject.toml"
PACKAGE_JSON = ROOT / "frontend" / "package.json"

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def read_version() -> str:
    if not VERSION_FILE.exists():
        raise SystemExit(f"VERSION file missing at {VERSION_FILE}")
    text = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not SEMVER_RE.match(text):
        raise SystemExit(f"VERSION ({text!r}) is not semver MAJOR.MINOR.PATCH")
    return text


def write_version(v: str) -> None:
    if not SEMVER_RE.match(v):
        raise SystemExit(f"refusing to write non-semver version {v!r}")
    VERSION_FILE.write_text(f"{v}\n", encoding="utf-8")


def bump(current: str, level: str) -> str:
    m = SEMVER_RE.match(current)
    if not m:
        raise SystemExit(f"current version {current!r} not semver")
    major, minor, patch = (int(g) for g in m.groups())
    if level == "major":
        major, minor, patch = major + 1, 0, 0
    elif level == "minor":
        minor, patch = minor + 1, 0
    elif level == "patch":
        patch += 1
    else:
        raise SystemExit(f"unknown bump level: {level}")
    return f"{major}.{minor}.{patch}"


def update_pyproject(v: str) -> bool:
    """Update the [project] version line. Returns True if file changed."""
    if not PYPROJECT.exists():
        print(f"warn: {PYPROJECT} missing — skipping", file=sys.stderr)
        return False
    text = PYPROJECT.read_text(encoding="utf-8")
    new = re.sub(
        r'(?m)^(version\s*=\s*)"[^"]*"',
        rf'\g<1>"{v}"',
        text,
        count=1,
    )
    if new == text:
        return False
    PYPROJECT.write_text(new, encoding="utf-8")
    return True


def update_package_json(v: str) -> bool:
    if not PACKAGE_JSON.exists():
        print(f"warn: {PACKAGE_JSON} missing — skipping", file=sys.stderr)
        return False
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    if data.get("version") == v:
        return False
    data["version"] = v
    # Preserve trailing newline + 2-space indent (npm/pnpm convention)
    PACKAGE_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--bump", choices=["major", "minor", "patch"])
    g.add_argument("--set", dest="set_to", metavar="X.Y.Z")
    g.add_argument("--print", action="store_true", dest="just_print")
    args = parser.parse_args()

    current = read_version()
    if args.just_print:
        print(current)
        return 0

    if args.bump:
        new = bump(current, args.bump)
        write_version(new)
        print(f"VERSION: {current} → {new}")
        current = new
    elif args.set_to:
        if not SEMVER_RE.match(args.set_to):
            raise SystemExit(f"--set value {args.set_to!r} is not semver")
        write_version(args.set_to)
        print(f"VERSION: {current} → {args.set_to}")
        current = args.set_to

    py_changed = update_pyproject(current)
    js_changed = update_package_json(current)

    print(f"version: {current}")
    print(f"  backend/pyproject.toml  {'updated' if py_changed else 'already in sync'}")
    print(f"  frontend/package.json   {'updated' if js_changed else 'already in sync'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
