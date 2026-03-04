from __future__ import annotations

import math
from collections import defaultdict

from canopy.config import Config
from canopy.layout.collapse import collapse_overflow
from canopy.models import LayoutResult, Module, NodePosition, ProjectData, RingPosition

_CORE_NODE_RADIUS = 35.0
_CORE_ORBIT_SCALE = 1.4  # Multi-core orbit radius = node_radius * scale
_MIN_NODE_RADIUS = 10.0
_MAX_NODE_RADIUS = 32.0
_NODE_SCALE = 0.75
_JITTER_AMPLITUDE = 15.0
_JITTER_FREQUENCY = 3.7
_RING_MARGIN = 80.0
_MIN_RING_RADIUS = 100.0
_NODE_GAP = 6.0


def _node_radius(lines: int, is_core: bool) -> float:
    if is_core:
        return _CORE_NODE_RADIUS
    return max(_MIN_NODE_RADIUS, min(_MAX_NODE_RADIUS, math.sqrt(lines) * _NODE_SCALE))


def compute_layout(project_data: ProjectData, cfg: Config) -> LayoutResult:
    if not project_data.modules:
        return LayoutResult()

    layer_map: dict[str, int] = {layer.name: layer.ring for layer in project_data.layers}

    # Group modules by layer, sort by LOC desc
    ring_modules: dict[str, list[Module]] = defaultdict(list)
    for m in project_data.modules:
        ring_modules[m.layer].append(m)
    for mods in ring_modules.values():
        mods.sort(key=lambda m: m.lines, reverse=True)

    # Identify core (ring 0) and non-core layers
    core_layer: str | None = None
    non_core_layers: list[str] = []
    for layer in project_data.layers:
        if layer.ring == 0:
            core_layer = layer.name
        else:
            non_core_layers.append(layer.name)

    # Sort non-core layers by ring index
    non_core_layers.sort(key=lambda name: layer_map[name])

    # Step 1 — Ring radii
    width = cfg.output.width
    height = cfg.output.height
    max_radius = min(width, height) / 2 - _RING_MARGIN
    num_rings = len(non_core_layers)
    ring_radii: list[float] = []
    if num_rings > 0:
        step = (max_radius - _MIN_RING_RADIUS) / max(1, num_rings - 1)
        ring_radii = [_MIN_RING_RADIUS + step * i for i in range(num_rings)]

    nodes: list[NodePosition] = []

    # Step 2 — Core nodes (distributed in small orbit when multiple)
    if core_layer and core_layer in ring_modules:
        core_mods = ring_modules[core_layer]
        count = len(core_mods)
        if count == 1:
            nodes.append(
                NodePosition(name=core_mods[0].name, x=0.0, y=0.0, radius=_CORE_NODE_RADIUS)
            )
        else:
            # Spread around a small orbit so labels don't overlap
            orbit_r = _CORE_NODE_RADIUS * _CORE_ORBIT_SCALE
            for i, m in enumerate(core_mods):
                angle = 2 * math.pi * i / count - math.pi / 2
                nodes.append(
                    NodePosition(
                        name=m.name,
                        x=math.cos(angle) * orbit_r,
                        y=math.sin(angle) * orbit_r,
                        radius=_node_radius(m.lines, is_core=True),
                    )
                )

    # Step 3 — Overflow collapse per ring
    for idx, layer_name in enumerate(non_core_layers):
        mods = ring_modules.get(layer_name, [])
        if not mods:
            continue
        r = ring_radii[idx]
        max_r = max(_node_radius(m.lines, False) for m in mods)
        capacity = int(2 * math.pi * r / (2 * max_r + _NODE_GAP))
        capacity = max(capacity, 1)
        if len(mods) > capacity:
            ring_modules[layer_name] = collapse_overflow(mods, capacity)

    # Step 4 — Sector allocation
    total_modules = sum(len(ring_modules.get(ln, [])) for ln in non_core_layers)
    sector_starts: dict[str, float] = {}
    sector_spans: dict[str, float] = {}
    accumulated = 0.0
    for layer_name in non_core_layers:
        count = len(ring_modules.get(layer_name, []))
        span = (count / total_modules) * 2 * math.pi if total_modules > 0 else 0.0
        sector_starts[layer_name] = accumulated
        sector_spans[layer_name] = span
        accumulated += span

    # Step 5 — Position non-core nodes
    for idx, layer_name in enumerate(non_core_layers):
        mods = ring_modules.get(layer_name, [])
        if not mods:
            continue
        r = ring_radii[idx]
        start = sector_starts[layer_name]
        span = sector_spans[layer_name]
        count = len(mods)
        for i, m in enumerate(mods):
            angle = start + span * (i + 1) / (count + 1)
            jitter = math.sin(i * _JITTER_FREQUENCY) * _JITTER_AMPLITUDE
            effective_r = r + jitter
            x = math.cos(angle) * effective_r
            y = math.sin(angle) * effective_r
            nodes.append(
                NodePosition(
                    name=m.name,
                    x=x,
                    y=y,
                    radius=_node_radius(m.lines, False),
                )
            )

    # Step 6 — Ring positions
    layer_by_name = {la.name: la for la in project_data.layers}
    rings: list[RingPosition] = []
    for idx, layer_name in enumerate(non_core_layers):
        layer = layer_by_name[layer_name]
        rings.append(RingPosition(layer.name, ring_radii[idx], layer.label))

    return LayoutResult(nodes=nodes, rings=rings)
