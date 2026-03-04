"""SVG renderer for canopy orbital diagrams.

Note on coordinate systems: the layout engine (orbital.py) uses standard
math coordinates where positive Y points up. SVG has positive Y pointing
down. The translation ``svg_y = cy + node.y`` implicitly mirrors the Y
axis, but since the orbital distribution is radially symmetric the visual
result is equivalent. We accept this mirroring and do not invert Y.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from random import Random
from xml.sax.saxutils import escape

from canopy.layout.collapse import COLLAPSED_PREFIX
from canopy.models import Dependency, LayoutResult, Module, NodePosition, ProjectData

from .theme import HealthColors, Theme, compute_stats, health_colors


def _stable_hash(s: str) -> int:
    """Deterministic hash independent of PYTHONHASHSEED."""
    return int(hashlib.sha256(s.encode()).hexdigest()[:16], 16)


def _fmt(v: float) -> str:
    return f"{v:.1f}"


@dataclass
class _RenderContext:
    parts: list[str] = field(default_factory=list)
    theme: Theme = field(default_factory=Theme)
    cx: float = 0.0
    cy: float = 0.0
    module_map: dict[str, Module] = field(default_factory=dict)
    pos_map: dict[str, NodePosition] = field(default_factory=dict)
    project_name: str = ""
    project_data: ProjectData = field(default_factory=ProjectData)
    layout: LayoutResult = field(default_factory=LayoutResult)
    core_layer: str | None = None

    def svg_xy(self, node: NodePosition) -> tuple[float, float]:
        return self.cx + node.x, self.cy + node.y

    def resolve_dep(
        self, dep: Dependency
    ) -> tuple[Module, Module, float, float, float, float] | None:
        src_mod = self.module_map.get(dep.from_module)
        tgt_mod = self.module_map.get(dep.to_module)
        if not src_mod or not tgt_mod:
            return None
        src_pos = self.pos_map.get(dep.from_module)
        tgt_pos = self.pos_map.get(dep.to_module)
        if not src_pos or not tgt_pos:
            return None
        sx, sy = self.cx + src_pos.x, self.cy + src_pos.y
        tx, ty = self.cx + tgt_pos.x, self.cy + tgt_pos.y
        return src_mod, tgt_mod, sx, sy, tx, ty


# ---------------------------------------------------------------------------
# 1. Defs: gradients and filters
# ---------------------------------------------------------------------------


def _render_defs(ctx: _RenderContext) -> None:
    t = ctx.theme
    ctx.parts.append("<defs>")
    # Background radial gradient
    ctx.parts.append(
        f'<radialGradient id="bgGrad" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="{t.bg_inner}"/>'
        f'<stop offset="50%" stop-color="{t.bg_mid}"/>'
        f'<stop offset="100%" stop-color="{t.bg_outer}"/>'
        f"</radialGradient>"
    )
    # Node glow filter
    ctx.parts.append(
        '<filter id="nodeGlow" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="6" result="blur"/>'
        "<feMerge>"
        '<feMergeNode in="blur"/>'
        '<feMergeNode in="SourceGraphic"/>'
        "</feMerge>"
        "</filter>"
    )
    # Soft glow (ambient)
    ctx.parts.append(
        '<filter id="softGlow" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="12"/>'
        "</filter>"
    )
    # Churn pulse filter
    ctx.parts.append(
        '<filter id="churnPulse" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="4" result="blur"/>'
        "<feMerge>"
        '<feMergeNode in="blur"/>'
        '<feMergeNode in="SourceGraphic"/>'
        "</feMerge>"
        "</filter>"
    )
    ctx.parts.append("</defs>")


# ---------------------------------------------------------------------------
# 2. Background
# ---------------------------------------------------------------------------


def _render_background(ctx: _RenderContext) -> None:
    t = ctx.theme
    ctx.parts.append(f'<rect width="{t.width}" height="{t.height}" fill="url(#bgGrad)"/>')


# ---------------------------------------------------------------------------
# 3. Stars
# ---------------------------------------------------------------------------


def _render_stars(ctx: _RenderContext) -> None:
    t = ctx.theme
    rng = Random(_stable_hash(ctx.project_name))
    for _ in range(t.star_count):
        sx = rng.uniform(0, t.width)
        sy = rng.uniform(0, t.height)
        sr = rng.uniform(t.star_min_r, t.star_max_r)
        so = rng.uniform(t.star_min_opacity, t.star_max_opacity)
        ctx.parts.append(
            f'<circle cx="{_fmt(sx)}" cy="{_fmt(sy)}" r="{_fmt(sr)}"'
            f' fill="{t.star_fill}" opacity="{_fmt(so)}"/>'
        )


# ---------------------------------------------------------------------------
# 4. Rings
# ---------------------------------------------------------------------------


def _render_rings(ctx: _RenderContext) -> None:
    t = ctx.theme
    for ring in ctx.layout.rings:
        is_infra = ring.layer_name == "infra"
        stroke = t.ring_infra if is_infra else t.ring_default
        dash = ' stroke-dasharray="8 4"' if is_infra else ""
        ctx.parts.append(
            f'<circle cx="{_fmt(ctx.cx)}" cy="{_fmt(ctx.cy)}"'
            f' r="{_fmt(ring.radius)}" fill="none" stroke="{stroke}"'
            f' stroke-width="0.5" opacity="0.3"{dash}/>'
        )


# ---------------------------------------------------------------------------
# 5. Ring labels
# ---------------------------------------------------------------------------


def _render_ring_labels(ctx: _RenderContext) -> None:
    t = ctx.theme
    for ring in ctx.layout.rings:
        # Position at angle -π/2 - 0.35 (just left of top)
        angle = -math.pi / 2 - 0.35
        lx = ctx.cx + ring.radius * math.cos(angle)
        ly = ctx.cy + ring.radius * math.sin(angle)
        ctx.parts.append(
            f'<text x="{_fmt(lx)}" y="{_fmt(ly)}"'
            f' font-family="monospace" font-size="8" font-weight="600"'
            f' fill="{t.text_muted}" text-anchor="start"'
            f' transform="rotate(-70 {_fmt(lx)} {_fmt(ly)})">'
            f"{escape(ring.label)}</text>"
        )


# ---------------------------------------------------------------------------
# 6. Dependencies
# ---------------------------------------------------------------------------


def _render_dependencies(ctx: _RenderContext) -> None:
    _render_core_deps(ctx)
    _render_infra_deps(ctx)
    _render_significant_deps(ctx)


def _render_core_deps(ctx: _RenderContext) -> None:
    """Lines from core modules to infra modules."""
    t = ctx.theme
    if not ctx.core_layer:
        return
    for dep in ctx.project_data.dependencies:
        resolved = ctx.resolve_dep(dep)
        if not resolved:
            continue
        src_mod, tgt_mod, sx, sy, tx, ty = resolved
        if src_mod.layer != ctx.core_layer or tgt_mod.layer == ctx.core_layer:
            continue
        ctx.parts.append(
            f'<line x1="{_fmt(sx)}" y1="{_fmt(sy)}"'
            f' x2="{_fmt(tx)}" y2="{_fmt(ty)}"'
            f' stroke="{t.dep_core_infra}" stroke-width="0.5" opacity="0.12"/>'
        )


def _render_infra_deps(ctx: _RenderContext) -> None:
    """Light lines for low-weight dependencies from infra outward."""
    t = ctx.theme
    for dep in ctx.project_data.dependencies:
        if dep.weight > 0.5:
            continue
        resolved = ctx.resolve_dep(dep)
        if not resolved:
            continue
        src_mod, _tgt_mod, sx, sy, tx, ty = resolved
        if ctx.core_layer and src_mod.layer == ctx.core_layer:
            continue
        ctx.parts.append(
            f'<line x1="{_fmt(sx)}" y1="{_fmt(sy)}"'
            f' x2="{_fmt(tx)}" y2="{_fmt(ty)}"'
            f' stroke="{t.dep_light}" stroke-width="0.5" opacity="0.15"/>'
        )


def _render_significant_deps(ctx: _RenderContext) -> None:
    """Bezier curves for significant dependencies (weight >= 0.3, non-core)."""
    t = ctx.theme
    for dep in ctx.project_data.dependencies:
        if dep.weight < 0.3:
            continue
        resolved = ctx.resolve_dep(dep)
        if not resolved:
            continue
        src_mod, _tgt_mod, sx, sy, tx, ty = resolved
        if ctx.core_layer and src_mod.layer == ctx.core_layer:
            continue
        # Control point pulled 30% toward center
        mx, my = (sx + tx) / 2, (sy + ty) / 2
        cpx = mx + (ctx.cx - mx) * 0.3
        cpy = my + (ctx.cy - my) * 0.3
        ctx.parts.append(
            f'<path d="M{_fmt(sx)},{_fmt(sy)}'
            f" Q{_fmt(cpx)},{_fmt(cpy)}"
            f' {_fmt(tx)},{_fmt(ty)}"'
            f' fill="none" stroke="{t.dep_significant}"'
            f' stroke-width="0.8" opacity="0.2"/>'
        )


# ---------------------------------------------------------------------------
# 7. Nodes
# ---------------------------------------------------------------------------


def _render_nodes(ctx: _RenderContext) -> None:
    for node in ctx.layout.nodes:
        _render_single_node(ctx, node)


def _render_single_node(ctx: _RenderContext, node: NodePosition) -> None:
    mod = ctx.module_map.get(node.name)
    if not mod:
        return
    hc = health_colors(ctx.theme, mod.mi)
    is_core = ctx.core_layer and mod.layer == ctx.core_layer
    ctx.parts.append(f'<g data-module="{escape(node.name)}">')
    _render_ambient_glow(ctx, node, hc, is_core)
    if mod.churn >= ctx.theme.churn_high:
        _render_churn_pulse(ctx, node, hc)
    _render_node_body(ctx, node, hc)
    if mod.dead > 0:
        _render_dead_spots(ctx, node, mod)
    _render_node_label(ctx, node, mod, is_core)
    ctx.parts.append("</g>")


def _render_ambient_glow(
    ctx: _RenderContext,
    node: NodePosition,
    hc: HealthColors,
    is_core: bool,
) -> None:
    t = ctx.theme
    sx, sy = ctx.svg_xy(node)
    opacity = t.ambient_opacity_core if is_core else t.ambient_opacity
    ctx.parts.append(
        f'<circle cx="{_fmt(sx)}" cy="{_fmt(sy)}"'
        f' r="{_fmt(node.radius * 2.5)}"'
        f' fill="{hc.glow}" opacity="{_fmt(opacity)}"'
        f' filter="url(#softGlow)"/>'
    )


def _render_churn_pulse(ctx: _RenderContext, node: NodePosition, hc: HealthColors) -> None:
    t = ctx.theme
    sx, sy = ctx.svg_xy(node)
    r = node.radius
    r_max = _fmt(r + 4)
    r_val = _fmt(r)
    ctx.parts.append(
        f'<circle cx="{_fmt(sx)}" cy="{_fmt(sy)}" r="{r_val}"'
        f' fill="none" stroke="{t.churn_stroke}" stroke-width="1.5"'
        f' opacity="0.4" filter="url(#churnPulse)">'
        f'<animate attributeName="r" values="{r_val};{r_max};{r_val}"'
        f' dur="3s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="0.4;0.1;0.4"'
        f' dur="3s" repeatCount="indefinite"/>'
        f"</circle>"
    )


def _render_node_body(ctx: _RenderContext, node: NodePosition, hc: HealthColors) -> None:
    sx, sy = ctx.svg_xy(node)
    r = node.radius
    # Shadow
    ctx.parts.append(
        f'<circle cx="{_fmt(sx + 1)}" cy="{_fmt(sy + 1)}"'
        f' r="{_fmt(r)}" fill="#000000" opacity="0.3"/>'
    )
    # Main body
    ctx.parts.append(
        f'<circle cx="{_fmt(sx)}" cy="{_fmt(sy)}"'
        f' r="{_fmt(r)}" fill="{hc.base}" filter="url(#nodeGlow)"/>'
    )
    # Highlight
    ctx.parts.append(
        f'<circle cx="{_fmt(sx)}" cy="{_fmt(sy - r * 0.3)}"'
        f' r="{_fmt(r * 0.6)}" fill="{hc.light}" opacity="0.15"/>'
    )
    # Specular
    ctx.parts.append(
        f'<circle cx="{_fmt(sx - r * 0.15)}" cy="{_fmt(sy - r * 0.35)}"'
        f' r="{_fmt(r * 0.2)}" fill="#ffffff" opacity="0.08"/>'
    )


def _render_dead_spots(ctx: _RenderContext, node: NodePosition, mod: Module) -> None:
    t = ctx.theme
    sx, sy = ctx.svg_xy(node)
    rng = Random(_stable_hash(f"{node.x:.1f},{node.y:.1f}"))
    count = min(mod.dead, 8)
    for _ in range(count):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(0, node.radius * 0.7)
        dx = dist * math.cos(angle)
        dy = dist * math.sin(angle)
        sr = rng.uniform(1.5, 3.0)
        ctx.parts.append(
            f'<circle cx="{_fmt(sx + dx)}" cy="{_fmt(sy + dy)}"'
            f' r="{_fmt(sr)}" fill="{t.dead_fill}"'
            f' opacity="{t.dead_opacity}"/>'
        )


# ---------------------------------------------------------------------------
# 8. Labels (rendered inside each node's <g> via _render_node_label)
# ---------------------------------------------------------------------------


def _render_node_label(
    ctx: _RenderContext, node: NodePosition, mod: Module, is_core: bool
) -> None:
    t = ctx.theme
    sx, sy = ctx.svg_xy(node)

    # Label text
    if node.name.startswith(COLLAPSED_PREFIX):
        label = escape(mod.desc) if mod.desc else "..."
    else:
        segment = node.name.rsplit(".", 1)[-1]
        segment = segment.lstrip("_")
        if len(segment) > 9:
            segment = segment[:9] + ".."
        label = escape(segment)

    # Font sizing
    if is_core:
        font_size, font_weight = 11, 700
    elif node.radius > 22:
        font_size, font_weight = 9, 600
    elif node.radius > 15:
        font_size, font_weight = 8, 600
    else:
        font_size, font_weight = 7, 600

    ctx.parts.append(
        f'<text x="{_fmt(sx)}" y="{_fmt(sy)}"'
        f' font-family="monospace" font-size="{font_size}"'
        f' font-weight="{font_weight}"'
        f' fill="{t.text_primary}" text-anchor="middle"'
        f' dy="0.35em">{label}</text>'
    )

    # LOC label (only for larger nodes and core)
    if is_core or node.radius > 18:
        loc_y = sy + node.radius + 14
        ctx.parts.append(
            f'<text x="{_fmt(sx)}" y="{_fmt(loc_y)}"'
            f' font-family="monospace" font-size="7"'
            f' fill="{t.text_muted}" text-anchor="middle"'
            f' dy="0.35em">{mod.lines} loc</text>'
        )


# ---------------------------------------------------------------------------
# 9. Core decoration
# ---------------------------------------------------------------------------


def _render_core_decoration(ctx: _RenderContext) -> None:
    if not ctx.core_layer:
        return
    has_core = any(
        (m := ctx.module_map.get(n.name)) is not None and m.layer == ctx.core_layer
        for n in ctx.layout.nodes
    )
    if not has_core:
        return
    t = ctx.theme
    core_r = ctx.layout.core_orbit_radius
    if core_r > 0:
        # Compute decoration radius from orbit + largest core node + margin
        core_nodes = [
            n
            for n in ctx.layout.nodes
            if (m := ctx.module_map.get(n.name)) and m.layer == ctx.core_layer
        ]
        max_node_r = max((n.radius for n in core_nodes), default=0.0)
        ring_r = core_r + max_node_r + 10.0
    else:
        ring_r = t.core_ring_radius
    ctx.parts.append(
        f'<circle cx="{_fmt(ctx.cx)}" cy="{_fmt(ctx.cy)}"'
        f' r="{_fmt(ring_r)}" fill="none"'
        f' stroke="{t.core_ring_stroke}" stroke-width="0.5"'
        f' stroke-dasharray="4 6" opacity="0.3">'
        f'<animateTransform attributeName="transform" type="rotate"'
        f' from="0 {_fmt(ctx.cx)} {_fmt(ctx.cy)}"'
        f' to="360 {_fmt(ctx.cx)} {_fmt(ctx.cy)}"'
        f' dur="60s" repeatCount="indefinite"/>'
        f"</circle>"
    )


# ---------------------------------------------------------------------------
# 10. Stats bar
# ---------------------------------------------------------------------------


def _render_stats_bar(ctx: _RenderContext) -> None:
    t = ctx.theme
    s = compute_stats(ctx.project_data.modules, t)
    if s.modules == 0:
        return

    stats = (
        f"{s.modules} modules | {s.lines} lines | "
        f"{s.healthy_pct}% healthy {s.moderate_pct}% moderate {s.complex_pct}% complex"
    )
    if s.dead_total > 0:
        stats += f" | {s.dead_total} dead"
    stats = escape(stats)

    y = t.height - 20
    ctx.parts.append(
        f'<text x="{_fmt(t.width / 2)}" y="{_fmt(y)}"'
        f' font-family="monospace" font-size="9"'
        f' fill="{t.text_very_muted}" text-anchor="middle"'
        f' dy="0.35em">{stats}</text>'
    )


# ---------------------------------------------------------------------------
# 11. Watermark
# ---------------------------------------------------------------------------


def _render_watermark(ctx: _RenderContext) -> None:
    t = ctx.theme
    ctx.parts.append(
        f'<text x="{_fmt(t.width - 15)}" y="{_fmt(t.height - 10)}"'
        f' font-family="monospace" font-size="10"'
        f' fill="{t.watermark_fill}" text-anchor="end"'
        f' dy="0.35em">{escape("canopy-code")}</text>'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_svg(
    project_data: ProjectData,
    layout: LayoutResult,
    theme: Theme,
) -> str:
    """Render a complete SVG string from project data and layout.

    Returns a GitHub-safe inline SVG with no ``<style>``, ``<script>``,
    ``onclick``, external fonts, or ``dominant-baseline``.
    """
    ctx = _RenderContext(
        theme=theme,
        cx=theme.width / 2,
        cy=theme.height / 2,
        module_map={m.name: m for m in project_data.modules},
        pos_map={n.name: n for n in layout.nodes},
        project_name=project_data.project_name,
        project_data=project_data,
        layout=layout,
        core_layer=next((la.name for la in project_data.layers if la.ring == 0), None),
    )

    ctx.parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {theme.width} {theme.height}">'
    )

    _render_defs(ctx)
    _render_background(ctx)
    _render_stars(ctx)
    _render_rings(ctx)
    _render_ring_labels(ctx)
    _render_dependencies(ctx)
    _render_nodes(ctx)
    _render_core_decoration(ctx)
    _render_stats_bar(ctx)
    _render_watermark(ctx)

    ctx.parts.append("</svg>")
    return "\n".join(ctx.parts)
