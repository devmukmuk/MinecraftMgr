"""Tests for the screenshot gallery page renderer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from minecraftmgr.models.screenshot_match import ScreenshotMatch
from minecraftmgr.services.gallery_service import build_gallery, render_gallery


def _matched(realm: str, version: str, filename: str) -> ScreenshotMatch:
    return ScreenshotMatch(
        filename=filename,
        taken_at=datetime(2026, 8, 17, 14, 30, 0),
        realm=realm,
        minecraft_version=version,
        relative_path=f"{realm}/{version}/{filename}",
        matched=True,
    )


def _unmatched(filename: str) -> ScreenshotMatch:
    return ScreenshotMatch(
        filename=filename,
        taken_at=None,
        realm=None,
        minecraft_version=None,
        relative_path=f"_unsorted/{filename}",
        matched=False,
    )


def test_render_gallery_includes_realm_and_version_filters() -> None:
    """Each distinct realm/version gets its own filter checkbox."""

    html = render_gallery(
        [
            _matched("gravestone", "26.1.2", "a.png"),
            _matched("cave", "1.21.1", "b.png"),
        ]
    )

    assert 'data-filter="realm" value="gravestone"' in html
    assert 'data-filter="realm" value="cave"' in html
    assert 'data-filter="version" value="26.1.2"' in html
    assert 'data-filter="version" value="1.21.1"' in html


def test_render_gallery_card_references_relative_image_path() -> None:
    """Each card's <img src> points one level up at the organized-tree file."""

    html = render_gallery([_matched("gravestone", "26.1.2", "shot.png")])

    assert '<img src="../gravestone/26.1.2/shot.png"' in html


def test_render_gallery_unmatched_uses_unsorted_label() -> None:
    """An unmatched entry is grouped under the 'Unsorted' realm filter."""

    html = render_gallery([_unmatched("mystery.png")])

    assert 'data-filter="realm" value="Unsorted"' in html
    assert 'data-realm="Unsorted"' in html


def test_render_gallery_footer_links_the_shared_logo_and_copyright() -> None:
    """The gallery footer points at the picker site's logo and shows the copyright line."""

    html = render_gallery([])

    assert '<img class="footer-logo" src="https://minecraft.gamenightbymike.com/logo.png?v=1"' in html
    assert "&copy; 2026 Game Night by Mike." in html


def test_render_gallery_disables_browser_caching_of_the_page() -> None:
    """The gallery ships no-cache meta tags so a rebuilt manifest isn't hidden behind a stale cache."""

    html = render_gallery([])

    assert '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">' in html


def test_render_gallery_empty_manifest_still_renders_shell() -> None:
    """An empty manifest still produces a valid page shell, no cards."""

    html = render_gallery([])

    assert "Screenshot Gallery" in html
    assert "<article" not in html
    assert "0 screenshot(s)" in html


def test_build_gallery_writes_file(tmp_path: Path) -> None:
    """build_gallery writes the rendered page to the given output path, creating parent dirs."""

    output = tmp_path / "_screenshots" / "report" / "index.html"

    result = build_gallery([_matched("gravestone", "26.1.2", "shot.png")], output)

    assert result == output
    assert output.exists()
    assert "gravestone" in output.read_text(encoding="utf-8")
