"""Render the filterable screenshot gallery page from an organize manifest."""

from __future__ import annotations

from pathlib import Path

from minecraftmgr.models.screenshot_match import ScreenshotMatch

UNSORTED_LABEL = "Unsorted"
UNKNOWN_VERSION_LABEL = "Unknown"

_PAGE_TEMPLATE = """<title>Screenshot Gallery &mdash; Game Night by Mike</title>
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

  .layout {{
    display: grid;
    grid-template-columns: 220px 1fr;
    min-height: 100vh;
  }}

  @media (max-width: 720px) {{
    .layout {{ grid-template-columns: 1fr; }}
  }}

  nav.filters {{
    padding: 1.75rem 1.25rem;
    border-right: 1px solid var(--line);
    background: var(--surface);
  }}

  nav.filters h1 {{
    font-family: Rockwell, 'Roboto Slab', 'Noto Serif', Georgia, serif;
    font-size: 1.3rem;
    margin: 0 0 1.2rem;
  }}

  .filter-group {{ margin-bottom: 1.4rem; }}

  .filter-group h2 {{
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--ink-dim);
    margin: 0 0 0.5rem;
  }}

  .filter-group label {{
    display: flex;
    align-items: center;
    gap: 0.45rem;
    font-size: 0.88rem;
    padding: 0.2rem 0;
    cursor: pointer;
  }}

  .count-pill {{
    margin-left: auto;
    font-size: 0.72rem;
    color: var(--ink-dim);
  }}

  .reset-btn {{
    font-family: inherit;
    font-size: 0.78rem;
    color: var(--accent);
    background: none;
    border: none;
    padding: 0;
    cursor: pointer;
    text-decoration: underline;
  }}

  main {{ padding: 1.75rem 1.75rem 4rem; }}

  .summary {{
    color: var(--ink-dim);
    font-size: 0.92rem;
    margin: 0 0 1.2rem;
  }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 1rem;
  }}

  .card {{
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
    box-shadow: var(--shadow);
    display: flex;
    flex-direction: column;
  }}

  .card[hidden] {{ display: none; }}

  .card img {{
    width: 100%;
    aspect-ratio: 16 / 9;
    object-fit: cover;
    display: block;
    background: var(--muted-bg);
  }}

  .card-meta {{
    padding: 0.6rem 0.75rem 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }}

  .card-realm {{
    font-weight: 600;
    font-size: 0.9rem;
  }}

  .card-sub {{
    font-size: 0.76rem;
    color: var(--ink-dim);
    font-family: 'Cascadia Code', 'Consolas', 'SFMono-Regular', Menlo, monospace;
  }}

  .empty-state {{
    color: var(--ink-dim);
    padding: 2rem 0;
  }}

  .card-img-btn {{
    display: block;
    width: 100%;
    padding: 0;
    border: none;
    background: none;
    cursor: pointer;
  }}

  .card-img-btn:focus-visible {{
    outline: 2px solid var(--accent);
    outline-offset: -2px;
  }}

  .lightbox {{
    position: fixed;
    inset: 0;
    background: rgba(10, 8, 4, 0.92);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
  }}

  .lightbox[hidden] {{ display: none; }}

  .lightbox img {{
    max-width: 90vw;
    max-height: 86vh;
    object-fit: contain;
    box-shadow: 0 10px 40px rgba(0,0,0,0.5);
  }}

  .lightbox-caption {{
    position: absolute;
    bottom: 1.5rem;
    left: 0;
    right: 0;
    text-align: center;
    color: #fff8ec;
    font-size: 0.82rem;
    font-family: 'Cascadia Code', 'Consolas', 'SFMono-Regular', Menlo, monospace;
  }}

  .lightbox-btn {{
    position: absolute;
    top: 0;
    bottom: 0;
    width: 4rem;
    border: none;
    background: none;
    color: #fff8ec;
    font-size: 2.2rem;
    cursor: pointer;
    opacity: 0.75;
  }}

  .lightbox-btn:hover, .lightbox-btn:focus-visible {{ opacity: 1; }}

  .lightbox-prev {{ left: 0; }}
  .lightbox-next {{ right: 0; }}

  .lightbox-close {{
    position: absolute;
    top: 0.75rem;
    right: 1rem;
    border: none;
    background: none;
    color: #fff8ec;
    font-size: 2rem;
    line-height: 1;
    cursor: pointer;
    opacity: 0.85;
  }}

  .lightbox-close:hover, .lightbox-close:focus-visible {{ opacity: 1; }}
</style>

<div class="layout">
  <nav class="filters">
    <h1>Screenshots</h1>

    <div class="filter-group">
      <h2>Realm</h2>
{realm_checkboxes}
    </div>

    <div class="filter-group">
      <h2>Version</h2>
{version_checkboxes}
    </div>

    <button class="reset-btn" id="reset-filters">Reset filters</button>
  </nav>

  <main>
    <p class="summary" id="summary">{total} screenshot(s)</p>
    <div class="grid" id="grid">
{cards}
    </div>
    <p class="empty-state" id="empty-state" hidden>No screenshots match the current filters.</p>
  </main>
</div>

<div class="lightbox" id="lightbox" hidden>
  <button class="lightbox-btn lightbox-prev" id="lightbox-prev" aria-label="Previous screenshot">&lsaquo;</button>
  <img id="lightbox-img" src="" alt="">
  <button class="lightbox-btn lightbox-next" id="lightbox-next" aria-label="Next screenshot">&rsaquo;</button>
  <button class="lightbox-close" id="lightbox-close" aria-label="Close">&times;</button>
  <p class="lightbox-caption" id="lightbox-caption"></p>
</div>

<script>
  var realmChecks = Array.prototype.slice.call(document.querySelectorAll('[data-filter="realm"]'));
  var versionChecks = Array.prototype.slice.call(document.querySelectorAll('[data-filter="version"]'));
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var summary = document.getElementById('summary');
  var emptyState = document.getElementById('empty-state');

  function checkedValues(checks) {{
    return checks.filter(function (c) {{ return c.checked; }}).map(function (c) {{ return c.value; }});
  }}

  function applyFilters() {{
    var realms = checkedValues(realmChecks);
    var versions = checkedValues(versionChecks);
    var visible = 0;

    cards.forEach(function (card) {{
      var matches = realms.indexOf(card.getAttribute('data-realm')) !== -1
        && versions.indexOf(card.getAttribute('data-version')) !== -1;
      card.hidden = !matches;
      if (matches) {{ visible += 1; }}
    }});

    summary.textContent = visible + ' of {total} screenshot(s)';
    emptyState.hidden = visible !== 0;
  }}

  realmChecks.concat(versionChecks).forEach(function (input) {{
    input.addEventListener('change', applyFilters);
  }});

  document.getElementById('reset-filters').addEventListener('click', function () {{
    realmChecks.concat(versionChecks).forEach(function (input) {{ input.checked = true; }});
    applyFilters();
  }});

  applyFilters();

  var lightbox = document.getElementById('lightbox');
  var lightboxImg = document.getElementById('lightbox-img');
  var lightboxCaption = document.getElementById('lightbox-caption');

  function visibleCards() {{
    return cards.filter(function (card) {{ return !card.hidden; }});
  }}

  function openLightbox(card) {{
    var btn = card.querySelector('.card-img-btn');
    lightboxImg.src = btn.getAttribute('data-full');
    lightboxImg.alt = btn.getAttribute('data-filename');
    lightboxCaption.textContent = card.querySelector('.card-realm').textContent
      + ' · ' + card.querySelector('.card-sub').textContent;
    lightbox.hidden = false;
    lightbox.setAttribute('data-current', String(visibleCards().indexOf(card)));
  }}

  function closeLightbox() {{
    lightbox.hidden = true;
    lightboxImg.src = '';
  }}

  function showByOffset(offset) {{
    var shown = visibleCards();
    if (shown.length === 0) {{ return; }}
    var current = parseInt(lightbox.getAttribute('data-current'), 10) || 0;
    var next = (current + offset + shown.length) % shown.length;
    openLightbox(shown[next]);
  }}

  cards.forEach(function (card) {{
    var btn = card.querySelector('.card-img-btn');
    btn.addEventListener('click', function () {{ openLightbox(card); }});
  }});

  document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
  document.getElementById('lightbox-prev').addEventListener('click', function () {{ showByOffset(-1); }});
  document.getElementById('lightbox-next').addEventListener('click', function () {{ showByOffset(1); }});

  lightbox.addEventListener('click', function (event) {{
    if (event.target === lightbox) {{ closeLightbox(); }}
  }});

  document.addEventListener('keydown', function (event) {{
    if (lightbox.hidden) {{ return; }}
    if (event.key === 'Escape') {{ closeLightbox(); }}
    if (event.key === 'ArrowLeft') {{ showByOffset(-1); }}
    if (event.key === 'ArrowRight') {{ showByOffset(1); }}
  }});
</script>
"""

_CHECKBOX_TEMPLATE = (
    '      <label><input type="checkbox" data-filter="{kind}" value="{value}" checked>'
    "{label}<span class=\"count-pill\">{count}</span></label>"
)

_CARD_TEMPLATE = """      <article class="card" data-realm="{realm}" data-version="{version}">
        <button class="card-img-btn" data-full="../{relative_path}" data-filename="{filename}">
          <img src="../{relative_path}" alt="{filename}" loading="lazy">
        </button>
        <div class="card-meta">
          <span class="card-realm">{realm_label}</span>
          <span class="card-sub">{version_label} &middot; {taken_label}</span>
        </div>
      </article>"""


def _realm_label(match: ScreenshotMatch) -> str:
    return match.realm if match.matched and match.realm else UNSORTED_LABEL


def _version_label(match: ScreenshotMatch) -> str:
    if match.matched and match.minecraft_version:
        return match.minecraft_version
    return UNKNOWN_VERSION_LABEL


def _taken_label(match: ScreenshotMatch) -> str:
    return match.taken_at.strftime("%Y-%m-%d %H:%M") if match.taken_at else "Unknown date"


def _render_checkbox_group(kind: str, labels: dict[str, int]) -> str:
    return "\n".join(
        _CHECKBOX_TEMPLATE.format(kind=kind, value=label, label=label, count=count)
        for label, count in sorted(labels.items())
    )


def _render_card(match: ScreenshotMatch) -> str:
    realm_label = _realm_label(match)
    version_label = _version_label(match)

    return _CARD_TEMPLATE.format(
        realm=realm_label,
        version=version_label,
        relative_path=match.relative_path,
        filename=match.filename,
        realm_label=realm_label,
        version_label=version_label,
        taken_label=_taken_label(match),
    )


def render_gallery(matches: list[ScreenshotMatch]) -> str:
    """Render the screenshot gallery page HTML for the given manifest entries."""

    realm_counts: dict[str, int] = {}
    version_counts: dict[str, int] = {}

    for match in matches:
        realm_counts[_realm_label(match)] = realm_counts.get(_realm_label(match), 0) + 1
        version_counts[_version_label(match)] = version_counts.get(_version_label(match), 0) + 1

    cards = "\n".join(_render_card(match) for match in matches)

    return _PAGE_TEMPLATE.format(
        realm_checkboxes=_render_checkbox_group("realm", realm_counts),
        version_checkboxes=_render_checkbox_group("version", version_counts),
        total=len(matches),
        cards=cards,
    )


def build_gallery(matches: list[ScreenshotMatch], output_path: Path) -> Path:
    """Render the screenshot gallery page and write it to output_path."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_gallery(matches), encoding="utf-8")

    return output_path
