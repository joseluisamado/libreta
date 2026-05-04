"""Import a real DokuWiki installation into Libreta's content layout.

Source layout (DokuWiki on disk):

    storage/data/
    ├── pages/<namespace>/<page>.txt          # DokuWiki syntax
    ├── media/<namespace>/<file>              # uploaded files
    └── meta/<namespace>/<page>.changes       # tab-separated edit history

Target (Libreta), one namespace becomes one directory under pages/. Pages with
attachments referenced via DokuWiki's media-namespace are promoted to
``<page>.md`` and the referenced media files are copied into a sidecar ``.<page>.md/``, so the
page is self-contained:

    pages/
    ├── faang/big-o.md
    ├── faang/.big-o.md/recursive_runtimes.svg
    ├── faang/.big-o.md/Amortized_Analysis_Explained.pdf
    └── hardware/ps3_backups.md
        hardware/.ps3_backups.md/20251127-182450.png
        ...

Pages with no media attachments are written as plain ``<page>.md``.

Skipped namespaces: ``playground``, ``wiki``, plus the top-level admin pages
``start.txt``, ``sidebar.txt``, ``scratch.txt`` (configurable via --skip).

Run via:

    uv run python scripts/import_dokuwiki.py \\
        --source /path/to/dokuwiki/storage/data \\
        [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path("./dokuwiki/storage/data")
DEFAULT_DEST = PROJECT_ROOT / "data" / "content" / "pages"

DEFAULT_SKIP_NAMESPACES = {"playground", "wiki"}
DEFAULT_SKIP_TOP_PAGES = {"start", "sidebar", "scratch"}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico"}


# ---------- DokuWiki → markdown converter ----------


def _resolve_relative(rest: str, page_namespace: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve a relative DokuWiki id where ``..:`` walks up one namespace.

    DokuWiki uses dot-segments rather than slashes: ``.:foo`` is current
    namespace + foo, ``..:foo`` is parent + foo, ``...:foo`` is grandparent.
    """
    parts = list(rest.split(":"))
    base = list(page_namespace)
    while parts and parts[0] == "":
        # Each empty leading segment caused by extra dots = pop one level.
        if base:
            base.pop()
        parts.pop(0)
    return tuple(base + [p for p in parts if p])


def _resolve_media_id(
    media_id: str, page_namespace: tuple[str, ...]
) -> tuple[str, ...]:
    """Resolve a DokuWiki media id (colon-separated) into namespace parts."""
    media_id = media_id.strip()
    if media_id.startswith("."):
        # ".:foo" → current ns + foo; "..:foo" → parent ns + foo; etc.
        # Strip the run of dots and any colon that follows.
        match = re.match(r"^(\.+):?(.*)$", media_id)
        if match:
            dots, rest = match.groups()
            up = len(dots) - 1
            base = list(page_namespace)
            for _ in range(up):
                if base:
                    base.pop()
            return tuple(base + [p for p in rest.split(":") if p])
    if media_id.startswith(":"):
        return tuple(p for p in media_id[1:].split(":") if p)
    return tuple(p for p in media_id.split(":") if p)


def _resolve_page_id(page_id: str, page_namespace: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve a DokuWiki page id into target path segments (namespace + slug)."""
    page_id = page_id.strip()
    if page_id.startswith("."):
        match = re.match(r"^(\.+):?(.*)$", page_id)
        if match:
            dots, rest = match.groups()
            up = len(dots) - 1
            base = list(page_namespace)
            for _ in range(up):
                if base:
                    base.pop()
            return tuple(base + [p for p in rest.split(":") if p])
    if page_id.startswith(":"):
        return tuple(p for p in page_id[1:].split(":") if p)
    if ":" not in page_id:
        return (*page_namespace, page_id)
    return tuple(page_id.split(":"))


class Converter:
    """Convert one DokuWiki page (.txt) to GFM markdown.

    Stateful: ``media_used`` accumulates resolved media path-tuples so the
    importer knows which files to copy into the destination.
    """

    def __init__(self, page_namespace: tuple[str, ...]):
        self.page_namespace = page_namespace
        self.media_used: list[tuple[str, ...]] = []

    # --- block-level passes ---

    def convert(self, text: str) -> str:
        # 1. Protect fenced code (DokuWiki <code>/<file>) before any other
        #    transform so syntax inside isn't mangled.
        placeholders: list[str] = []

        def stash(match: re.Match[str]) -> str:
            tag = match.group(1)  # 'code' or 'file'
            lang = (match.group(2) or "").strip()
            body = match.group(3)
            fence = (
                f"```{lang}\n{body.rstrip()}\n```"
                if tag == "code"
                else (f"```\n{body.rstrip()}\n```")
            )
            placeholders.append(fence)
            return f"\x00BLOCK{len(placeholders) - 1}\x00"

        text = re.sub(
            r"<(code|file)(?:\s+([^>]*))?>(.*?)</\1>",
            stash,
            text,
            flags=re.DOTALL,
        )

        # 2. Strip <nowiki> wrappers (keep the inner text verbatim)
        text = re.sub(r"</?nowiki>", "", text)

        # 3. Convert headings (DokuWiki uses LARGER `=` for HIGHER level)
        #    ====== H1 ======   →   # H1
        #    ===== H2 =====     →   ## H2
        #    ==== H3 ====       →   ### H3
        #    === H4 ===         →   #### H4
        #    == H5 ==           →   ##### H5
        def heading_sub(match: re.Match[str]) -> str:
            equals = match.group(1)
            title = match.group(2).strip()
            level = max(1, 7 - len(equals))
            return f"{'#' * level} {title}"

        text = re.sub(
            r"^(={2,6})\s*(.+?)\s*\1\s*$", heading_sub, text, flags=re.MULTILINE
        )

        # 4. Lists. DokuWiki uses 2-space indents:
        #       "  * item"   →   "- item"
        #       "  - item"   →   "1. item"
        #    Each extra 2 spaces = one more nesting level → 2 markdown spaces.
        def list_sub(match: re.Match[str]) -> str:
            indent = match.group(1)
            marker = match.group(2)
            content = match.group(3)
            depth = (len(indent) - 2) // 2  # 0 for "  *"
            md_indent = "  " * depth
            md_marker = "1." if marker == "-" else "-"
            return f"{md_indent}{md_marker} {content}"

        text = re.sub(r"^(  +)([*-])\s+(.*)$", list_sub, text, flags=re.MULTILINE)

        # 5. Inline transforms

        # 5a. Media: {{ ns:file?size |caption }}
        text = re.sub(r"\{\{([^}|]+)(?:\|([^}]*))?\}\}", self._media_sub, text)

        # 5b. Wikilinks: [[target|text]] or [[target]]
        text = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", self._link_sub, text)

        # 5c. Bold (same syntax)        — leave **...** alone
        # 5d. Italic //...// → *...*    (avoid eating http://, file paths)
        text = re.sub(
            r"(?<![:/])//(?!/)([^\n/][^\n]*?)//(?!/)",
            r"*\1*",
            text,
        )

        # 5e. Monospace ''...'' → `...`
        text = re.sub(r"''([^']+)''", r"`\1`", text)

        # 5f. Underline __...__ → drop the markers (no markdown equivalent)
        text = re.sub(r"__([^_]+)__", r"\1", text)

        # 5g. Strikethrough <del>...</del> → ~~...~~
        text = re.sub(r"<del>(.+?)</del>", r"~~\1~~", text)

        # 5h. Forced line break: \\<space> at end of line
        text = re.sub(r"\\\\(?=\s)", "  ", text)

        # 6. Tables: ^h1^h2^ … and |r1|r2|. Convert blocks of these lines.
        text = self._convert_tables(text)

        # 7. Restore code blocks
        for i, block in enumerate(placeholders):
            text = text.replace(f"\x00BLOCK{i}\x00", block)

        # 8. Tighten consecutive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip() + "\n"

    # --- helpers ---

    def _media_sub(self, match: re.Match[str]) -> str:
        raw_id = match.group(1).strip()
        caption = (match.group(2) or "").strip()

        # Strip size hint after `?` (e.g., "?200x50", "?50", "?linkonly")
        media_id, _, _ = raw_id.partition("?")
        # PDF/anchor fragment after `#` (e.g., "#page=149") — preserve so
        # links to PDFs can scroll to the right page.
        media_id, _, fragment = media_id.partition("#")
        media_id = media_id.strip()

        # External URL — leave it as a plain image
        if media_id.startswith(("http://", "https://")):
            alt = caption or ""
            return f"![{alt}]({media_id})"

        # Skip RSS/dynamic embeds (rare; appear as `rss>...`)
        if media_id.startswith(("rss>", "iframe>")):
            return ""

        ns_parts = _resolve_media_id(media_id, self.page_namespace)
        if not ns_parts:
            return match.group(0)

        self.media_used.append(ns_parts)
        filename = ns_parts[-1]
        ext = Path(filename).suffix.lower()
        alt = caption or filename
        # Files end up colocated with the page; reference by basename.
        href = filename + (f"#{fragment}" if fragment else "")
        if ext in IMAGE_EXTS:
            return f"![{alt}]({href})"
        return f"[{alt}]({href})"

    def _link_sub(self, match: re.Match[str]) -> str:
        target = match.group(1).strip()
        label = (match.group(2) or "").strip()

        # External URL
        if target.startswith(("http://", "https://", "mailto:", "ftp://")):
            return f"[{label or target}]({target})"

        # Same-page anchor: [[#anchor]] / [[#anchor|text]]
        if target.startswith("#"):
            return f"[{label or target[1:]}]({target.lower().replace(' ', '-')})"

        # Interwiki (doku>, wp>, etc.) — keep as plain text in brackets so it's
        # clear something used to live there but isn't navigable here.
        if ">" in target:
            return label or target

        # Windows share \\server\share — leave verbatim
        if target.startswith("\\\\"):
            return label or target

        # Internal page link, possibly with #anchor
        page_id, _, anchor = target.partition("#")
        parts = _resolve_page_id(page_id, self.page_namespace)
        url = "/w/" + "/".join(parts)
        if anchor:
            url += "#" + anchor.lower().replace(" ", "-")
        text = label or page_id.replace(":", " / ")
        return f"[{text}]({url})"

    def _convert_tables(self, text: str) -> str:
        lines = text.split("\n")
        out: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.lstrip().startswith(("^", "|")) and re.search(r"[\^|]\s*$", line):
                # collect contiguous table block
                block: list[str] = []
                while i < len(lines) and lines[i].lstrip().startswith(("^", "|")):
                    block.append(lines[i])
                    i += 1
                out.extend(self._render_table(block))
                continue
            out.append(line)
            i += 1
        return "\n".join(out)

    def _render_table(self, block: list[str]) -> list[str]:
        rows: list[tuple[bool, list[str]]] = []
        for line in block:
            line = line.rstrip()
            is_header = line.lstrip().startswith("^")
            # split on either separator
            cells = re.split(r"[\^|]", line)
            cells = [c.strip() for c in cells[1:-1]]  # drop empty edges
            if not cells:
                continue
            rows.append((is_header, cells))

        if not rows:
            return block

        # determine header
        if rows[0][0]:
            header = rows[0][1]
            body = [r[1] for r in rows[1:]]
        else:
            cols = len(rows[0][1])
            header = [""] * cols
            body = [r[1] for r in rows]

        cols = max(len(header), *(len(r) for r in body)) if body else len(header)
        header = header + [""] * (cols - len(header))
        body = [r + [""] * (cols - len(r)) for r in body]

        out = ["| " + " | ".join(header) + " |", "|" + "|".join([" --- "] * cols) + "|"]
        out.extend("| " + " | ".join(r) + " |" for r in body)
        out.append("")
        return out


# ---------- Importer ----------


def parse_changes(
    meta_dir: Path, ns_parts: tuple[str, ...]
) -> tuple[datetime | None, datetime | None]:
    """Return (created, updated) from the .changes file for a page."""
    if not ns_parts:
        return None, None
    changes = meta_dir.joinpath(*ns_parts).with_suffix(".changes")
    if not changes.exists():
        return None, None
    timestamps: list[int] = []
    for line in changes.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if not parts or not parts[0].isdigit():
            continue
        timestamps.append(int(parts[0]))
    if not timestamps:
        return None, None
    return (
        datetime.fromtimestamp(timestamps[0], tz=timezone.utc),
        datetime.fromtimestamp(timestamps[-1], tz=timezone.utc),
    )


def title_from_body(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip() or fallback
        if line:
            break
    return fallback


def humanise(slug: str) -> str:
    return slug.replace("_", " ").replace("-", " ").title()


def build_frontmatter(
    title: str, created: datetime | None, updated: datetime | None, tags: list[str]
) -> str:
    lines = ["---", f'title: "{title}"']
    if created:
        lines.append(f"created: {created.isoformat()}")
    if updated:
        lines.append(f"updated: {updated.isoformat()}")
    if tags:
        lines.append("tags: [" + ", ".join(tags) + "]")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + "\n"


def iter_pages(
    pages_dir: Path, skip_ns: set[str], skip_top: set[str]
) -> Iterable[Path]:
    for path in sorted(pages_dir.rglob("*.txt")):
        rel = path.relative_to(pages_dir)
        parts = rel.parts
        if parts[0] in skip_ns:
            continue
        if len(parts) == 1 and rel.stem in skip_top:
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="DokuWiki data dir (default: %(default)s)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help="Libreta pages dir (default: %(default)s)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-namespace",
        action="append",
        default=[],
        help="Additional top-level namespace to skip",
    )
    args = parser.parse_args()

    src: Path = args.source.resolve()
    dst: Path = args.dest.resolve()
    pages_dir = src / "pages"
    media_dir = src / "media"
    meta_dir = src / "meta"

    if not pages_dir.is_dir():
        print(f"source not found: {pages_dir}", file=sys.stderr)
        return 2

    skip_ns = DEFAULT_SKIP_NAMESPACES | set(args.skip_namespace)
    pages = list(iter_pages(pages_dir, skip_ns, DEFAULT_SKIP_TOP_PAGES))
    print(f"importing {len(pages)} pages from {pages_dir} → {dst}")
    if args.dry_run:
        print("(dry run — no files written)")

    pages_written = 0
    media_copied = 0
    for src_page in pages:
        rel = src_page.relative_to(pages_dir)
        ns_parts = rel.parts[:-1]
        stem = rel.stem
        ns_path_for_meta = (*ns_parts, stem)

        body = src_page.read_text(encoding="utf-8", errors="replace")
        conv = Converter(page_namespace=ns_parts)
        md_body = conv.convert(body)

        title = title_from_body(md_body, humanise(stem))
        created, updated = parse_changes(meta_dir, ns_path_for_meta)
        if not updated:
            updated = datetime.fromtimestamp(src_page.stat().st_mtime, tz=timezone.utc)
        if not created:
            created = updated

        # Resolve media files this page actually uses
        media_files: list[tuple[Path, str]] = []  # (source, dest_basename)
        seen_basenames: set[str] = set()
        for ns in conv.media_used:
            candidate = media_dir.joinpath(*ns)
            if not candidate.exists():
                print(
                    f"  warn: missing media {':'.join(ns)} referenced by {rel}",
                    file=sys.stderr,
                )
                continue
            base = candidate.name
            if base in seen_basenames:
                continue
            seen_basenames.add(base)
            media_files.append((candidate, base))

        # New model: every .md file stands alone.  Pages with media get a
        # hidden sidecar directory (``.<stem>.md/``) for attachments.
        page_dir = dst.joinpath(*ns_parts)
        md_dest = page_dir / f"{stem}.md"
        sidecar_dir = page_dir / f".{stem}.md"

        out = build_frontmatter(title, created, updated, ["imported"]) + md_body
        rel_md = md_dest.relative_to(dst)
        print(f"  {rel}  →  {rel_md}")

        if not args.dry_run:
            md_dest.parent.mkdir(parents=True, exist_ok=True)
            md_dest.write_text(out, encoding="utf-8")

        for src_file, base in media_files:
            asset_dest = sidecar_dir / base
            print(f"      asset: {asset_dest.relative_to(dst)}")
            if not args.dry_run:
                asset_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, asset_dest)
            media_copied += 1

        pages_written += 1

    print(f"\ndone: {pages_written} pages, {media_copied} media files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
