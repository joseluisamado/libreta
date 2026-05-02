from __future__ import annotations

from collections import Counter
from pathlib import Path

from libreta.tagging import (
    build_corpus_df,
    good_term,
    score_page,
    strip_markup,
    tokenize,
)


class DescribeTokenize:
    def it_returns_lowercase_tokens(self) -> None:
        assert tokenize("Hello World FooBar") == ["hello", "world", "foobar"]

    def it_skips_short_tokens(self) -> None:
        assert "ab" not in tokenize("ab cd efgh")

    def it_matches_words_with_digits(self) -> None:
        assert "utf8" in tokenize("utf8 support")

    def it_matches_accented_letters(self) -> None:
        assert "café" in tokenize("un café au lait")


class DescribeStripMarkup:
    def it_removes_fenced_code_blocks(self) -> None:
        text = "intro\n```python\nprint('hi')\n```\noutro"
        assert "print" not in strip_markup(text)
        assert "intro" in strip_markup(text)
        assert "outro" in strip_markup(text)

    def it_removes_inline_code(self) -> None:
        text = "use the `foo.bar()` function"
        assert "foo.bar" not in strip_markup(text)
        assert "use the" in strip_markup(text)

    def it_removes_links(self) -> None:
        text = "see [the docs](https://example.com) for more"
        assert "example.com" not in strip_markup(text)
        assert "the docs" not in strip_markup(text)
        assert "see" in strip_markup(text) and "for more" in strip_markup(text)

    def it_removes_images(self) -> None:
        text = "diagram ![alt](img.png) here"
        assert "img.png" not in strip_markup(text)
        assert "diagram" in strip_markup(text) and "here" in strip_markup(text)

    def it_removes_standalone_urls(self) -> None:
        text = "visit https://foo.com/bar today"
        assert "foo.com" not in strip_markup(text)
        assert "visit" in strip_markup(text) and "today" in strip_markup(text)


class DescribeGoodTerm:
    def it_rejects_stopwords(self) -> None:
        assert not good_term("the")
        assert not good_term("and")

    def it_rejects_short_terms(self) -> None:
        assert not good_term("ab")

    def it_rejects_long_terms(self) -> None:
        assert not good_term("a" * 100)

    def it_rejects_numeric(self) -> None:
        assert not good_term("123")

    def it_accepts_normal_words(self) -> None:
        assert good_term("python")
        assert good_term("deployment")


class DescribeScorePage:
    def it_returns_top_terms(self) -> None:
        tf = Counter({"python": 5, "async": 3, "server": 2, "fast": 2, "config": 1, "test": 1})
        df = Counter({"python": 3, "async": 2, "server": 2, "fast": 1, "config": 1, "test": 1})
        tags = score_page(tf, df, n_docs=5)
        assert 2 <= len(tags) <= 5
        # "test" is the least distinctive (df=1, tf=1) — should be first dropped
        assert "test" not in tags

    def it_dedupes_stems(self) -> None:
        tf = Counter({"pythons": 3, "python": 2})
        df = Counter({"pythons": 2, "python": 1})
        tags = score_page(tf, df, n_docs=2)
        # Should only keep one of pythons/python
        assert len([t for t in tags if t.startswith("python")]) <= 1


class DescribeBuildCorpusDf:
    def it_returns_counter_and_count(self, tmp_path: Path) -> None:
        pages = tmp_path / "pages"
        pages.mkdir(parents=True, exist_ok=True)
        (pages / "a.md").write_text("---\ntitle: Alpha\n---\n\npython async\n")
        (pages / "b.md").write_text("---\ntitle: Beta\n---\n\npython server\n")

        df, n_docs = build_corpus_df(tmp_path)
        assert n_docs == 2
        assert df["python"] == 2
        assert df["async"] == 1
        assert df["server"] == 1
