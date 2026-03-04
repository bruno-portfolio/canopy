from __future__ import annotations

from canopy.config import Config, LayerConfig
from canopy.layout.layers import (
    _build_layer_list,
    _default_label,
    _match_layer,
    assign_layers,
)
from canopy.models import (
    Dependency,
    Layer,
    Module,
    ProjectData,
)

# ---------------------------------------------------------------------------
# Layer matching
# ---------------------------------------------------------------------------


class TestMatchLayer:
    def test_exact_match(self):
        cfg = Config(
            layers={
                "core": LayerConfig(modules=["_core"]),
                "data": LayerConfig(modules=["cepea"]),
            }
        )
        assert _match_layer("agrobr._core", cfg) == "core"
        assert _match_layer("agrobr.cepea", cfg) == "data"

    def test_no_match(self):
        cfg = Config(layers={"core": LayerConfig(modules=["_core"])})
        assert _match_layer("agrobr.unknown", cfg) == "uncategorized"

    def test_first_wins(self):
        cfg = Config(
            layers={
                "first": LayerConfig(modules=["shared"]),
                "second": LayerConfig(modules=["shared"]),
            }
        )
        assert _match_layer("agrobr.shared", cfg) == "first"

    def test_empty_config(self):
        cfg = Config(layers={})
        assert _match_layer("agrobr.anything", cfg) == "uncategorized"


# ---------------------------------------------------------------------------
# Default label
# ---------------------------------------------------------------------------


class TestDefaultLabel:
    def test_underscore(self):
        assert _default_label("data_sources") == "Data Sources"

    def test_simple(self):
        assert _default_label("core") == "Core"

    def test_leading_underscore(self):
        assert _default_label("_core") == "Core"


# ---------------------------------------------------------------------------
# Layer list construction
# ---------------------------------------------------------------------------


class TestBuildLayerList:
    def test_ring_order(self):
        cfg = Config(
            layers={
                "core": LayerConfig(modules=["_core"]),
                "infra": LayerConfig(modules=["_cache"], label="Infrastructure"),
                "data": LayerConfig(modules=["cepea"]),
            }
        )
        layers = _build_layer_list(cfg, has_uncategorized=False)
        assert len(layers) == 3
        assert layers[0] == Layer(name="core", ring=0, label="Core")
        assert layers[1] == Layer(name="infra", ring=1, label="Infrastructure")
        assert layers[2] == Layer(name="data", ring=2, label="Data")

    def test_uncategorized_outermost(self):
        cfg = Config(layers={"core": LayerConfig(modules=["_core"])})
        layers = _build_layer_list(cfg, has_uncategorized=True)
        assert len(layers) == 2
        assert layers[1] == Layer(name="uncategorized", ring=1, label="Uncategorized")

    def test_no_uncategorized(self):
        cfg = Config(layers={"core": LayerConfig(modules=["_core"])})
        layers = _build_layer_list(cfg, has_uncategorized=False)
        assert len(layers) == 1
        assert layers[0].name == "core"


# ---------------------------------------------------------------------------
# assign_layers integration
# ---------------------------------------------------------------------------


class TestAssignLayers:
    def test_basic_assignment(self):
        data = ProjectData(
            modules=[
                Module(name="agrobr._core", lines=100, funcs=5, mi=70.0, cc=3.0),
                Module(name="agrobr.cepea", lines=200, funcs=8, mi=45.0, cc=5.0),
            ]
        )
        cfg = Config(
            layers={
                "core": LayerConfig(modules=["_core"]),
                "data": LayerConfig(modules=["cepea"]),
            }
        )
        result = assign_layers(data, cfg)
        assert result.modules[0].layer == "core"
        assert result.modules[1].layer == "data"
        assert len(result.layers) == 2

    def test_uncategorized(self):
        data = ProjectData(
            modules=[
                Module(name="agrobr.unknown", lines=50, funcs=2, mi=80.0, cc=1.0),
            ]
        )
        cfg = Config(layers={"core": LayerConfig(modules=["_core"])})
        result = assign_layers(data, cfg)
        assert result.modules[0].layer == "uncategorized"
        assert any(la.name == "uncategorized" for la in result.layers)

    def test_no_config_layers(self):
        data = ProjectData(
            modules=[
                Module(name="pkg.mod", lines=50, funcs=2, mi=80.0, cc=1.0),
            ]
        )
        cfg = Config(layers={})
        result = assign_layers(data, cfg)
        assert result.modules[0].layer == "uncategorized"
        assert len(result.layers) == 1
        assert result.layers[0].ring == 0

    def test_empty_modules(self):
        data = ProjectData(modules=[])
        cfg = Config(layers={"core": LayerConfig(modules=["_core"])})
        result = assign_layers(data, cfg)
        assert result.modules == []
        assert result.layers == []

    def test_preserves_fields(self):
        data = ProjectData(
            modules=[
                Module(
                    name="agrobr._core",
                    lines=100,
                    funcs=5,
                    mi=70.0,
                    cc=3.0,
                    dead=2,
                    churn=7,
                    desc="Core module",
                ),
            ],
            dependencies=[
                Dependency(from_module="agrobr.cepea", to_module="agrobr._core"),
            ],
        )
        cfg = Config(layers={"core": LayerConfig(modules=["_core"])})
        result = assign_layers(data, cfg)
        mod = result.modules[0]
        assert mod.lines == 100
        assert mod.dead == 2
        assert mod.churn == 7
        assert mod.desc == "Core module"
        assert result.dependencies == data.dependencies

    def test_five_layers(self):
        cfg = Config(
            layers={
                "a": LayerConfig(modules=["ma"]),
                "b": LayerConfig(modules=["mb"]),
                "c": LayerConfig(modules=["mc"]),
                "d": LayerConfig(modules=["md"]),
                "e": LayerConfig(modules=["me"]),
            }
        )
        data = ProjectData(
            modules=[Module(name=f"pkg.m{c}", lines=10, funcs=1, mi=90.0, cc=1.0) for c in "abcde"]
        )
        result = assign_layers(data, cfg)
        assert len(result.layers) == 5
        for i, layer in enumerate(result.layers):
            assert layer.ring == i

    def test_all_matched_no_uncategorized(self):
        cfg = Config(
            layers={
                "core": LayerConfig(modules=["_core"]),
                "data": LayerConfig(modules=["cepea"]),
            }
        )
        data = ProjectData(
            modules=[
                Module(name="agrobr._core", lines=100, funcs=5, mi=70.0, cc=3.0),
                Module(name="agrobr.cepea", lines=200, funcs=8, mi=45.0, cc=5.0),
            ]
        )
        result = assign_layers(data, cfg)
        assert not any(la.name == "uncategorized" for la in result.layers)
