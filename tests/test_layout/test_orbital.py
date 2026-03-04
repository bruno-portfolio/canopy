from __future__ import annotations

import math

import pytest

from canopy.config import Config, OutputConfig
from canopy.layout.orbital import _node_radius, compute_layout
from canopy.models import Layer, LayoutResult, Module, ProjectData


def _cfg(width: int = 1000, height: int = 800) -> Config:
    return Config(output=OutputConfig(width=width, height=height))


def _mod(name: str, lines: int, *, layer: str = "infra") -> Module:
    return Module(name=name, lines=lines, funcs=1, mi=50.0, cc=2.0, layer=layer)


def _pd(
    modules: list[Module],
    layers: list[Layer] | None = None,
) -> ProjectData:
    if layers is None:
        layers = [Layer("core", 0, "Core"), Layer("infra", 1, "Infra")]
    return ProjectData(modules=modules, layers=layers)


class TestCorePositioning:
    def test_core_at_origin(self):
        pd = _pd([_mod("app", 500, layer="core")])
        result = compute_layout(pd, _cfg())
        core = [n for n in result.nodes if n.name == "app"]
        assert len(core) == 1
        assert core[0].x == 0.0
        assert core[0].y == 0.0

    def test_core_radius(self):
        pd = _pd([_mod("app", 500, layer="core")])
        result = compute_layout(pd, _cfg())
        core = [n for n in result.nodes if n.name == "app"]
        assert core[0].radius == 35.0


class TestNodeRadius:
    def test_formula(self):
        r = _node_radius(400, False)
        assert r == pytest.approx(math.sqrt(400) * 0.75)

    def test_clamp_min(self):
        r = _node_radius(1, False)
        assert r == 10.0

    def test_clamp_max(self):
        r = _node_radius(10000, False)
        assert r == 32.0

    def test_core_override(self):
        r = _node_radius(1, True)
        assert r == 35.0


class TestSingleRing:
    def test_distribution(self):
        mods = [_mod(f"m{i}", 50) for i in range(5)]
        pd = _pd(mods)
        result = compute_layout(pd, _cfg())
        non_core = [n for n in result.nodes if n.name.startswith("m")]
        assert len(non_core) == 5
        # All should be at roughly the same distance from center
        dists = [math.sqrt(n.x**2 + n.y**2) for n in non_core]
        mean_dist = sum(dists) / len(dists)
        for d in dists:
            assert d == pytest.approx(mean_dist, abs=30)  # jitter tolerance


class TestSorting:
    def test_sort_by_loc_desc(self):
        mods = [_mod("small", 10), _mod("big", 1000)]
        pd = _pd(mods)
        result = compute_layout(pd, _cfg())
        non_core = [n for n in result.nodes if not n.name.startswith("_")]
        # big should come first in sector (earlier index = lower angle within sector)
        big_node = next(n for n in non_core if n.name == "big")
        small_node = next(n for n in non_core if n.name == "small")
        big_angle = math.atan2(big_node.y, big_node.x) % (2 * math.pi)
        small_angle = math.atan2(small_node.y, small_node.x) % (2 * math.pi)
        assert big_angle < small_angle


class TestDeterminism:
    def test_deterministic_jitter(self):
        mods = [_mod(f"m{i}", 50) for i in range(10)]
        pd = _pd(mods)
        r1 = compute_layout(pd, _cfg())
        r2 = compute_layout(pd, _cfg())
        for a, b in zip(r1.nodes, r2.nodes, strict=True):
            assert a.x == b.x
            assert a.y == b.y


class TestRingRadii:
    def test_scale_to_canvas(self):
        mods = [_mod("m1", 50)]
        pd = _pd(mods)
        big = compute_layout(pd, _cfg(1000, 800))
        small = compute_layout(pd, _cfg(500, 400))
        big_ring = big.rings[0].radius if big.rings else 0
        small_ring = small.rings[0].radius if small.rings else 0
        # Both should have rings, but with only 1 non-core layer both start at MIN_RING_RADIUS
        assert big_ring >= small_ring or big_ring == small_ring

    def test_multiple_rings_radii(self):
        layers = [
            Layer("core", 0, "Core"),
            Layer("infra", 1, "Infra"),
            Layer("api", 2, "API"),
            Layer("ui", 3, "UI"),
        ]
        mods = [
            _mod("m1", 50, layer="infra"),
            _mod("m2", 50, layer="api"),
            _mod("m3", 50, layer="ui"),
        ]
        pd = _pd(mods, layers)
        result = compute_layout(pd, _cfg())
        radii = [r.radius for r in result.rings]
        assert radii == sorted(radii)
        assert len(radii) == 3


class TestEdgeCases:
    def test_empty_project(self):
        pd = ProjectData()
        result = compute_layout(pd, _cfg())
        assert result == LayoutResult()

    def test_only_core(self):
        layers = [Layer("core", 0, "Core")]
        pd = _pd([_mod("app", 500, layer="core")], layers)
        result = compute_layout(pd, _cfg())
        assert len(result.nodes) == 1
        assert len(result.rings) == 0


class TestSectorProportional:
    def test_proportional_sectors(self):
        layers = [
            Layer("core", 0, "Core"),
            Layer("infra", 1, "Infra"),
            Layer("api", 2, "API"),
        ]
        mods = [
            *[_mod(f"infra{i}", 50, layer="infra") for i in range(6)],
            *[_mod(f"api{i}", 50, layer="api") for i in range(2)],
        ]
        pd = _pd(mods, layers)
        result = compute_layout(pd, _cfg())
        infra_nodes = [n for n in result.nodes if n.name.startswith("infra")]
        api_nodes = [n for n in result.nodes if n.name.startswith("api")]
        # Infra has 6/8 of total, api has 2/8 — infra should span wider angles
        infra_angles = sorted(math.atan2(n.y, n.x) for n in infra_nodes)
        api_angles = sorted(math.atan2(n.y, n.x) for n in api_nodes)
        infra_span = infra_angles[-1] - infra_angles[0]
        api_span = api_angles[-1] - api_angles[0] if len(api_angles) > 1 else 0.0
        assert infra_span > api_span


class TestNoOverlap:
    def test_no_overlap(self):
        layers = [Layer("core", 0, "Core"), Layer("infra", 1, "Infra")]
        mods = [_mod(f"m{i}", 10 + i * 5, layer="infra") for i in range(100)]
        pd = _pd(mods, layers)
        result = compute_layout(pd, _cfg())
        non_core = [n for n in result.nodes if n.x != 0.0 or n.y != 0.0]
        for i, a in enumerate(non_core):
            for b in non_core[i + 1 :]:
                dist = math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)
                assert dist >= a.radius + b.radius - 1.0  # 1px tolerance


class TestOverflowCollapse:
    def test_overflow_triggers_collapse(self):
        layers = [Layer("core", 0, "Core"), Layer("infra", 1, "Infra")]
        mods = [_mod(f"m{i}", 10 + i, layer="infra") for i in range(100)]
        pd = _pd(mods, layers)
        result = compute_layout(pd, _cfg())
        assert len(result.nodes) < 100


class TestRingPositions:
    def test_ring_positions_match_layers(self):
        layers = [
            Layer("core", 0, "Core"),
            Layer("infra", 1, "Infra"),
            Layer("api", 2, "API"),
        ]
        mods = [
            _mod("m1", 50, layer="infra"),
            _mod("m2", 50, layer="api"),
        ]
        pd = _pd(mods, layers)
        result = compute_layout(pd, _cfg())
        ring_names = {r.layer_name for r in result.rings}
        assert ring_names == {"infra", "api"}
        for r in result.rings:
            layer = next(la for la in layers if la.name == r.layer_name)
            assert r.label == layer.label
