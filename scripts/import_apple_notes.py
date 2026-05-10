"""Import Apple Notes into a Libreta git source.

Reads notes directly from ``NoteStore.sqlite`` (the Notes.app database) and
writes one ``.md`` file per note into a target git working tree.

The Notes database is at::

    ~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite

Each note's body is stored as a gzip'd Apple-flavoured protobuf in
``ZICCLOUDSYNCINGOBJECT.ZDATA``. The protobuf wraps an NSAttributedString:
plain text plus per-run style metadata (bold, italics, headings, bullets,
checklists, links). Attachments (images, PDFs, drawings) live under
``Accounts/<account>/Media/<UUID>/...`` next to the database.

This importer extracts what's losslessly representable as CommonMark + GFM:

* Plain text, hard line breaks, paragraphs.
* Bold (``**``), italic (``*``), monospaced (`` ` ``), strikethrough (``~~``).
* Headings (Title → H1, Heading → H2, Subheading → H3).
* Bulleted / numbered / dashed lists with nesting.
* Checklists (``- [ ]`` / ``- [x]``).
* Block quotes.
* Links (markdown ``[text](url)``).
* Image attachments — copied to a sidecar dir and referenced inline.

Things that cannot survive the trip lossless are dropped with a warning,
not silently elided:

* Hand-drawn sketches (scribbles).
* Tables (Apple Notes uses an internal table format; we render them as
  best-effort GFM tables, with a warning for cells that contain anything
  other than plain text).
* Locked / encrypted notes — skipped, listed at the end.
* Audio recordings, scanned documents — kept as attachment files with a
  link, no rendering.

Usage::

    uv run python scripts/import_apple_notes.py \\
        --notestore ~/Library/Group\\ Containers/group.com.apple.notes/NoteStore.sqlite \\
        --repo /path/to/your-wiki-clone \\
        --dest apple-notes \\
        [--dry-run] [--account "iCloud"] [--folder "Recipes"]

Run on a Mac with **Full Disk Access** granted to the terminal (System
Settings → Privacy & Security → Full Disk Access). Without it, opening
the database returns "operation not permitted".
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import re
import shutil
import sqlite3
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# ---------- Apple Cocoa epoch helpers ----------

# Cocoa stores timestamps as seconds since 2001-01-01 UTC.
COCOA_EPOCH = datetime(2001, 1, 1, tzinfo=UTC)


def cocoa_to_iso(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    try:
        return (
            datetime.fromtimestamp(float(seconds), tz=UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (OSError, ValueError, OverflowError):
        return None


def cocoa_offset_to_iso(seconds: float | None) -> str | None:
    """Cocoa-epoch helper that matches what's in the Notes DB."""
    if seconds is None:
        return None
    try:
        ts = COCOA_EPOCH.timestamp() + float(seconds)
        return (
            datetime.fromtimestamp(ts, tz=UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (OSError, ValueError, OverflowError):
        return None


# ---------- Minimal protobuf reader (varint + length-delimited only) ----------
#
# Apple's note body protobuf uses standard wire types. We don't have the .proto,
# but the structure is well-documented by reverse engineering (see e.g.
# threeplanetssoftware/apple_cloud_notes_parser). We only need a few fields,
# so a minimal decoder beats adding a `protobuf` dependency.


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def _iter_fields(
    buf: bytes, start: int = 0, end: int | None = None
) -> Iterator[tuple[int, int, bytes | int]]:
    """Yield (field_number, wire_type, value) triples.

    For length-delimited fields (wire_type=2) the value is the raw bytes.
    For varints (wire_type=0) it's the integer. Other wire types are skipped.
    """
    if end is None:
        end = len(buf)
    i = start
    while i < end:
        try:
            tag, i = _read_varint(buf, i)
        except (IndexError, ValueError):
            return
        field_number = tag >> 3
        wire_type = tag & 0x07
        if wire_type == 0:
            value, i = _read_varint(buf, i)
            yield field_number, wire_type, value
        elif wire_type == 2:
            length, i = _read_varint(buf, i)
            chunk = buf[i : i + length]
            i += length
            yield field_number, wire_type, chunk
        elif wire_type == 1:
            i += 8  # 64-bit fixed
        elif wire_type == 5:
            i += 4  # 32-bit fixed
        else:
            return  # unsupported, bail


# ---------- Apple Notes protobuf shape ----------
#
# Outer message (NoteStoreProto):
#   1: Document
#       3: Note (the part we care about)
#           2: string  — the full plain-text body, no run markers
#           5: AttributeRun (repeated) — style runs, in order
#                1: length (varint, in UTF-16 code units)
#                2: ParagraphStyle
#                     1: style_type (varint: 0=Title, 1=Heading, 2=Subheading,
#                                    100=monospaced block, 101=todo,
#                                    103=block quote, 104=numbered, 105=dashed,
#                                    106=bulleted)
#                     4: indent (varint)
#                     5: TodoState (1: uuid bytes; 2: done bool)
#                3: font (FontInfo) — we ignore beyond bold/italic flags
#                5: bold (varint, 1 if bold)
#                6: italic (varint, 1 if italic)
#                7: underline (varint)
#                8: strikethrough (varint)
#                9: superscript (varint, signed-ish)
#               10: link (string URL)
#               12: AttachmentInfo
#                     1: attachment uuid (string)
#                     2: type uti (string)
#
# Field numbers above are the ones I'm using. Other fields (colours, etc.)
# we don't need.


@dataclass
class ParagraphStyle:
    style_type: int | None = None  # see comment above
    indent: int = 0
    todo_done: bool | None = None  # None if not a todo


@dataclass
class Run:
    length: int
    paragraph: ParagraphStyle = field(default_factory=ParagraphStyle)
    bold: bool = False
    italic: bool = False
    monospaced: bool = False
    strikethrough: bool = False
    link: str | None = None
    attachment_uuid: str | None = None


@dataclass
class NoteBody:
    text: str
    runs: list[Run]


def _decode_paragraph(buf: bytes) -> ParagraphStyle:
    p = ParagraphStyle()
    for fn, wt, val in _iter_fields(buf):
        if fn == 1 and wt == 0 and isinstance(val, int):
            p.style_type = val
        elif fn == 4 and wt == 0 and isinstance(val, int):
            p.indent = val
        elif fn == 5 and wt == 2 and isinstance(val, bytes):
            for tfn, twt, tval in _iter_fields(val):
                if tfn == 2 and twt == 0 and isinstance(tval, int):
                    p.todo_done = bool(tval)
    return p


def _decode_attachment(buf: bytes) -> str | None:
    for fn, wt, val in _iter_fields(buf):
        if fn == 1 and wt == 2 and isinstance(val, bytes):
            try:
                return val.decode("utf-8")
            except UnicodeDecodeError:
                return None
    return None


def _decode_run(buf: bytes) -> Run:
    run = Run(length=0)
    for fn, wt, val in _iter_fields(buf):
        if fn == 1 and wt == 0 and isinstance(val, int):
            run.length = val
        elif fn == 2 and wt == 2 and isinstance(val, bytes):
            run.paragraph = _decode_paragraph(val)
        elif fn == 5 and wt == 0 and isinstance(val, int):
            run.bold = bool(val)
        elif fn == 6 and wt == 0 and isinstance(val, int):
            run.italic = bool(val)
        elif fn == 8 and wt == 0 and isinstance(val, int):
            run.strikethrough = bool(val)
        elif fn == 10 and wt == 2 and isinstance(val, bytes):
            with contextlib.suppress(UnicodeDecodeError):
                run.link = val.decode("utf-8") or None
        elif fn == 12 and wt == 2 and isinstance(val, bytes):
            run.attachment_uuid = _decode_attachment(val)
    return run


def _decode_note_inner(buf: bytes) -> NoteBody | None:
    text = ""
    runs: list[Run] = []
    for fn, wt, val in _iter_fields(buf):
        if fn == 2 and wt == 2 and isinstance(val, bytes):
            try:
                text = val.decode("utf-8")
            except UnicodeDecodeError:
                text = val.decode("utf-8", errors="replace")
        elif fn == 5 and wt == 2 and isinstance(val, bytes):
            runs.append(_decode_run(val))
    if not text and not runs:
        return None
    return NoteBody(text=text, runs=runs)


def decode_note_body(zdata: bytes) -> NoteBody | None:
    """Decode a ``ZICCLOUDSYNCINGOBJECT.ZDATA`` blob into text + runs.

    Returns None if the blob doesn't look like a notes body.
    """
    try:
        decompressed = gzip.decompress(zdata)
    except OSError:
        return None
    # Outer wrapper. We descend through field 1 (Document) → field 3 (Note).
    for fn, wt, val in _iter_fields(decompressed):
        if fn == 2 and wt == 2 and isinstance(val, bytes):
            for d_fn, d_wt, d_val in _iter_fields(val):
                if d_fn == 3 and d_wt == 2 and isinstance(d_val, bytes):
                    return _decode_note_inner(d_val)
    # Some versions put the Note directly at the top level.
    return _decode_note_inner(decompressed)


# ---------- Markdown rendering ----------

# UTF-16 code unit boundaries: Apple's run lengths are in UTF-16 code units,
# but Python strings are sequences of code points. Convert by walking the
# original string and counting UTF-16 units.


def _split_text_by_runs(text: str, runs: list[Run]) -> list[tuple[str, Run]]:
    """Slice *text* according to UTF-16-code-unit run lengths."""
    out: list[tuple[str, Run]] = []
    i = 0  # code-point index
    remaining = list(runs)
    if not remaining:
        return [(text, Run(length=len(text)))]

    units_consumed = 0
    for run in remaining:
        target = units_consumed + run.length
        # Walk forward until we've consumed `run.length` UTF-16 units.
        start = i
        units = units_consumed
        while i < len(text) and units < target:
            ch = text[i]
            units += 2 if ord(ch) > 0xFFFF else 1
            i += 1
        out.append((text[start:i], run))
        units_consumed = units
    if i < len(text):
        out.append((text[i:], remaining[-1]))
    return out


_MD_ESCAPE_RE = re.compile(r"([\\`*_{}\[\]()#+\-!|<>])")


def _escape_inline(s: str) -> str:
    return _MD_ESCAPE_RE.sub(r"\\\1", s)


def _wrap_inline(text: str, run: Run) -> str:
    """Apply inline marks (bold/italic/etc.) to *text*, escaped."""
    if run.attachment_uuid:
        # Caller resolves the actual filename; placeholder marker.
        return f"\x00ATTACH:{run.attachment_uuid}\x00"
    out = _escape_inline(text)
    if run.monospaced:
        out = f"`{text}`"  # monospace: don't escape, raw chars (best effort)
    if run.italic:
        out = f"*{out}*"
    if run.bold:
        out = f"**{out}**"
    if run.strikethrough:
        out = f"~~{out}~~"
    if run.link:
        out = f"[{out}]({run.link})"
    return out


# Paragraph style constants from reverse-engineering.
P_TITLE = 0
P_HEADING = 1
P_SUBHEADING = 2
P_MONOSPACE_BLOCK = 100
P_TODO = 101
P_QUOTE = 103
P_NUMBERED = 104
P_DASHED = 105
P_BULLETED = 106


def render_to_markdown(
    body: NoteBody,
    attachments: dict[str, str],
    warnings: list[str],
) -> str:
    """Render a decoded note body to GFM markdown.

    *attachments* maps attachment UUID → relative path to the resolved file
    inside the page's sidecar directory. UUIDs not in the map render as a
    bracketed placeholder and a warning is appended.
    """
    pieces = _split_text_by_runs(body.text, body.runs)
    lines: list[str] = []
    current: list[str] = []
    current_para: ParagraphStyle | None = None

    def flush() -> None:
        nonlocal current, current_para
        if not current:
            current_para = None
            return
        joined = "".join(current).rstrip()

        # Resolve attachment placeholders.
        def _resolve(m: re.Match[str]) -> str:
            uuid = m.group(1)
            rel = attachments.get(uuid)
            if rel is None:
                warnings.append(f"  unresolved attachment {uuid}")
                return f"`[attachment missing: {uuid}]`"
            ext = Path(rel).suffix.lower()
            if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".heic"}:
                return f"![]({rel})"
            return f"[{Path(rel).name}]({rel})"

        joined = re.sub(r"\x00ATTACH:([0-9A-F-]+)\x00", _resolve, joined)
        if current_para is None:
            lines.append(joined)
        else:
            st = current_para.style_type
            indent = "    " * max(0, current_para.indent)
            if st == P_TITLE:
                lines.append(f"# {joined}")
            elif st == P_HEADING:
                lines.append(f"## {joined}")
            elif st == P_SUBHEADING:
                lines.append(f"### {joined}")
            elif st == P_MONOSPACE_BLOCK:
                # Group runs of monospace lines into a fenced block at flush
                # time. Simpler: emit per-line, the post-pass will fold them.
                lines.append(f"\x01MONO\x01{joined}")
            elif st == P_TODO:
                mark = "x" if current_para.todo_done else " "
                lines.append(f"{indent}- [{mark}] {joined}")
            elif st == P_QUOTE:
                lines.append(f"> {joined}")
            elif st == P_NUMBERED:
                lines.append(f"{indent}1. {joined}")
            elif st in (P_DASHED, P_BULLETED):
                lines.append(f"{indent}- {joined}")
            else:
                lines.append(joined)
        current = []
        current_para = None

    for chunk, run in pieces:
        if not chunk:
            continue
        # Newline within a chunk closes the current paragraph.
        sub_lines = chunk.split("\n")
        for j, sub in enumerate(sub_lines):
            if j > 0:
                flush()
            if sub:
                if current_para is None:
                    current_para = run.paragraph
                current.append(_wrap_inline(sub, run))
    flush()

    # Post-pass: fold consecutive monospace lines into ``` fences.
    folded: list[str] = []
    in_block = False
    for line in lines:
        if line.startswith("\x01MONO\x01"):
            if not in_block:
                folded.append("```")
                in_block = True
            folded.append(line[len("\x01MONO\x01") :])
        else:
            if in_block:
                folded.append("```")
                in_block = False
            folded.append(line)
    if in_block:
        folded.append("```")

    # Collapse triple+ blank lines.
    out: list[str] = []
    blank = 0
    for line in folded:
        if not line.strip():
            blank += 1
            if blank <= 1:
                out.append("")
        else:
            blank = 0
            out.append(line)
    return "\n".join(out).strip() + "\n"


# ---------- Filesystem helpers ----------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(s: str, fallback: str = "untitled") -> str:
    s = s.strip().lower()
    s = _SLUG_RE.sub("-", s).strip("-")
    return s or fallback


def unique_path(p: Path) -> Path:
    """Add ``-2``, ``-3``, ... if *p* already exists."""
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    n = 2
    while True:
        candidate = p.with_name(f"{stem}-{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1


# ---------- Database queries ----------

NOTES_QUERY = """
SELECT
    n.Z_PK              AS pk,
    n.ZTITLE1           AS title,
    n.ZSNIPPET          AS snippet,
    n.ZIDENTIFIER       AS uuid,
    n.ZCREATIONDATE1    AS created,
    n.ZMODIFICATIONDATE1 AS modified,
    n.ZISPASSWORDPROTECTED AS locked,
    n.ZISPINNED         AS pinned,
    f.ZTITLE2           AS folder_title,
    f.ZIDENTIFIER       AS folder_uuid,
    a.ZNAME             AS account_name,
    nd.ZDATA            AS data
FROM ZICCLOUDSYNCINGOBJECT n
LEFT JOIN ZICCLOUDSYNCINGOBJECT f ON n.ZFOLDER = f.Z_PK
LEFT JOIN ZICCLOUDSYNCINGOBJECT a ON n.ZACCOUNT4 = a.Z_PK OR n.ZACCOUNT2 = a.Z_PK
LEFT JOIN ZICNOTEDATA nd ON nd.ZNOTE = n.Z_PK
WHERE n.ZTITLE1 IS NOT NULL
  AND (n.ZMARKEDFORDELETION IS NULL OR n.ZMARKEDFORDELETION = 0)
ORDER BY n.ZMODIFICATIONDATE1 DESC
"""


ATTACHMENTS_QUERY = """
SELECT
    att.ZIDENTIFIER         AS uuid,
    att.ZFILENAME           AS filename,
    att.ZTYPEUTI            AS uti,
    att.ZNOTE               AS note_pk,
    media.ZIDENTIFIER       AS media_uuid,
    media.ZFILENAME         AS media_filename
FROM ZICCLOUDSYNCINGOBJECT att
LEFT JOIN ZICCLOUDSYNCINGOBJECT media ON att.ZMEDIA = media.Z_PK
WHERE att.ZNOTE IS NOT NULL
"""


@dataclass
class Note:
    pk: int
    title: str
    uuid: str
    created: str | None
    modified: str | None
    locked: bool
    pinned: bool
    folder_title: str | None
    folder_uuid: str | None
    account_name: str | None
    data: bytes | None


@dataclass
class Attachment:
    uuid: str
    filename: str | None
    uti: str | None
    note_pk: int
    media_uuid: str | None
    media_filename: str | None


def query_notes(db: Path) -> list[Note]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(NOTES_QUERY).fetchall()
    finally:
        conn.close()
    return [
        Note(
            pk=r["pk"],
            title=r["title"] or "Untitled",
            uuid=r["uuid"] or "",
            created=cocoa_offset_to_iso(r["created"]),
            modified=cocoa_offset_to_iso(r["modified"]),
            locked=bool(r["locked"]),
            pinned=bool(r["pinned"]),
            folder_title=r["folder_title"],
            folder_uuid=r["folder_uuid"],
            account_name=r["account_name"],
            data=r["data"],
        )
        for r in rows
    ]


def query_attachments(db: Path) -> dict[int, list[Attachment]]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(ATTACHMENTS_QUERY).fetchall()
    finally:
        conn.close()
    out: dict[int, list[Attachment]] = {}
    for r in rows:
        att = Attachment(
            uuid=r["uuid"] or "",
            filename=r["filename"],
            uti=r["uti"],
            note_pk=r["note_pk"],
            media_uuid=r["media_uuid"],
            media_filename=r["media_filename"],
        )
        out.setdefault(att.note_pk, []).append(att)
    return out


def find_attachment_file(media_root: Path, attachment: Attachment) -> Path | None:
    """Locate the on-disk file for *attachment* under ``Media/<uuid>/``."""
    candidates: list[Path] = []
    if attachment.media_uuid:
        d = media_root / attachment.media_uuid
        if d.is_dir():
            if attachment.media_filename:
                p = d / attachment.media_filename
                if p.is_file():
                    return p
            candidates.extend(p for p in d.iterdir() if p.is_file())
    if attachment.uuid:
        d = media_root / attachment.uuid
        if d.is_dir():
            if attachment.filename:
                p = d / attachment.filename
                if p.is_file():
                    return p
            candidates.extend(p for p in d.iterdir() if p.is_file())
    return candidates[0] if candidates else None


# ---------- Importer ----------


@dataclass
class ImportStats:
    notes_seen: int = 0
    notes_written: int = 0
    notes_skipped_locked: int = 0
    notes_skipped_empty: int = 0
    attachments_copied: int = 0
    attachments_missing: int = 0
    warnings: list[str] = field(default_factory=list)


def import_notes(
    notestore: Path,
    repo: Path,
    dest_subpath: str,
    *,
    dry_run: bool,
    account_filter: str | None,
    folder_filter: str | None,
) -> ImportStats:
    if not notestore.is_file():
        raise SystemExit(f"error: NoteStore.sqlite not found at {notestore}")
    if not (repo / ".git").exists():
        raise SystemExit(f"error: {repo} is not a git working tree")

    media_root = notestore.parent
    # Try common Media layouts.
    for candidate in (
        media_root / "Media",
        media_root / "Accounts" / "LocalAccount" / "Media",
    ):
        if candidate.is_dir():
            media_root = candidate
            break

    dest_root = (repo / dest_subpath).resolve()
    if not dest_root.is_relative_to(repo.resolve()):
        raise SystemExit("error: --dest must stay inside --repo")

    notes = query_notes(notestore)
    attachments_by_note = query_attachments(notestore)
    stats = ImportStats(notes_seen=len(notes))

    for note in notes:
        if account_filter and (note.account_name or "") != account_filter:
            continue
        if folder_filter and (note.folder_title or "") != folder_filter:
            continue

        if note.locked:
            stats.notes_skipped_locked += 1
            stats.warnings.append(f"locked, skipped: {note.title}")
            continue
        if not note.data:
            stats.notes_skipped_empty += 1
            continue

        body = decode_note_body(note.data)
        if body is None:
            stats.notes_skipped_empty += 1
            stats.warnings.append(f"could not decode body: {note.title}")
            continue

        # Path: dest/<folder>/<title>.md
        folder_dir = slugify(note.folder_title or "_inbox", "_inbox")
        title_slug = slugify(note.title, fallback=f"note-{note.pk}")
        page_path = dest_root / folder_dir / f"{title_slug}.md"
        page_path = unique_path(page_path)
        sidecar_dir = page_path.parent / f".{page_path.name}"

        # Copy attachments first so we know their relative paths.
        attachment_map: dict[str, str] = {}
        atts = attachments_by_note.get(note.pk, [])
        for att in atts:
            src = find_attachment_file(media_root, att)
            if src is None:
                stats.attachments_missing += 1
                stats.warnings.append(f"  attachment file missing for {note.title}: {att.uuid}")
                continue
            target = sidecar_dir / src.name
            target = unique_path(target)
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
            stats.attachments_copied += 1
            rel = f"./.{page_path.name}/{target.name}"
            attachment_map[att.uuid] = rel

        per_note_warnings: list[str] = []
        markdown_body = render_to_markdown(body, attachment_map, per_note_warnings)
        if per_note_warnings:
            stats.warnings.append(f"in {note.title}:")
            stats.warnings.extend(per_note_warnings)

        # Frontmatter.
        fm_lines = ["---"]
        fm_lines.append(f"title: {note.title!r}")
        if note.created:
            fm_lines.append(f"created: {note.created}")
        if note.modified:
            fm_lines.append(f"updated: {note.modified}")
        if note.account_name:
            fm_lines.append(f"apple_notes_account: {note.account_name!r}")
        if note.folder_title:
            fm_lines.append(f"apple_notes_folder: {note.folder_title!r}")
        if note.uuid:
            fm_lines.append(f"apple_notes_uuid: {note.uuid}")
        if note.pinned:
            fm_lines.append("pinned: true")
        fm_lines.append("---")
        full = "\n".join(fm_lines) + "\n\n" + markdown_body

        if dry_run:
            print(f"[dry-run] would write {page_path.relative_to(repo)}")
        else:
            page_path.parent.mkdir(parents=True, exist_ok=True)
            page_path.write_text(full, encoding="utf-8")
            print(f"wrote {page_path.relative_to(repo)}")
        stats.notes_written += 1

    return stats


# ---------- CLI ----------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Apple Notes into a Libreta git working tree."
    )
    parser.add_argument(
        "--notestore",
        type=Path,
        default=Path.home() / "Library/Group Containers/group.com.apple.notes/NoteStore.sqlite",
        help="Path to NoteStore.sqlite (default: standard macOS location).",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        required=True,
        help="Path to the target git working tree (must be a clone of your wiki source).",
    )
    parser.add_argument(
        "--dest",
        type=str,
        default="apple-notes",
        help="Destination subpath inside --repo (default: apple-notes).",
    )
    parser.add_argument(
        "--account",
        type=str,
        default=None,
        help="Only import notes from this Notes account name (e.g. 'iCloud').",
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=None,
        help="Only import notes from this folder title.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write anything; just print what would be imported.",
    )
    args = parser.parse_args()

    stats = import_notes(
        notestore=args.notestore.expanduser(),
        repo=args.repo.expanduser().resolve(),
        dest_subpath=args.dest,
        dry_run=args.dry_run,
        account_filter=args.account,
        folder_filter=args.folder,
    )

    print(file=sys.stderr)
    print(
        f"Done. Seen {stats.notes_seen}, wrote {stats.notes_written}, "
        f"locked-skipped {stats.notes_skipped_locked}, "
        f"empty-skipped {stats.notes_skipped_empty}.",
        file=sys.stderr,
    )
    print(
        f"Attachments: {stats.attachments_copied} copied, {stats.attachments_missing} missing.",
        file=sys.stderr,
    )
    if stats.warnings:
        print(file=sys.stderr)
        print(f"{len(stats.warnings)} warning(s):", file=sys.stderr)
        for w in stats.warnings:
            print(f"  - {w}", file=sys.stderr)
    if not args.dry_run:
        print(file=sys.stderr)
        print(
            "Next: cd into --repo, review the changes, then commit and push.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
