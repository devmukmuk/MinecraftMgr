"""Tests for the exact copy-paste snippets rendered after provision/activate."""

from __future__ import annotations

from minecraftmgr.models.server_entry import ServerEntry
from minecraftmgr.services.realm_handoff_service import (
    render_cloudflare_instructions,
    render_handoff,
    render_server_add_command,
    render_velocity_snippet,
)


def _entry() -> ServerEntry:
    return ServerEntry(
        server_id="gatorland",
        name="Gatorland",
        status="active",
        port=26020,
        minecraft_version="26.2",
        server_type="paper",
        jar_source="",
        data_dir="gatorland_26_2",
        created="2026-08-16T21:00:00+00:00",
        notes="",
    )


def test_render_server_add_command_includes_all_fields() -> None:
    """The rendered command is copy-paste ready with every field the real command needs."""

    command = render_server_add_command(_entry())

    assert command == (
        "minecraftmgr server add gatorland "
        '--name "Gatorland" --port 26020 '
        "--mc-version 26.2 --type paper "
        "--data-dir gatorland_26_2"
    )


def test_render_velocity_snippet_has_matching_server_id_and_port() -> None:
    """[servers] and [forced-hosts] both reference the same server_id, and the given backend port."""

    snippet = render_velocity_snippet(_entry(), backend_port=26020)

    assert 'gatorland = "127.0.0.1:26020"' in snippet
    assert '"gatorland.gamenightbymike.com" = [' in snippet
    assert '"gatorland"' in snippet


def test_render_cloudflare_instructions_names_the_realm() -> None:
    """Cloudflare instructions name the realm as the CNAME record name."""

    instructions = render_cloudflare_instructions(_entry())

    assert "Name: gatorland" in instructions
    assert "Target: mc.gamenightbymike.com" in instructions
    assert "CNAME" in instructions


def test_render_handoff_includes_all_three_sections() -> None:
    """The full handoff block includes the server add command, velocity snippet, and Cloudflare steps."""

    handoff = render_handoff(_entry(), backend_port=26020)

    assert "minecraftmgr server add gatorland" in handoff
    assert "[servers]" in handoff
    assert "Cloudflare" in handoff
