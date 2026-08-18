"""Render the realm-picker static site from the servers.json registry."""

from __future__ import annotations

from pathlib import Path

from minecraftmgr.constants import (
    COMPANY_NAME,
    COMPANY_YEAR,
    LOGO_VERSION,
    REALM_DOMAIN,
    SCREENSHOTS_URL,
    TRIGGER_URL,
)
from minecraftmgr.models.server_entry import ServerEntry

_STATUS_LABELS = {
    "active": ("active", "ACTIVE"),
    "inactive": ("inactive", "INACTIVE"),
}

_PAGE_TEMPLATE = """<title>Game Night by Mike</title>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<style>
  :root {{
    --bg: #f1ecdf;
    --surface: #fbf8f0;
    --surface-raised: #ffffff;
    --ink: #26221a;
    --ink-dim: #6b6455;
    --line: #ddd2b8;
    --accent: #b9711a;
    --accent-ink: #fff8ec;
    --good: #4f7942;
    --good-bg: #e4ecd9;
    --muted: #948c78;
    --muted-bg: #eae4d3;
    --shadow: 0 1px 2px rgba(38,34,26,0.06), 0 6px 16px -8px rgba(38,34,26,0.18);
    color-scheme: light;
  }}

  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #14171c;
      --surface: #1b1f26;
      --surface-raised: #21262e;
      --ink: #ece5d3;
      --ink-dim: #979082;
      --line: #2b313b;
      --accent: #e8a33d;
      --accent-ink: #201404;
      --good: #8fbb74;
      --good-bg: #24301f;
      --muted: #6b7280;
      --muted-bg: #232830;
      --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 10px 24px -10px rgba(0,0,0,0.55);
      color-scheme: dark;
    }}
  }}

  :root[data-theme="dark"] {{
    --bg: #14171c;
    --surface: #1b1f26;
    --surface-raised: #21262e;
    --ink: #ece5d3;
    --ink-dim: #979082;
    --line: #2b313b;
    --accent: #e8a33d;
    --accent-ink: #201404;
    --good: #8fbb74;
    --good-bg: #24301f;
    --muted: #6b7280;
    --muted-bg: #232830;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 10px 24px -10px rgba(0,0,0,0.55);
    color-scheme: dark;
  }}

  * {{ box-sizing: border-box; }}

  body {{
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }}

  .wrap {{
    max-width: 920px;
    margin: 0 auto;
    padding: 2.75rem 1.5rem 5rem;
  }}

  header.hero {{
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    margin-bottom: 0.5rem;
  }}

  .eyebrow {{
    font-family: 'Cascadia Code', 'Consolas', 'SFMono-Regular', Menlo, monospace;
    font-size: 0.72rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--accent);
  }}

  h1 {{
    font-family: Rockwell, 'Roboto Slab', 'Noto Serif', Georgia, serif;
    font-weight: 700;
    font-size: clamp(2.1rem, 5vw, 2.9rem);
    margin: 0;
    text-wrap: balance;
    letter-spacing: -0.01em;
  }}

  .tagline {{
    color: var(--ink-dim);
    font-size: 1.02rem;
    max-width: 46ch;
  }}

  .torch-rule {{
    height: 3px;
    margin: 1.6rem 0 2.2rem;
    border-radius: 2px;
    background: linear-gradient(90deg, var(--accent), transparent 70%);
  }}

  h2.section-title {{
    font-family: Rockwell, 'Roboto Slab', 'Noto Serif', Georgia, serif;
    font-size: 1.15rem;
    margin: 0 0 0.3rem;
    letter-spacing: -0.01em;
  }}

  .section-sub {{
    color: var(--ink-dim);
    font-size: 0.92rem;
    margin: 0 0 1.1rem;
    max-width: 60ch;
  }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 1rem;
  }}

  .card {{
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 1.1rem 1.15rem 1rem;
    box-shadow: var(--shadow);
    display: flex;
    flex-direction: column;
    gap: 0.7rem;
    transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease, border-color 160ms ease;
  }}

  .card:hover {{ transform: translateY(-2px); }}

  .card.running {{ background: var(--good-bg); border-color: var(--good); }}

  .card-top {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.6rem;
  }}

  .realm-name {{
    font-family: Rockwell, 'Roboto Slab', 'Noto Serif', Georgia, serif;
    font-weight: 700;
    font-size: 1.28rem;
    margin: 0;
  }}

  .version-badge {{
    font-family: 'Cascadia Code', 'Consolas', 'SFMono-Regular', Menlo, monospace;
    font-size: 0.74rem;
    color: var(--ink-dim);
  }}

  .status {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.72rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-weight: 600;
    padding: 0.24rem 0.55rem;
    border-radius: 999px;
    white-space: nowrap;
  }}

  .status .dot {{
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
  }}

  .status.active {{ color: var(--good); background: var(--good-bg); }}
  .status.inactive {{ color: var(--muted); background: var(--muted-bg); }}
  .status.running {{ color: var(--good); background: var(--surface-raised); }}
  .status.running .dot {{ animation: flicker 2.6s ease-in-out infinite; }}
  .status.stopped {{ color: var(--muted); background: var(--surface-raised); }}

  @media (prefers-reduced-motion: reduce) {{
    .status.running .dot {{ animation: none; }}
  }}

  @keyframes flicker {{
    0%, 100% {{ opacity: 1; }}
    45% {{ opacity: 0.55; }}
    52% {{ opacity: 1; }}
    78% {{ opacity: 0.7; }}
  }}

  .addr-row {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--surface-raised);
    border: 1px solid var(--line);
    border-radius: 7px;
    padding: 0.5rem 0.6rem;
  }}

  .addr-row code {{
    font-family: 'Cascadia Code', 'Consolas', 'SFMono-Regular', Menlo, monospace;
    font-size: 0.82rem;
    color: var(--ink);
    overflow-x: auto;
    white-space: nowrap;
    flex: 1;
    user-select: all;
  }}

  .copy-btn {{
    font-family: inherit;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: var(--accent-ink);
    background: var(--accent);
    border: none;
    border-radius: 5px;
    padding: 0.36rem 0.6rem;
    cursor: pointer;
    flex-shrink: 0;
  }}

  .copy-btn:focus-visible, summary:focus-visible {{
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }}

  .copy-btn[data-copied="true"] {{ background: var(--good); color: #fff; }}

  .live-row {{
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.5rem;
    font-size: 0.78rem;
  }}

  .live-row[hidden] {{ display: none; }}

  .autostart-btn {{
    font-family: inherit;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: var(--ink);
    background: transparent;
    border: 1px solid var(--accent);
    border-radius: 5px;
    padding: 0.3rem 0.55rem;
    cursor: pointer;
  }}

  .autostart-btn[hidden] {{ display: none; }}
  .autostart-btn:disabled {{ opacity: 0.6; cursor: default; }}

  details.howto summary {{
    cursor: pointer;
    font-size: 0.82rem;
    color: var(--ink-dim);
    list-style: none;
  }}

  details.howto summary::-webkit-details-marker {{ display: none; }}
  details.howto summary::before {{
    content: "+ ";
    color: var(--accent);
    font-weight: 700;
  }}
  details.howto[open] summary::before {{ content: "\\2212 "; }}

  details.howto ol {{
    margin: 0.5rem 0 0;
    padding-left: 1.1rem;
    font-size: 0.85rem;
    color: var(--ink-dim);
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }}

  .gallery-section {{
    margin-top: 2.4rem;
    padding-top: 1.6rem;
    border-top: 1px solid var(--line);
  }}

  .gallery-link {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-family: inherit;
    font-size: 0.86rem;
    font-weight: 600;
    color: var(--accent-ink);
    background: var(--accent);
    border-radius: 7px;
    padding: 0.55rem 1rem;
    text-decoration: none;
  }}

  .gallery-link:hover {{ opacity: 0.92; }}

  footer {{
    margin-top: 3rem;
    padding-top: 1.2rem;
    border-top: 1px solid var(--line);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.6rem;
    text-align: center;
  }}

  .footer-build-note {{
    font-size: 0.78rem;
    color: var(--ink-dim);
  }}

  .footer-logo {{
    display: block;
    max-height: 32px;
    width: auto;
  }}

  .footer-copyright {{
    max-width: 40ch;
    font-size: 0.72rem;
    color: var(--ink-dim);
    opacity: 0.75;
  }}
</style>

<div class="wrap">

  <header class="hero">
    <span class="eyebrow">minecraft.{domain}</span>
    <h1>Game Night by Mike</h1>
    <p class="tagline">Pick a realm, copy its address, paste it into the Minecraft launcher. No ports, nothing to install.</p>
  </header>
  <div class="torch-rule"></div>

  <section>
    <h2 class="section-title">Realms</h2>
    <p class="section-sub">Every realm registered in servers.json, with the version it needs and its connect address.</p>

    <div class="grid">
{cards}
    </div>
  </section>

  <section class="gallery-section">
    <h2 class="section-title">Screenshots</h2>
    <p class="section-sub">Screenshots from every realm, sorted by realm and version.</p>
    <a class="gallery-link" href="{screenshots_url}">Open the gallery &rarr;</a>
  </section>

  <footer>
    <p class="footer-build-note">Generated from servers.json by <code>minecraftmgr web build</code>.</p>
    <img class="footer-logo" src="logo.png?v={logo_version}" alt="{company_name} logo">
    <p class="footer-copyright">&copy; {company_year} {company_name}.</p>
  </footer>

</div>

<script>
  document.querySelectorAll('.copy-btn').forEach(function (btn) {{
    btn.addEventListener('click', function () {{
      var text = btn.getAttribute('data-copy');
      function done() {{
        btn.textContent = 'Copied';
        btn.setAttribute('data-copied', 'true');
        setTimeout(function () {{
          btn.textContent = 'Copy';
          btn.removeAttribute('data-copied');
        }}, 1400);
      }}
      if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText(text).then(done, function () {{
          var code = btn.previousElementSibling;
          if (code) {{
            var range = document.createRange();
            range.selectNode(code);
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
          }}
        }});
      }} else {{
        var code = btn.previousElementSibling;
        if (code) {{
          var range = document.createRange();
          range.selectNode(code);
          var sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(range);
        }}
      }}
    }});
  }});

  var TRIGGER_URL = "{trigger_url}";

  function refreshStatus() {{
    fetch(TRIGGER_URL + "/status").then(function (res) {{
      if (!res.ok) {{ throw new Error("bad status"); }}
      return res.json();
    }}).then(function (statuses) {{
      document.querySelectorAll(".status[data-realm]").forEach(function (badge) {{
        var realm = badge.getAttribute("data-realm");
        var state = statuses[realm];
        if (!state) {{ return; }}
        var registry = badge.getAttribute("data-registry") === "active" ? "ACTIVE" : "INACTIVE";
        var running = state === "running";
        badge.classList.remove("active", "inactive");
        badge.classList.add(running ? "running" : "stopped");
        badge.querySelector(".status-label").textContent = registry + "-" + (running ? "Running" : "Stopped");
        var card = badge.closest(".card");
        if (card) {{
          card.classList.toggle("running", running);
        }}
      }});
      document.querySelectorAll(".live-row").forEach(function (row) {{
        var realm = row.getAttribute("data-realm");
        var state = statuses[realm];
        if (!state) {{ return; }}
        row.hidden = false;
        var btn = row.querySelector(".autostart-btn");
        btn.hidden = state !== "stopped";
      }});
    }}).catch(function () {{
      // Trigger daemon not reachable -- picker stays fully usable without it.
    }});
  }}

  document.querySelectorAll(".autostart-btn").forEach(function (btn) {{
    btn.addEventListener("click", function () {{
      var realm = btn.getAttribute("data-realm");
      var pin = window.prompt("Family PIN to start " + realm + ":");
      if (!pin) {{ return; }}

      btn.disabled = true;
      btn.textContent = "Starting\\u2026";

      fetch(TRIGGER_URL + "/start/" + realm, {{
        method: "POST",
        headers: {{ "X-Autostart-Pin": pin }}
      }}).then(function (res) {{
        if (res.status === 403) {{ window.alert("Wrong PIN."); return; }}
        if (!res.ok) {{ window.alert("Could not start it \\u2014 try again in a bit."); return; }}
        setTimeout(refreshStatus, 15000);
      }}).catch(function () {{
        window.alert("Could not reach the server.");
      }}).finally(function () {{
        btn.disabled = false;
        btn.textContent = "Autostart";
      }});
    }});
  }});

  refreshStatus();
</script>
"""

_CARD_TEMPLATE = """      <article class="card">
        <div class="card-top">
          <div>
            <p class="realm-name">{name}</p>
            <span class="version-badge">Minecraft {version} &middot; {server_type}</span>
          </div>
          <span class="status {status_class}" data-realm="{server_id}" data-registry="{status_class}"><span class="dot"></span><span class="status-label">{status_label}</span></span>
        </div>
        <div class="addr-row">
          <code>{address}</code>
          <button class="copy-btn" data-copy="{address}">Copy</button>
        </div>
        <details class="howto">
          <summary>How to join</summary>
          <ol>
            <li>Open the Minecraft launcher, select <b>{version}</b>, and press Play.</li>
            <li>Multiplayer &rarr; Add Server.</li>
            <li>Paste the address above. Leave the port blank.</li>
          </ol>
        </details>
        <div class="live-row" data-realm="{server_id}" hidden>
          <button class="autostart-btn" data-realm="{server_id}" hidden>Autostart</button>
        </div>
      </article>"""


def realm_address(server_id: str) -> str:
    """Return the public connect address for a realm."""

    return f"{server_id}.{REALM_DOMAIN}"


def _render_card(server: ServerEntry) -> str:
    status_class, status_label = _STATUS_LABELS.get(server.status, ("inactive", server.status.title()))

    return _CARD_TEMPLATE.format(
        server_id=server.server_id,
        name=server.name,
        version=server.minecraft_version,
        server_type=server.server_type.title(),
        status_class=status_class,
        status_label=status_label,
        address=realm_address(server.server_id),
    )


def render_site(servers: list[ServerEntry]) -> str:
    """Render the realm-picker page HTML for the given registry entries."""

    cards = "\n".join(_render_card(server) for server in servers)

    return _PAGE_TEMPLATE.format(
        domain=REALM_DOMAIN,
        trigger_url=TRIGGER_URL,
        screenshots_url=SCREENSHOTS_URL,
        company_name=COMPANY_NAME,
        company_year=COMPANY_YEAR,
        logo_version=LOGO_VERSION,
        cards=cards,
    )


def build_site(servers: list[ServerEntry], output_path: Path) -> Path:
    """Render the realm-picker page and write it to output_path."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_site(servers), encoding="utf-8")

    return output_path
