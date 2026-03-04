from __future__ import annotations

import pytest

from canopy.layout.collapse import collapse_overflow, collapse_small
from canopy.models import Dependency, Layer, Module, ProjectData


def _mod(name: str, lines: int, *, layer: str = "infra", **kw) -> Module:
    return Module(
        name=name,
        lines=lines,
        funcs=kw.get("funcs", 1),
        mi=kw.get("mi", 50.0),
        cc=kw.get("cc", 2.0),
        dead=kw.get("dead", 0),
        churn=kw.get("churn", 0),
        layer=layer,
    )


def _pd(modules: list[Module], deps: list[Dependency] | None = None) -> ProjectData:
    return ProjectData(
        modules=modules,
        dependencies=deps or [],
        layers=[Layer("infra", 1, "Infra"), Layer("api", 2, "API")],
    )


class TestCollapseSmall:
    def test_no_small_modules(self):
        mods = [_mod("a", 100), _mod("b", 200)]
        pd = _pd(mods)
        result = collapse_small(pd, min_loc=50)
        assert len(result.modules) == 2
        assert {m.name for m in result.modules} == {"a", "b"}

    def test_all_small_single_layer(self):
        mods = [_mod("a", 10), _mod("b", 20), _mod("c", 5)]
        pd = _pd(mods)
        result = collapse_small(pd, min_loc=50)
        assert len(result.modules) == 1
        assert result.modules[0].name == "_collapsed_infra"

    def test_mixed_modules(self):
        mods = [_mod("big", 100), _mod("s1", 10), _mod("s2", 20)]
        pd = _pd(mods)
        result = collapse_small(pd, min_loc=50)
        names = {m.name for m in result.modules}
        assert "big" in names
        assert "_collapsed_infra" in names
        assert len(result.modules) == 2

    def test_single_small_no_collapse(self):
        mods = [_mod("big", 100), _mod("small", 10)]
        pd = _pd(mods)
        result = collapse_small(pd, min_loc=50)
        assert len(result.modules) == 2
        assert {m.name for m in result.modules} == {"big", "small"}

    def test_collapsed_metrics(self):
        s1 = _mod("s1", 10, mi=40.0, cc=3.0, dead=1, churn=2, funcs=5)
        s2 = _mod("s2", 30, mi=60.0, cc=5.0, dead=3, churn=4, funcs=7)
        pd = _pd([s1, s2])
        result = collapse_small(pd, min_loc=50)
        collapsed = result.modules[0]
        assert collapsed.lines == 40
        assert collapsed.funcs == 12
        expected_mi = (40.0 * 10 + 60.0 * 30) / 40
        assert collapsed.mi == pytest.approx(expected_mi)
        assert collapsed.cc == 5.0
        assert collapsed.dead == 4
        assert collapsed.churn == 6

    def test_dependency_remap(self):
        mods = [_mod("big", 100), _mod("s1", 10), _mod("s2", 20)]
        deps = [Dependency("ext", "s1", 1.0)]
        pd = _pd(mods, deps)
        result = collapse_small(pd, min_loc=50)
        assert len(result.dependencies) == 1
        assert result.dependencies[0].to_module == "_collapsed_infra"

    def test_self_dep_removal(self):
        mods = [_mod("s1", 10), _mod("s2", 20)]
        deps = [Dependency("s1", "s2", 1.0)]
        pd = _pd(mods, deps)
        result = collapse_small(pd, min_loc=50)
        assert len(result.dependencies) == 0

    def test_duplicate_dep_merge(self):
        mods = [_mod("big", 100), _mod("s1", 10), _mod("s2", 20)]
        deps = [
            Dependency("big", "s1", 2.0),
            Dependency("big", "s2", 3.0),
        ]
        pd = _pd(mods, deps)
        result = collapse_small(pd, min_loc=50)
        assert len(result.dependencies) == 1
        assert result.dependencies[0].weight == pytest.approx(5.0)

    def test_empty_modules(self):
        pd = ProjectData()
        result = collapse_small(pd, min_loc=50)
        assert result.modules == []

    def test_preserves_layers(self):
        mods = [_mod("s1", 10), _mod("s2", 20)]
        pd = _pd(mods)
        result = collapse_small(pd, min_loc=50)
        assert result.layers == pd.layers

    def test_multiple_layers_independent(self):
        mods = [
            _mod("a1", 10, layer="infra"),
            _mod("a2", 20, layer="infra"),
            _mod("b1", 5, layer="api"),
            _mod("b2", 15, layer="api"),
        ]
        pd = _pd(mods)
        result = collapse_small(pd, min_loc=50)
        names = {m.name for m in result.modules}
        assert "_collapsed_infra" in names
        assert "_collapsed_api" in names
        assert len(result.modules) == 2


class TestCollapseOverflow:
    def test_basic(self):
        mods = [_mod(f"m{i}", 100 - i) for i in range(10)]
        result = collapse_overflow(mods, 5)
        assert len(result) == 5
        collapsed = [m for m in result if m.name.startswith("_collapsed_")]
        assert len(collapsed) == 1
        assert "+6 more" in collapsed[0].desc

    def test_all_fit(self):
        mods = [_mod(f"m{i}", 100) for i in range(3)]
        result = collapse_overflow(mods, 5)
        assert len(result) == 3
        assert all(not m.name.startswith("_collapsed_") for m in result)
