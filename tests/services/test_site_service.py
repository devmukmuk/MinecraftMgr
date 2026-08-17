"""Tests for the realm-picker static site renderer."""

from __future__ import annotations

from pathlib import Path

from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.site_service import build_site, realm_address, render_site


def _entry(server_id: str, **overrides: object) -> ServerEntry:
    fields = {
        "server_id": server_id,
        "name": server_id.title(),
        "status": "active",
        "port": 25565,
        "minecraft_version": "1.21.10",
        "server_type": "paper",
        "jar_source": "",
        "data_dir": server_id,
        "created": "2026-08-15T21:00:00+00:00",
        "notes": "",
    }
    fields.update(overrides)
    return ServerEntry(**fields)


def test_realm_address_uses_realm_domain() -> None:
    """A realm's address is <server_id>.gamenightbymike.com."""

    assert realm_address("gravestone") == "gravestone.gamenightbymike.com"


def test_render_site_includes_each_realm() -> None:
    """Every registered realm gets a card with its name, version, and address."""

    html = render_site([_entry("gravestone", name="Gravestone", minecraft_version="26.1.2")])

    assert "Gravestone" in html
    assert "26.1.2" in html
    assert "gravestone.gamenightbymike.com" in html


def test_render_site_maps_status_to_label() -> None:
    """Active realms show 'Online', inactive realms show 'Test realm'."""

    html = render_site(
        [
            _entry("gravestone", status="active"),
            _entry("jitterbug", status="inactive"),
        ]
    )

    assert "Online" in html
    assert "Test realm" in html


def test_render_site_links_to_the_screenshot_gallery() -> None:
    """The picker page always links out to the screenshot gallery subdomain."""

    html = render_site([])

    assert "https://shots.gamenightbymike.com/report/" in html


def test_render_site_eyebrow_shows_the_real_site_domain() -> None:
    """The hero eyebrow shows minecraft.gamenightbymike.com, the page's real address."""

    html = render_site([])

    assert '<span class="eyebrow">minecraft.gamenightbymike.com</span>' in html
    assert "mc.gamenightbymike.com" not in html


def test_render_site_footer_shows_the_logo_and_copyright() -> None:
    """The footer carries the shared Game Night by Mike logo and copyright line."""

    html = render_site([])

    assert '<img class="footer-logo" src="logo.png"' in html
    assert "&copy; 2026 Game Night by Mike." in html


def test_render_site_empty_registry_still_renders_shell() -> None:
    """An empty realm list still produces a valid page shell, no cards."""

    html = render_site([])

    assert "Game Night by Mike" in html
    assert "<article" not in html


def test_build_site_writes_file(tmp_path: Path) -> None:
    """build_site writes the rendered page to the given output path, creating parent dirs."""

    output = tmp_path / "public" / "index.html"

    result = build_site([_entry("gravestone")], output)

    assert result == output
    assert output.exists()
    assert "Gravestone" in output.read_text(encoding="utf-8")
