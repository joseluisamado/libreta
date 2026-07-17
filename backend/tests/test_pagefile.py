"""Unit tests for non-page file classification (_classify_other)."""

from pathlib import Path

import pytest

from libreta.errors import FrontmatterInBodyError
from libreta.storage.pagefile import (
    _as_weight,
    _body_looks_like_frontmatter,
    _classify_other,
    _read_webloc_url,
    read_h1_or_fallback,
    read_page_file,
    read_page_head,
    read_weight,
    sanitize_page_meta,
    walk_children,
    write_page_file,
)

_WEBLOC_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    '<plist version="1.0">\n'
    "<dict><key>URL</key><string>{url}</string></dict>\n"
    "</plist>\n"
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("photo.png", "image"),
        ("PHOTO.JPG", "image"),
        ("diagram.drawio.svg", "drawio"),
        ("diagram.drawio.png", "drawio"),
        # HTML gets its own kind: it is rendered (JS-stripped) in a dedicated
        # viewer, not shown as raw source like other text. See R6.
        ("index.html", "html"),
        ("page.HTM", "html"),
        ("notes.txt", "text"),
        ("style.css", "text"),
        ("Dockerfile", "text"),
        ("archive.zip", "binary"),
        ("data.bin", "binary"),
    ],
)
def test_classify_other(name: str, expected: str) -> None:
    assert _classify_other(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("clip.mp4", "video"),
        ("clip.webm", "video"),
        ("clip.MOV", "video"),
        ("photo.heic", "image"),  # rendered by Safari; broken elsewhere (no decode)
        ("photo.HEIF", "image"),
    ],
)
def test_classify_video_and_heic(name: str, expected: str) -> None:
    assert _classify_other(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # All e-reader formats map to a single "ebook" kind; foliate-js sniffs
        # the concrete format client-side.
        ("book.epub", "ebook"),
        ("BOOK.EPUB", "ebook"),
        ("classic.mobi", "ebook"),
        ("kindle.azw3", "ebook"),
        ("kindle.azw", "ebook"),
        ("old.prc", "ebook"),
        ("story.fb2", "ebook"),
        ("story.fb2.zip", "ebook"),
        ("story.fbz", "ebook"),
        ("comic.cbz", "ebook"),
        # Not e-books: a plain zip stays binary.
        ("archive.zip", "binary"),
    ],
)
def test_classify_ebook(name: str, expected: str) -> None:
    assert _classify_other(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("bookmark.webloc", "weblink"),
        ("Bookmark.WEBLOC", "weblink"),
        # A generic .plist is still text, not a weblink.
        ("settings.plist", "text"),
    ],
)
def test_classify_weblink(name: str, expected: str) -> None:
    assert _classify_other(name) == expected


def test_read_webloc_url_xml(tmp_path: Path) -> None:
    f = tmp_path / "link.webloc"
    f.write_text(_WEBLOC_XML.format(url="https://example.com/page"))
    assert _read_webloc_url(f) == "https://example.com/page"


def test_read_webloc_url_binary(tmp_path: Path) -> None:
    import plistlib

    f = tmp_path / "link.webloc"
    f.write_bytes(plistlib.dumps({"URL": "https://example.org"}, fmt=plistlib.FMT_BINARY))
    assert _read_webloc_url(f) == "https://example.org"


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "javascript:alert(1)", "ftp://host/x", ""],
)
def test_read_webloc_url_rejects_unsafe(tmp_path: Path, url: str) -> None:
    f = tmp_path / "link.webloc"
    f.write_text(_WEBLOC_XML.format(url=url))
    assert _read_webloc_url(f) is None


def test_read_webloc_url_malformed(tmp_path: Path) -> None:
    f = tmp_path / "broken.webloc"
    f.write_text("not a plist at all")
    assert _read_webloc_url(f) is None


def test_weblink_is_first_class_child_with_target(tmp_path: Path) -> None:
    """A .webloc is a clickable child node carrying its resolved target URL,
    not a thumbnail-bearing previewable and not an other_file."""
    (tmp_path / "page.md").write_text("# Page\n")
    (tmp_path / "site.webloc").write_text(_WEBLOC_XML.format(url="https://example.com"))

    nodes, other = walk_children(tmp_path, "")

    by_name = {n.filename: n for n in nodes}
    assert by_name["site.webloc"].kind == "weblink"
    assert by_name["site.webloc"].target == "https://example.com"
    assert "site.webloc" not in {o.name for o in other}


def test_previewable_files_are_children_not_other_files(tmp_path: Path) -> None:
    """Files with a viewer + thumbnail (image, drawio, text, html, video) are
    first-class child nodes; only non-previewable binaries land in other_files."""
    (tmp_path / "page.md").write_text("# Page\n")
    (tmp_path / "photo.png").write_bytes(b"\x89PNG")
    (tmp_path / "chart.drawio.svg").write_text("<svg/>")
    (tmp_path / "notes.txt").write_text("hi")
    (tmp_path / "report.html").write_text("<p>x</p>")
    (tmp_path / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftyp")
    (tmp_path / "novel.epub").write_bytes(b"PK\x03\x04")
    (tmp_path / "comic.cbz").write_bytes(b"PK\x03\x04")
    (tmp_path / "archive.zip").write_bytes(b"PK")

    nodes, other = walk_children(tmp_path, "")

    kinds = {n.filename: n.kind for n in nodes}
    assert kinds["photo.png"] == "image"
    assert kinds["chart.drawio.svg"] == "drawio"
    assert kinds["notes.txt"] == "text"
    assert kinds["report.html"] == "html"
    assert kinds["clip.mp4"] == "video"
    assert kinds["novel.epub"] == "ebook"
    assert kinds["comic.cbz"] == "ebook"
    assert "page.md" in kinds  # the markdown page is still a node

    # Only the genuinely non-previewable binary remains in other_files.
    assert {o.name for o in other} == {"archive.zip"}


# ---------------------------------------------------------------------------
# Frontmatter round-trip: unknown keys must survive a write
# ---------------------------------------------------------------------------


def test_write_preserves_unknown_frontmatter_keys(tmp_path: Path) -> None:
    """A key Libreta doesn't model (e.g. ``weight``, arbitrary user keys) must
    survive a write. This is the contract the sidebar-``weight`` feature relies
    on: without it, adding ``weight`` to a page and later editing it through
    Libreta would silently drop the ordering (ARCHITECTURE.md: unknown keys are
    preserved on roundtrip)."""
    (tmp_path / "foo.md").write_text(
        "---\ntitle: Foo\nweight: 20\ncustom_key: keepme\n---\nOriginal body\n"
    )

    write_page_file(tmp_path, "foo.md", "Edited body")

    page = read_page_file(tmp_path, "foo.md")
    assert page.body == "Edited body"
    assert page.meta.weight == 20
    # The unmodelled key is still on disk (read back through the raw frontmatter).
    import frontmatter

    meta = frontmatter.load(tmp_path / "foo.md").metadata
    assert meta["custom_key"] == "keepme"
    assert meta["weight"] == 20


def test_read_surfaces_weight(tmp_path: Path) -> None:
    (tmp_path / "p.md").write_text("---\ntitle: P\nweight: 30\n---\n# P\n")
    assert read_page_file(tmp_path, "p.md").meta.weight == 30


def test_read_absent_weight_is_none(tmp_path: Path) -> None:
    (tmp_path / "p.md").write_text("---\ntitle: P\n---\n# P\n")
    assert read_page_file(tmp_path, "p.md").meta.weight is None


# ---------------------------------------------------------------------------
# weight coercion (_as_weight): malformed input must degrade to None, not throw
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (20, 20),
        (0, 0),
        (-5, -5),  # negative is allowed: sorts ahead of positives ("pin to top")
        ("30", 30),  # numeric string from YAML
        ("  40  ", 40),  # surrounding whitespace tolerated
        (None, None),  # absent
        ("notanint", None),  # unparseable → treated as absent
        ("", None),
        (1.5, None),  # float is not an int weight → treated as absent
        (True, None),  # bool rejected (YAML true/false are int subclasses)
        (False, None),
        ([1, 2], None),  # nonsense type → absent, not a crash
    ],
)
def test_as_weight_coercion(value: object, expected: int | None) -> None:
    assert _as_weight(value) == expected


# ---------------------------------------------------------------------------
# Sidebar ordering by weight
# ---------------------------------------------------------------------------


def _write_page(dir_path: Path, name: str, weight: object = None) -> None:
    fm = "---\ntitle: " + name
    if weight is not None:
        fm += f"\nweight: {weight}"
    fm += "\n---\n# " + name + "\n"
    (dir_path / f"{name}.md").write_text(fm)


def _order(tmp_path: Path) -> list[str]:
    nodes, _ = walk_children(tmp_path, "")
    return [n.filename for n in nodes]


def test_order_all_weighted_beats_filename_sort(tmp_path: Path) -> None:
    """The motivating case: a pedagogical sequence whose filenames sort wrong.
    ``callable_protocol_and_call`` must land last (weight 60), not second."""
    for name, w in [
        ("args_and_kwargs", 10),
        ("closures_and_free_variables", 20),
        ("decorators", 30),
        ("functools", 40),
        ("lambda_functions", 50),
        ("callable_protocol_and_call", 60),
    ]:
        _write_page(tmp_path, name, w)

    assert _order(tmp_path) == [
        "args_and_kwargs.md",
        "closures_and_free_variables.md",
        "decorators.md",
        "functools.md",
        "lambda_functions.md",
        "callable_protocol_and_call.md",
    ]


def test_order_none_weighted_is_unchanged_filename_sort(tmp_path: Path) -> None:
    """A folder with no weights must look exactly as it does today: pure
    case-folded filename order. This is what makes folder-by-folder adoption
    safe — an untouched folder does not visibly change."""
    for name in ["banana", "Apple", "cherry"]:
        _write_page(tmp_path, name)

    # casefold sort: Apple, banana, cherry
    assert _order(tmp_path) == ["Apple.md", "banana.md", "cherry.md"]


def test_order_mixed_weighted_first_then_alphabetical(tmp_path: Path) -> None:
    """Documented mixed-folder rule: weighted pages first in weight order, then
    unweighted pages alphabetically."""
    _write_page(tmp_path, "zzz", 5)  # weighted
    _write_page(tmp_path, "aaa", 15)  # weighted
    _write_page(tmp_path, "yankee")  # unweighted
    _write_page(tmp_path, "bravo")  # unweighted

    assert _order(tmp_path) == ["zzz.md", "aaa.md", "bravo.md", "yankee.md"]


def test_order_duplicate_weights_break_by_filename(tmp_path: Path) -> None:
    """Equal weights are not an error; they tie-break by filename, stably."""
    _write_page(tmp_path, "ccc", 10)
    _write_page(tmp_path, "aaa", 10)
    _write_page(tmp_path, "bbb", 20)

    assert _order(tmp_path) == ["aaa.md", "ccc.md", "bbb.md"]


def test_order_malformed_weight_treated_as_absent(tmp_path: Path) -> None:
    """A malformed weight must not throw or reorder unrelated pages — the page
    falls back to the unweighted (filename) bucket."""
    _write_page(tmp_path, "good", 10)
    _write_page(tmp_path, "broken", "notanint")  # malformed → absent
    _write_page(tmp_path, "plain")  # genuinely absent

    # good (weighted) first; broken + plain fall to alphabetical.
    assert _order(tmp_path) == ["good.md", "broken.md", "plain.md"]


def test_order_negative_weight_pins_to_top(tmp_path: Path) -> None:
    _write_page(tmp_path, "intro", -10)
    _write_page(tmp_path, "middle", 10)
    _write_page(tmp_path, "outro", 20)

    assert _order(tmp_path) == ["intro.md", "middle.md", "outro.md"]


# ---------------------------------------------------------------------------
# Setting frontmatter via the write meta channel
# ---------------------------------------------------------------------------


def test_write_sets_weight_via_meta_on_create(tmp_path: Path) -> None:
    """A brand-new page can be given a weight through the meta channel — the key
    doesn't have to pre-exist in the file (the roundtrip fix only copies keys
    forward; meta is the inbound channel for new managed values)."""
    write_page_file(tmp_path, "p.md", "# P\n", sanitize_page_meta({"weight": 10}))
    assert read_page_file(tmp_path, "p.md").meta.weight == 10


def test_write_updates_weight_via_meta(tmp_path: Path) -> None:
    (tmp_path / "p.md").write_text("---\ntitle: P\nweight: 10\n---\n# P\n")
    write_page_file(tmp_path, "p.md", "# P edited\n", sanitize_page_meta({"weight": 30}))
    page = read_page_file(tmp_path, "p.md")
    assert page.meta.weight == 30
    assert "# P edited" in page.body


def test_write_clears_weight_via_meta_null(tmp_path: Path) -> None:
    (tmp_path / "p.md").write_text("---\ntitle: P\nweight: 10\n---\n# P\n")
    write_page_file(tmp_path, "p.md", "# P\n", sanitize_page_meta({"weight": None}))
    assert read_page_file(tmp_path, "p.md").meta.weight is None


def test_write_meta_cannot_set_created_or_updated(tmp_path: Path) -> None:
    """created/updated are writer-owned; a caller's meta must not stomp them."""
    (tmp_path / "p.md").write_text("---\ntitle: P\ncreated: 2020-01-01T00:00:00+00:00\n---\n# P\n")
    write_page_file(
        tmp_path,
        "p.md",
        "# P\n",
        sanitize_page_meta({"created": "1999-01-01", "updated": "1999-01-01"}),
    )
    page = read_page_file(tmp_path, "p.md")
    # created preserved from the file (not the 1999 value the caller tried to set)
    assert page.meta.created is not None
    assert page.meta.created.year == 2020


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({"weight": 10}, {"weight": 10}),
        ({"weight": "20"}, {"weight": 20}),
        ({"weight": "bad"}, {"weight": None}),  # malformed → clear, not raise
        ({"weight": None}, {"weight": None}),
        ({"tags": ["a", "b"]}, {"tags": ["a", "b"]}),
        ({"tags": "solo"}, {"tags": ["solo"]}),
        ({"title": "Hi"}, {"title": "Hi"}),
        ({"title": "   "}, {}),  # blank title dropped
        ({"created": "2020", "updated": "2020"}, {}),  # writer-owned, dropped
        ({"unknown_key": "x"}, {}),  # not settable, dropped
        (None, {}),
        ({}, {}),
    ],
)
def test_sanitize_page_meta(meta: dict[str, object] | None, expected: dict[str, object]) -> None:
    assert sanitize_page_meta(meta) == expected


# ---------------------------------------------------------------------------
# Frontmatter-in-body guard
# ---------------------------------------------------------------------------


def test_write_rejects_frontmatter_in_body(tmp_path: Path) -> None:
    """A body opening with a frontmatter fence is a caller mistake — reject it
    rather than persist the YAML as visible page content."""
    with pytest.raises(FrontmatterInBodyError):
        write_page_file(tmp_path, "p.md", "---\nweight: 10\n---\n\n# P\n")
    # Nothing was written.
    assert not (tmp_path / "p.md").exists()


@pytest.mark.parametrize(
    ("body", "looks_like_fm"),
    [
        ("---\nweight: 10\n---\n\n# P\n", True),  # classic frontmatter block
        ("\n\n---\ntitle: x\n---\nbody", True),  # leading blank lines tolerated
        ("---\nkey: v\n...\nbody", True),  # YAML '...' terminator counts as close
        ("---\n\nJust a thematic break, no closing fence.\n", False),  # HR, allowed
        ("# Heading\n\n---\n\nmore", False),  # HR mid-document, not at top
        ("Normal body\n", False),
        ("", False),
    ],
)
def test_body_looks_like_frontmatter(body: str, looks_like_fm: bool) -> None:
    assert _body_looks_like_frontmatter(body) is looks_like_fm


# ---------------------------------------------------------------------------
# read_page_head: single-pass reader for weight + sidebar title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        # frontmatter weight + body H1
        ("---\ntitle: T\nweight: 20\n---\n\n# Real Heading\n\nbody\n", (20, "Real Heading")),
        # no frontmatter, leading H1
        ("# Just H1\n\nbody\n", (None, "Just H1")),
        # weight but no H1 → fallback title
        ("---\nweight: 5\n---\n\nJust a paragraph.\n", (5, "FB")),
        # leading blank lines before frontmatter are tolerated
        ("\n\n---\nweight: 7\n---\n\n# After Blanks\n", (7, "After Blanks")),
        # H2 first (not an H1) → fallback
        ("## Secondary\n\ntext\n", (None, "FB")),
        # empty file
        ("", (None, "FB")),
        # blank line *inside* the frontmatter block must not corrupt parsing
        ("---\ntitle: T\n\nweight: 9\n---\n# Heading\n", (9, "Heading")),
        # malformed weight → None, title still read
        ("---\nweight: notanint\n---\n# H\n", (None, "H")),
    ],
)
def test_read_page_head(tmp_path: Path, content: str, expected: tuple[int | None, str]) -> None:
    f = tmp_path / "p.md"
    f.write_text(content)
    assert read_page_head(f, "FB") == expected


def test_read_page_head_unreadable_file(tmp_path: Path) -> None:
    # A missing file degrades to (None, fallback), never raises.
    assert read_page_head(tmp_path / "nope.md", "FB") == (None, "FB")


def test_wrappers_delegate_to_head(tmp_path: Path) -> None:
    """read_weight / read_h1_or_fallback are thin wrappers over read_page_head."""
    f = tmp_path / "p.md"
    f.write_text("---\nweight: 40\n---\n\n# The Title\n")
    assert read_weight(f) == 40
    assert read_h1_or_fallback(f, "FB") == "The Title"
