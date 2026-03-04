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
    min-height: 100vh;
  }}

  .container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 32px 24px;
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

  .subtitle {{
    font-size: 12px;
    color: #484f58;
    margin-bottom: 24px;
    letter-spacing: 0.5px;
  }}

  .legend {{
    display: flex;
    gap: 20px;
    margin-bottom: 20px;
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
  }}

  .orbital-container:active {{
    cursor: grabbing;
  }}

  #canvas svg {{
    width: 100%;
    height: 100%;
    display: block;
  }}

  [data-module] {{
    cursor: pointer;
    transition: filter 0.2s ease;
  }}

  [data-module]:hover {{
    filter: brightness(1.5) drop-shadow(0 0 12px rgba(255,255,255,0.2));
  }}

  /* Disable expensive filters during zoom/pan for smooth interaction */
  .interacting svg * {{
    filter: none !important;
    transition: none !important;
  }}
  .interacting svg animate,
  .interacting svg animateTransform {{
    animation-play-state: paused;
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
    margin-top: 20px;
    padding: 16px 20px;
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 8px;
    flex-wrap: wrap;
  }}

  .stat {{ display: flex; flex-direction: column; gap: 4px; }}
  .stat-value {{ font-size: 18px; font-weight: 600; color: #e6edf3; }}
  .stat-label {{ font-size: 10px; color: #484f58; text-transform: uppercase; letter-spacing: 1px; }}
  .stat-value.green {{ color: {healthy_base}; }}
  .stat-value.yellow {{ color: {moderate_base}; }}
  .stat-value.red {{ color: {complex_base}; }}
</style>
</head>
<body>

<div class="container">
  <div class="header">
    <h1>canopy</h1>
    <span class="badge">{esc_name}</span>
    <span class="badge">{n_modules} modules</span>
    <span class="badge">{n_lines} lines</span>
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

<script>
const DATA = {json_data};

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
  document.getElementById('tt-mi').textContent = m.mi + '/100';
  document.getElementById('tt-cc').textContent = m.cc;
  document.getElementById('tt-dead').textContent = m.dead > 0 ? m.dead + ' functions' : 'None';
  document.getElementById('tt-churn').textContent = m.churn + ' commits';
  document.getElementById('tt-layer').textContent = m.layer;

  var bar = document.getElementById('tt-bar');
  bar.style.width = m.mi + '%';
  bar.style.background = m.mi >= {theme.mi_healthy} ? '{healthy_base}' : m.mi >= {theme.mi_moderate} ? '{moderate_base}' : '{complex_base}';

  tooltip.classList.add('visible');
  var left = cx + 16;
  var top = cy - 16;
  if (left + 240 > window.innerWidth) left = cx - 240;
  if (top + 200 > window.innerHeight) top = cy - 200;
  tooltip.style.left = left + 'px';
  tooltip.style.top = top + 'px';
}}

// --- Zoom & Pan ---
var viewBox = svgEl.viewBox.baseVal;
var isPanning = false;
var startPoint = {{ x: 0, y: 0 }};
var startViewBox = {{ x: 0, y: 0 }};

var container = document.getElementById('canvas');

// Throttle helper — limit re-renders during zoom/pan
var interactTimer = null;
function startInteraction() {{
  container.classList.add('interacting');
  clearTimeout(interactTimer);
}}
function endInteraction() {{
  clearTimeout(interactTimer);
  interactTimer = setTimeout(function() {{
    container.classList.remove('interacting');
  }}, 200);
}}

container.addEventListener('wheel', function(e) {{
  e.preventDefault();
  startInteraction();
  var scale = e.deltaY > 0 ? 1.1 : 0.9;
  var rect = svgEl.getBoundingClientRect();
  var mx = (e.clientX - rect.left) / rect.width;
  var my = (e.clientY - rect.top) / rect.height;

  var newW = viewBox.width * scale;
  var newH = viewBox.height * scale;
  viewBox.x += (viewBox.width - newW) * mx;
  viewBox.y += (viewBox.height - newH) * my;
  viewBox.width = newW;
  viewBox.height = newH;
  endInteraction();
}}, {{ passive: false }});

container.addEventListener('mousedown', function(e) {{
  if (e.button !== 0) return;
  isPanning = true;
  startInteraction();
  startPoint = {{ x: e.clientX, y: e.clientY }};
  startViewBox = {{ x: viewBox.x, y: viewBox.y }};
}});

window.addEventListener('mousemove', function(e) {{
  if (!isPanning) return;
  var rect = svgEl.getBoundingClientRect();
  var dx = (e.clientX - startPoint.x) / rect.width * viewBox.width;
  var dy = (e.clientY - startPoint.y) / rect.height * viewBox.height;
  viewBox.x = startViewBox.x - dx;
  viewBox.y = startViewBox.y - dy;
}});

window.addEventListener('mouseup', function() {{
  if (isPanning) endInteraction();
  isPanning = false;
}});
</script>
</body>
</html>
"""
