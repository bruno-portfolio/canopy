from __future__ import annotations

import math
from collections import defaultdict

from canopy.config import Config
from canopy.layout.collapse import collapse_overflow
from canopy.models import LayoutResult, Module, NodePosition, ProjectData, RingPosition

# Core node sizing
_CORE_MAX_RADIUS = 35.0
_CORE_MIN_RADIUS = 15.0
_CORE_CLEARANCE = 10.0
_CORE_TO_RING_GAP = 20.0

# Non-core node sizing
_MIN_NODE_RADIUS = 10.0
_MAX_NODE_RADIUS = 32.0
_NODE_SCALE = 0.75
_RING_MIN_NODE_RADIUS = 8.0

# Layout geometry
_JITTER_AMPLITUDE = 15.0
_JITTER_FREQUENCY = 3.7
_RING_MARGIN = 80.0
_MIN_RING_RADIUS = 100.0
_NODE_GAP = 6.0

# Collision avoidance
_REPULSION_ITERATIONS = 10
_REPULSION_STRENGTH = 0.5


def _core_node_radius(count: int) -> float:
    if count <= 1:
        return _CORE_MAX_RADIUS
    t = min((count - 2) / 10.0, 1.0)
    return _CORE_MAX_RADIUS - t * (_CORE_MAX_RADIUS - _CORE_MIN_RADIUS)


def _core_orbit_radius(count: int, node_r: float) -> float:
    if count <= 1:
        return 0.0
    return count * (2 * node_r + _CORE_CLEARANCE) / (2 * math.pi)


def _min_first_ring_radius(core_orbit_r: float, core_node_r: float) -> float:
    return max(_MIN_RING_RADIUS, core_orbit_r + core_node_r + _CORE_TO_RING_GAP)


def _node_radius(lines: int) -> float:
    return max(_MIN_NODE_RADIUS, min(_MAX_NODE_RADIUS, math.sqrt(lines) * _NODE_SCALE))


def _ring_capacity(ring_r: float, node_r: float) -> int:
    return max(1, int(2 * math.pi * ring_r / (2 * node_r + _NODE_GAP)))


def _ring_node_radius(base_r: float, count: int, ring_r: float) -> float:
    if count <= _ring_capacity(ring_r, base_r):
        return base_r
    fitted = (math.pi * ring_r / count) - _NODE_GAP / 2
    return max(_RING_MIN_NODE_RADIUS, fitted)


def _resolve_collisions(nodes: list[NodePosition], target_rs: list[float]) -> list[NodePosition]:
    xs = [n.x for n in nodes]
    ys = [n.y for n in nodes]
    rs = [n.radius for n in nodes]
    for _ in range(_REPULSION_ITERATIONS):
        moved = False
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                dx, dy = xs[j] - xs[i], ys[j] - ys[i]
                dist = math.hypot(dx, dy)
                min_dist = rs[i] + rs[j] + _NODE_GAP
                if dist < min_dist and dist > 0.01:
                    push = (min_dist - dist) * _REPULSION_STRENGTH / dist
                    # Split push equally between both nodes
                    xs[i] -= dx * push * 0.5
                    ys[i] -= dy * push * 0.5
                    xs[j] += dx * push * 0.5
                    ys[j] += dy * push * 0.5
                    moved = True
                elif dist <= 0.01:
                    xs[j] += min_dist * 0.5
                    moved = True
        # Re-project each node back to its assigned radial distance
        # (preserves angular spread from repulsion, restores ring membership)
        for i in range(len(nodes)):
            if target_rs[i] <= 0.01:
                continue  # single core at origin
            angle = math.atan2(ys[i], xs[i])
            xs[i] = math.cos(angle) * target_rs[i]
            ys[i] = math.sin(angle) * target_rs[i]
        if not moved:
            break
    return [NodePosition(n.name, xs[i], ys[i], rs[i]) for i, n in enumerate(nodes)]


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

    # Compute core geometry
    core_count = len(ring_modules.get(core_layer, [])) if core_layer else 0
    core_node_r = _core_node_radius(core_count)
    core_orbit_r = _core_orbit_radius(core_count, core_node_r)
    min_first_ring = _min_first_ring_radius(core_orbit_r, core_node_r)

    # Step 1 — Ring radii (pushed out if core is large)
    width = cfg.output.width
    height = cfg.output.height
    max_radius = min(width, height) / 2 - _RING_MARGIN
    num_rings = len(non_core_layers)
    ring_radii: list[float] = []
    if num_rings > 0:
        step = (max_radius - min_first_ring) / max(1, num_rings - 1)
        ring_radii = [min_first_ring + step * i for i in range(num_rings)]

    nodes: list[NodePosition] = []
    target_rs: list[float] = []

    # Step 2 — Core nodes
    if core_layer and core_layer in ring_modules:
        core_mods = ring_modules[core_layer]
        count = len(core_mods)
        if count == 1:
            nodes.append(NodePosition(name=core_mods[0].name, x=0.0, y=0.0, radius=core_node_r))
            target_rs.append(0.0)
        else:
            for i, m in enumerate(core_mods):
                angle = 2 * math.pi * i / count - math.pi / 2
                nodes.append(
                    NodePosition(
                        name=m.name,
                        x=math.cos(angle) * core_orbit_r,
                        y=math.sin(angle) * core_orbit_r,
                        radius=core_node_r,
                    )
                )
                target_rs.append(core_orbit_r)

    # Step 3 — Overflow collapse per ring (with shrink-first strategy)
    ring_fitted_radii: dict[str, float] = {}
    for idx, layer_name in enumerate(non_core_layers):
        mods = ring_modules.get(layer_name, [])
        if not mods:
            continue
        r = ring_radii[idx]
        max_r = max(_node_radius(m.lines) for m in mods)

        fitted_r = _ring_node_radius(max_r, len(mods), r)
        capacity = _ring_capacity(r, fitted_r)

        if len(mods) > capacity:
            ring_modules[layer_name] = collapse_overflow(mods, capacity)
        ring_fitted_radii[layer_name] = fitted_r

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
        fitted_r = ring_fitted_radii[layer_name]

        # Scale jitter to 0 when ring is >70% full
        capacity = _ring_capacity(r, fitted_r)
        fill_ratio = count / capacity

        jitter_scale = max(0.0, 1.0 - (fill_ratio - 0.7) / 0.3) if fill_ratio > 0.7 else 1.0

        for i, m in enumerate(mods):
            angle = start + span * (i + 1) / (count + 1)
            jitter = math.sin(i * _JITTER_FREQUENCY) * _JITTER_AMPLITUDE * jitter_scale
            effective_r = r + jitter
            x = math.cos(angle) * effective_r
            y = math.sin(angle) * effective_r

            node_r = min(_node_radius(m.lines), fitted_r)
            nodes.append(NodePosition(name=m.name, x=x, y=y, radius=node_r))
            target_rs.append(effective_r)

    # Step 6 — Collision avoidance
    nodes = _resolve_collisions(nodes, target_rs)

    # Step 7 — Ring positions
    layer_by_name = {la.name: la for la in project_data.layers}
    rings: list[RingPosition] = []
    for idx, layer_name in enumerate(non_core_layers):
        layer = layer_by_name[layer_name]
        rings.append(RingPosition(layer.name, ring_radii[idx], layer.label))

    return LayoutResult(nodes=nodes, rings=rings, core_orbit_radius=core_orbit_r)
