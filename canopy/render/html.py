"""Interactive HTML viewer for canopy orbital diagrams.

Injects a pre-rendered SVG (from ``render_svg``) into a self-contained HTML
page with tooltip, zoom/pan, and stats — extracted from the
``canopy-orbital.html`` prototype.  Zero external dependencies.
"""

from __future__ import annotations

import json
import re
from html import escape as html_escape

from canopy.models import ProjectData

from .theme import ProjectStats, Theme, compute_stats


def render_html(
    project_data: ProjectData,
    theme: Theme,
    svg_content: str,
) -> str:
    """Return a self-contained HTML string with interactive SVG viewer."""
    svg = _make_responsive(svg_content, theme)
    json_data = _build_module_data(project_data, theme)
    stats = compute_stats(project_data.modules, theme)
    return _html_template(svg, json_data, stats, project_data.project_name, theme)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_responsive(svg: str, theme: Theme) -> str:
    """Strip fixed width/height from root <svg> tag, let viewBox control sizing."""

    def _patch_svg_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        # Remove fixed width/height from the root <svg> only
        tag = re.sub(r'\s+width="\d+"', "", tag)
        tag = re.sub(r'\s+height="\d+"', "", tag)
        # Add responsive attributes
        tag = tag.replace(
            f'viewBox="0 0 {theme.width} {theme.height}"',
            f'viewBox="0 0 {theme.width} {theme.height}" width="100%" height="100%"',
        )
        return tag

    return re.sub(r"<svg\b[^>]*>", _patch_svg_tag, svg, count=1)


def _build_module_data(project_data: ProjectData, theme: Theme) -> str:
    """Build JSON dict of module metadata for tooltip lookup."""
    layer_map = {la.name: la.label for la in project_data.layers}
    modules = {}
    for m in project_data.modules:
        modules[m.name] = {
            "lines": m.lines,
            "funcs": m.funcs,
            "mi": round(m.mi, 2),
            "cc": round(m.cc, 2),
            "dead": m.dead,
            "churn": m.churn,
            "layer": layer_map.get(m.layer, m.layer),
            "desc": m.desc,
        }
    data = {
        "project_name": project_data.project_name,
        "modules": modules,
    }
    return json.dumps(data, indent=2)


def _html_template(
    svg: str,
    json_data: str,
    stats: ProjectStats,
    project_name: str,
    theme: Theme,
) -> str:
    """Assemble the full HTML page."""
    esc_name = html_escape(project_name)
    n_modules = stats.modules
    n_lines = f"{stats.lines:,}"
    healthy_pct = stats.healthy_pct
    moderate_pct = stats.moderate_pct
    complex_pct = stats.complex_pct
    dead_total = stats.dead_total

    # Theme colors for CSS
    healthy_base = theme.healthy.base
    moderate_base = theme.moderate.base
    complex_base = theme.complex.base

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>canopy — {esc_name} orbital view</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    background: #06080c;
    color: #c9d1d9;
    font-family: monospace;
    height: 100vh;
    overflow: hidden;
  }}

  @supports (height: 100dvh) {{
    body {{ height: 100dvh; }}
  }}

  .container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 16px 24px;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }}

  @supports (height: 100dvh) {{
    .container {{ height: 100dvh; }}
  }}

  .header {{
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 6px;
  }}

  .header h1 {{
    font-size: 20px;
    font-weight: 600;
    color: #e6edf3;
    letter-spacing: -0.5px;
  }}

  .header .badge {{
    background: #1a1f2b;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 11px;
    color: #7d8590;
  }}

  .search-box {{
    display: flex;
    align-items: center;
    margin-left: auto;
    gap: 6px;
  }}

  #search-input {{
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
    font-family: monospace;
    color: #c9d1d9;
    width: 160px;
    outline: none;
  }}

  #search-input:focus {{
    border-color: #58a6ff;
  }}

  #search-count {{
    font-size: 10px;
    color: #7d8590;
  }}

  #search-clear {{
    background: none;
    border: none;
    color: #7d8590;
    cursor: pointer;
    font-size: 16px;
    padding: 0 4px;
    display: none;
  }}

  .subtitle {{
    font-size: 12px;
    color: #484f58;
    margin-bottom: 12px;
    letter-spacing: 0.5px;
  }}

  .legend {{
    display: flex;
    gap: 20px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }}

  .legend-item {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: #7d8590;
  }}

  .legend-swatch {{
    width: 12px;
    height: 12px;
    border-radius: 50%;
  }}

  .legend-swatch.healthy {{ background: radial-gradient(circle at 40% 35%, {theme.healthy.light}, {theme.healthy.dark}); }}
  .legend-swatch.moderate {{ background: radial-gradient(circle at 40% 35%, {theme.moderate.light}, {theme.moderate.dark}); }}
  .legend-swatch.complex {{ background: radial-gradient(circle at 40% 35%, {theme.complex.light}, {theme.complex.dark}); }}
  .legend-swatch.dead {{ background: #484f58; opacity: 0.5; }}
  .legend-swatch.churn {{
    background: transparent;
    border: 2px solid {theme.churn_stroke};
    box-shadow: 0 0 4px rgba(188,140,255,0.4);
  }}
  .legend-swatch.dep {{
    width: 20px;
    height: 2px;
    border-radius: 1px;
    background: linear-gradient(90deg, {theme.dep_light}, {theme.dep_significant});
  }}

  .orbital-container {{
    position: relative;
    background: radial-gradient(ellipse at center, #0d1117 0%, #080b10 50%, #06080c 100%);
    border: 1px solid #21262d;
    border-radius: 12px;
    overflow: hidden;
    cursor: grab;
    flex: 1;
    min-height: 0;
    contain: layout paint;
  }}

  .orbital-container:active {{
    cursor: grabbing;
  }}

  #canvas svg {{
    width: 100%;
    height: 100%;
    display: block;
    transform-origin: 0 0;
    will-change: transform;
  }}

  [data-module] {{
    cursor: pointer;
    transition: filter 0.2s ease;
  }}

  [data-module]:hover {{
    filter: brightness(1.5) drop-shadow(0 0 12px rgba(255,255,255,0.2));
  }}

  /* Perf: shared rules for .is-moving (during interaction) and .zoomed-in (scale > 1.5).
     Filter IDs must match svg.py _render_defs(). */
  .is-moving [data-module],
  .is-moving #canvas svg circle,
  .zoomed-in [data-module],
  .zoomed-in #canvas svg circle[filter] {{
    filter: none !important;
  }}

  .is-moving #canvas svg circle[filter*="softGlow"],
  .is-moving #canvas svg circle[filter*="churnPulse"],
  .zoomed-in #canvas svg circle[filter*="softGlow"],
  .zoomed-in #canvas svg circle[filter*="churnPulse"] {{
    visibility: hidden !important;
  }}

  /* .is-moving only: hide deps & pause CSS animations during drag/wheel */
  .is-moving #canvas svg line,
  .is-moving #canvas svg path {{
    filter: none !important;
    animation-play-state: paused !important;
  }}

  .is-moving #canvas svg line,
  .is-moving #canvas svg path[fill="none"] {{
    visibility: hidden !important;
  }}

  /* .zoomed-in only: pause SVG DOM animations */
  .zoomed-in #canvas svg animate,
  .zoomed-in #canvas svg animateTransform {{
    animation-play-state: paused !important;
  }}

  .search-dim {{
    opacity: 0.12;
    pointer-events: none;
  }}

  .search-highlight {{
    filter: brightness(1.5) drop-shadow(0 0 8px rgba(88,166,255,0.5));
  }}

  .tooltip {{
    position: fixed;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 12px;
    font-family: monospace;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s ease;
    z-index: 100;
    min-width: 220px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.6);
  }}

  .tooltip.visible {{ opacity: 1; }}
  .tooltip .tt-name {{ font-weight: 600; color: #e6edf3; font-size: 13px; margin-bottom: 4px; }}
  .tooltip .tt-desc {{ color: #58a6ff; font-size: 10px; margin-bottom: 8px; }}
  .tooltip .tt-row {{ display: flex; justify-content: space-between; gap: 24px; padding: 2px 0; color: #7d8590; }}
  .tooltip .tt-row .tt-val {{ color: #c9d1d9; font-weight: 500; }}
  .tooltip .tt-bar {{ height: 3px; background: #21262d; border-radius: 2px; margin-top: 8px; overflow: hidden; }}
  .tooltip .tt-bar-fill {{ height: 100%; border-radius: 2px; }}

  .stats-bar {{
    display: flex;
    gap: 32px;
    margin-top: 8px;
    padding: 10px 20px;
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 8px;
    flex-wrap: wrap;
    flex-shrink: 0;
  }}

  .stat {{ display: flex; flex-direction: column; gap: 4px; }}
  .stat-value {{ font-size: 18px; font-weight: 600; color: #e6edf3; }}
  .stat-label {{ font-size: 10px; color: #484f58; text-transform: uppercase; letter-spacing: 1px; }}
  .stat-value.green {{ color: {healthy_base}; }}
  .stat-value.yellow {{ color: {moderate_base}; }}
  .stat-value.red {{ color: {complex_base}; }}

  #sidebar-toggle {{
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 20;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #7d8590;
    cursor: pointer;
    font-size: 18px;
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
  }}

  #sidebar-toggle:hover {{
    color: #e6edf3;
  }}

  #sidebar {{
    position: absolute;
    top: 0;
    right: 0;
    width: 240px;
    height: 100%;
    background: #161b22ee;
    border-left: 1px solid #30363d;
    transform: translateX(100%);
    transition: transform 0.2s ease;
    z-index: 15;
    display: flex;
    flex-direction: column;
  }}

  #sidebar.open {{
    transform: translateX(0);
  }}

  .sidebar-header {{
    padding: 12px;
    font-size: 12px;
    font-weight: 600;
    color: #e6edf3;
    border-bottom: 1px solid #30363d;
  }}

  #sidebar-list {{
    flex: 1;
    overflow-y: auto;
    padding: 4px 0;
  }}

  #sidebar-list::-webkit-scrollbar {{
    width: 4px;
  }}

  #sidebar-list::-webkit-scrollbar-thumb {{
    background: #30363d;
    border-radius: 2px;
  }}

  .sidebar-item {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 12px;
    font-size: 11px;
    color: #c9d1d9;
    cursor: pointer;
  }}

  .sidebar-item:hover {{
    background: #1a1f2b;
  }}

  .sidebar-mi {{
    font-weight: 600;
    font-size: 10px;
  }}

  #shortcuts-overlay {{
    display: none;
    position: fixed;
    inset: 0;
    z-index: 200;
    background: rgba(0,0,0,0.7);
    align-items: center;
    justify-content: center;
  }}

  #shortcuts-overlay.visible {{
    display: flex;
  }}

  .shortcuts-modal {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 24px;
    min-width: 280px;
  }}

  .shortcuts-modal h2 {{
    font-size: 14px;
    color: #e6edf3;
    margin-bottom: 16px;
  }}

  .shortcuts-grid {{
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 16px;
    align-items: center;
  }}

  .shortcuts-grid kbd {{
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 11px;
    font-family: monospace;
    color: #e6edf3;
  }}

  .shortcuts-grid span {{
    font-size: 12px;
    color: #7d8590;
  }}
</style>
</head>
<body>

<div class="container">
  <div class="header">
    <h1>canopy</h1>
    <span class="badge">{esc_name}</span>
    <span class="badge">{n_modules} modules</span>
    <span class="badge">{n_lines} lines</span>
    <div class="search-box">
      <input id="search-input" placeholder="Search modules..." />
      <span id="search-count"></span>
      <button id="search-clear">&times;</button>
    </div>
  </div>
  <p class="subtitle">ORBITAL CODE HEALTH</p>

  <div class="legend">
    <div class="legend-item"><div class="legend-swatch healthy"></div>Healthy</div>
    <div class="legend-item"><div class="legend-swatch moderate"></div>Moderate</div>
    <div class="legend-item"><div class="legend-swatch complex"></div>Complex</div>
    <div class="legend-item"><div class="legend-swatch dead"></div>Dead code</div>
    <div class="legend-item"><div class="legend-swatch churn"></div>High churn</div>
    <div class="legend-item"><div class="legend-swatch dep"></div>Dependency</div>
  </div>

  <div class="orbital-container" id="canvas">
    <button id="sidebar-toggle">&#9776;</button>
    <div id="sidebar">
      <div class="sidebar-header">Modules</div>
      <div id="sidebar-list"></div>
    </div>
    {svg}
  </div>

  <div class="stats-bar">
    <div class="stat"><span class="stat-value">{n_modules}</span><span class="stat-label">Modules</span></div>
    <div class="stat"><span class="stat-value">{n_lines}</span><span class="stat-label">Lines</span></div>
    <div class="stat"><span class="stat-value green">{healthy_pct}%</span><span class="stat-label">Healthy</span></div>
    <div class="stat"><span class="stat-value yellow">{moderate_pct}%</span><span class="stat-label">Moderate</span></div>
    <div class="stat"><span class="stat-value red">{complex_pct}%</span><span class="stat-label">Complex</span></div>
    <div class="stat"><span class="stat-value" style="color:#484f58">{dead_total}</span><span class="stat-label">Dead Code</span></div>
  </div>
</div>

<div class="tooltip" id="tooltip">
  <div class="tt-name" id="tt-name"></div>
  <div class="tt-desc" id="tt-desc"></div>
  <div class="tt-row"><span>Lines</span><span class="tt-val" id="tt-lines"></span></div>
  <div class="tt-row"><span>Functions</span><span class="tt-val" id="tt-funcs"></span></div>
  <div class="tt-row"><span>Maintainability</span><span class="tt-val" id="tt-mi"></span></div>
  <div class="tt-row"><span>Complexity avg</span><span class="tt-val" id="tt-cc"></span></div>
  <div class="tt-row"><span>Dead code</span><span class="tt-val" id="tt-dead"></span></div>
  <div class="tt-row"><span>Churn (30d)</span><span class="tt-val" id="tt-churn"></span></div>
  <div class="tt-row"><span>Layer</span><span class="tt-val" id="tt-layer"></span></div>
  <div class="tt-bar"><div class="tt-bar-fill" id="tt-bar"></div></div>
</div>

<div id="shortcuts-overlay">
  <div class="shortcuts-modal">
    <h2>Keyboard Shortcuts</h2>
    <div class="shortcuts-grid">
      <kbd>/</kbd><span>Search modules</span>
      <kbd>Esc</kbd><span>Close / Clear</span>
      <kbd>R</kbd><span>Reset zoom</span>
      <kbd>M</kbd><span>Module list</span>
      <kbd>?</kbd><span>This help</span>
    </div>
  </div>
</div>

<script>
const DATA = {json_data};

// --- Constants ---
const MI_HEALTHY = {theme.mi_healthy};
const MI_MODERATE = {theme.mi_moderate};
const HEALTHY_COLOR = '{healthy_base}';
const MODERATE_COLOR = '{moderate_base}';
const COMPLEX_COLOR = '{complex_base}';

function miColor(mi) {{
  return mi >= MI_HEALTHY ? HEALTHY_COLOR : mi >= MI_MODERATE ? MODERATE_COLOR : COMPLEX_COLOR;
}}

// --- Tooltip ---
const tooltip = document.getElementById('tooltip');
const svgEl = document.querySelector('#canvas svg');
let pinned = null;

svgEl.addEventListener('mousemove', function(e) {{
  if (pinned) return;
  var g = e.target.closest('[data-module]');
  if (!g) {{ tooltip.classList.remove('visible'); return; }}
  showTooltip(g.dataset.module, e.clientX, e.clientY);
}});

svgEl.addEventListener('mouseleave', function() {{
  if (!pinned) tooltip.classList.remove('visible');
}});

svgEl.addEventListener('click', function(e) {{
  var g = e.target.closest('[data-module]');
  if (!g) {{ pinned = null; tooltip.classList.remove('visible'); return; }}
  if (pinned === g.dataset.module) {{ pinned = null; tooltip.classList.remove('visible'); return; }}
  pinned = g.dataset.module;
  showTooltip(g.dataset.module, e.clientX, e.clientY);
}});

function showTooltip(name, cx, cy) {{
  var m = DATA.modules[name];
  if (!m) return;
  document.getElementById('tt-name').textContent = DATA.project_name + '/' + name;
  document.getElementById('tt-desc').textContent = m.desc || '';
  document.getElementById('tt-lines').textContent = m.lines.toLocaleString();
  document.getElementById('tt-funcs').textContent = m.funcs;
  var miEl = document.getElementById('tt-mi');
  miEl.textContent = m.mi + '/100';
  miEl.style.color = miColor(m.mi);
  document.getElementById('tt-cc').textContent = m.cc;
  document.getElementById('tt-dead').textContent = m.dead > 0 ? m.dead + ' functions' : 'None';
  document.getElementById('tt-churn').textContent = m.churn + ' commits';
  document.getElementById('tt-layer').textContent = m.layer;

  var bar = document.getElementById('tt-bar');
  bar.style.width = m.mi + '%';
  bar.style.background = miColor(m.mi);

  tooltip.classList.add('visible');
  var left = cx + 16;
  var top = cy - 16;
  if (left + 240 > window.innerWidth) left = cx - 240;
  if (top + 200 > window.innerHeight) top = cy - 200;
  tooltip.style.left = left + 'px';
  tooltip.style.top = top + 'px';
}}

// --- Zoom & Pan (CSS transform — GPU accelerated, no SVG re-render) ---
var container = document.getElementById('canvas');
var scale = 1;
var panX = 0;
var panY = 0;
var isPanning = false;
var startX = 0;
var startY = 0;
var startPanX = 0;
var startPanY = 0;

function applyTransform() {{
  svgEl.style.transform = 'translate(' + panX + 'px,' + panY + 'px) scale(' + scale + ')';
  var zoomed = scale > 1.5;
  if (zoomed !== wasZoomedIn) {{
    root.classList.toggle('zoomed-in', zoomed);
    wasZoomedIn = zoomed;
  }}
}}

// --- Performance: disable filters during interaction ---
var moveTimer = null;
var root = document.querySelector('.container');
var wasZoomedIn = false;

function startMoving() {{
  if (!root.classList.contains('is-moving')) root.classList.add('is-moving');
  clearTimeout(moveTimer);
  moveTimer = setTimeout(function() {{ root.classList.remove('is-moving'); }}, 150);
}}

function resetZoom() {{
  scale = 1; panX = 0; panY = 0; isPanning = false;
  svgEl.style.transition = 'transform 0.3s ease';
  applyTransform();
  setTimeout(function() {{ svgEl.style.transition = ''; }}, 300);
}}

container.addEventListener('wheel', function(e) {{
  e.preventDefault();
  startMoving();
  var factor = e.deltaY > 0 ? 0.9 : 1.1;
  var rect = container.getBoundingClientRect();
  var mx = e.clientX - rect.left;
  var my = e.clientY - rect.top;
  panX = mx - (mx - panX) * factor;
  panY = my - (my - panY) * factor;
  scale *= factor;
  applyTransform();
}}, {{ passive: false }});

container.addEventListener('mousedown', function(e) {{
  if (e.button !== 0) return;
  isPanning = true;
  startX = e.clientX;
  startY = e.clientY;
  startPanX = panX;
  startPanY = panY;
}});

window.addEventListener('mousemove', function(e) {{
  if (!isPanning) return;
  startMoving();
  panX = startPanX + (e.clientX - startX);
  panY = startPanY + (e.clientY - startY);
  applyTransform();
}});

window.addEventListener('mouseup', function() {{
  isPanning = false;
}});

container.addEventListener('dblclick', function() {{
  resetZoom();
}});

// --- Search / Filter ---
var searchInput = document.getElementById('search-input');
var searchCount = document.getElementById('search-count');
var searchClear = document.getElementById('search-clear');

function filterModules(query) {{
  var groups = svgEl.querySelectorAll('[data-module]');
  var matches = 0;
  query = query.toLowerCase();
  groups.forEach(function(g) {{
    var name = g.dataset.module.toLowerCase();
    if (!query || name.includes(query)) {{
      g.classList.remove('search-dim');
      if (query) {{ g.classList.add('search-highlight'); matches++; }}
      else {{ g.classList.remove('search-highlight'); }}
    }} else {{
      g.classList.add('search-dim');
      g.classList.remove('search-highlight');
    }}
  }});
  searchCount.textContent = query ? matches + ' found' : '';
  searchClear.style.display = query ? 'block' : 'none';
  filterSidebarList(query);
}}

searchInput.addEventListener('input', function() {{
  filterModules(this.value);
}});

searchClear.addEventListener('click', function() {{
  searchInput.value = '';
  filterModules('');
  searchInput.focus();
}});

// --- Sidebar ---
var sidebar = document.getElementById('sidebar');
var sidebarToggle = document.getElementById('sidebar-toggle');
var sidebarList = document.getElementById('sidebar-list');

function buildSidebarList() {{
  var entries = Object.keys(DATA.modules).map(function(name) {{
    return {{ name: name, mi: DATA.modules[name].mi }};
  }}).sort(function(a, b) {{ return a.mi - b.mi; }});
  sidebarList.innerHTML = '';
  entries.forEach(function(e) {{
    var item = document.createElement('div');
    item.className = 'sidebar-item';
    item.dataset.module = e.name;
    item.innerHTML = '<span>' + e.name + '</span><span class="sidebar-mi" style="color:' + miColor(e.mi) + '">' + e.mi + '</span>';
    item.addEventListener('click', function() {{ zoomToModule(e.name); }});
    sidebarList.appendChild(item);
  }});
}}

function filterSidebarList(query) {{
  query = query.toLowerCase();
  var items = sidebarList.querySelectorAll('.sidebar-item');
  items.forEach(function(item) {{
    item.style.display = item.dataset.module.toLowerCase().includes(query) || !query ? '' : 'none';
  }});
}}

function toggleSidebar() {{
  sidebar.classList.toggle('open');
}}

function zoomToModule(name) {{
  var g = document.querySelector('[data-module="' + name + '"]');
  if (!g) return;
  var bbox = g.getBBox();
  var cx = bbox.x + bbox.width / 2;
  var cy = bbox.y + bbox.height / 2;
  var rect = container.getBoundingClientRect();
  scale = 3;
  panX = rect.width / 2 - cx * scale;
  panY = rect.height / 2 - cy * scale;
  svgEl.style.transition = 'transform 0.3s ease';
  applyTransform();
  setTimeout(function() {{ svgEl.style.transition = ''; }}, 300);
  pinned = name;
  showTooltip(name, rect.left + rect.width / 2, rect.top + rect.height / 2);
}}

sidebarToggle.addEventListener('click', toggleSidebar);
buildSidebarList();

// --- Keyboard Shortcuts ---
var shortcutsOverlay = document.getElementById('shortcuts-overlay');

document.addEventListener('keydown', function(e) {{
  var tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA') {{
    if (e.key === 'Escape') {{
      searchInput.value = '';
      filterModules('');
      searchInput.blur();
    }}
    return;
  }}
  if (e.key === '/' || (e.ctrlKey && e.key === 'f')) {{
    e.preventDefault();
    searchInput.focus();
  }} else if (e.key === 'Escape') {{
    searchInput.value = '';
    filterModules('');
    pinned = null;
    tooltip.classList.remove('visible');
    sidebar.classList.remove('open');
    shortcutsOverlay.classList.remove('visible');
  }} else if (e.key === 'r' || e.key === 'R') {{
    resetZoom();
  }} else if (e.key === 'm' || e.key === 'M') {{
    toggleSidebar();
  }} else if (e.key === '?') {{
    shortcutsOverlay.classList.toggle('visible');
  }}
}});

shortcutsOverlay.addEventListener('click', function(e) {{
  if (e.target === shortcutsOverlay) shortcutsOverlay.classList.remove('visible');
}});
</script>
</body>
</html>
"""
