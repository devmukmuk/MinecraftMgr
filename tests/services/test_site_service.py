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
    """Active realms show 'ACTIVE', inactive realms show 'INACTIVE' -- the live-fetched
    running/stopped state gets appended client-side once the trigger daemon responds."""

    html = render_site(
        [
            _entry("gravestone", status="active"),
            _entry("jitterbug", status="inactive"),
        ]
    )

    assert "ACTIVE" in html
    assert "INACTIVE" in html


def test_render_site_status_badge_carries_realm_id_for_live_updates() -> None:
    """The status badge (not just the now-removed live-row) carries data-realm, so the
    client-side refreshStatus() can rewrite it to ACTIVE-Running/-Stopped in place."""

    html = render_site([_entry("gravestone", status="active")])

    assert 'class="status active" data-realm="gravestone" data-registry="active"' in html


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

    assert '<img class="footer-logo" src="logo.png?v=1"' in html
    assert "&copy; 2026 Game Night by Mike." in html


def test_render_site_disables_browser_caching_of_the_page() -> None:
    """The page ships no-cache meta tags so a rebuild isn't hidden behind a stale cache."""

    html = render_site([])

    assert '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">' in html


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


def test_render_site_has_hidden_proxy_and_offline_banners() -> None:
    """Both warning banners ship hidden; the page's status check shows them when needed."""

    html = render_site([])

    assert '<div class="alert" id="proxy-alert" role="alert" hidden>' in html
    assert '<div class="alert" id="offline-alert" role="alert" hidden>' in html
    assert 'statuses._proxy === "stopped"' in html
    assert "setInterval(refreshStatus, 60000)" in html


def test_render_site_has_pin_gated_players_section_per_card() -> None:
    """Each card gets a collapsed "Who's played here" section filled in by script after a PIN."""

    html = render_site([_entry("gatorland")])

    assert '<details class="howto players" data-realm="gatorland">' in html
    assert 'TRIGGER_URL + "/players"' in html
    assert '"X-Autostart-Pin": pin' in html
    assert "FourEight" not in html  # no player data baked into the public page


def test_render_site_players_table_headers_sort() -> None:
    """Player table headers are sort buttons; latest seen, newest first, is the default."""

    html = render_site([_entry("gatorland")])

    assert 'btn.className = "sort-btn"' in html
    assert 'details.getAttribute("data-sort") || "latest_seen"' in html
    assert "aria-sort" in html


def test_render_site_players_table_marks_ops_and_not_yet() -> None:
    """The player table script adds a yellow OP badge and shows "not yet" for never-played."""

    html = render_site([_entry("gatorland")])

    assert 'badge.className = "op-badge"' in html and ".op-badge {" in html
    assert 'td.textContent = "not yet"' in html


def test_render_site_hardcore_card_is_marked_and_has_reset_form() -> None:
    """A hardcore realm gets its own card style, badge, run summary and Archive & Reset form."""

    html = render_site([_entry("hardcore", mode="hardcore")])

    assert '<article class="card hardcore">' in html
    assert 'class="mode-badge"' in html
    assert '<details class="howto hardcore-runs" data-realm="hardcore">' in html
    assert '<button class="reset-btn" data-realm="hardcore">Archive &amp; Reset</button>' in html
    assert 'name="seed"' in html and "Leave blank for a random seed" in html
    assert 'TRIGGER_URL + "/reset/" + realm' in html
    assert 'TRIGGER_URL + "/hardcore"' in html


def test_render_site_survival_card_has_no_hardcore_parts() -> None:
    html = render_site([_entry("gatorland")])

    assert '<article class="card">' in html
    assert '<span class="mode-badge">' not in html
    assert '<form class="reset-form"' not in html
    assert '<details class="howto hardcore-runs"' not in html


def test_render_site_lists_hardcore_realms_first() -> None:
    html = render_site([_entry("arbor"), _entry("hardcore", mode="hardcore"), _entry("blue")])

    assert html.index("hardcore.gamenightbymike.com") < html.index("arbor.gamenightbymike.com")
    assert html.index("arbor.gamenightbymike.com") < html.index("blue.gamenightbymike.com")
