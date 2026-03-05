from __future__ import annotations

from unittest.mock import patch

from canopy.aggregator import _path_to_module, _process_vulture, _truncate, aggregate
from canopy.collectors import (
    RawChurnResult,
    RawFunctionCC,
    RawImportEdge,
    RawRadonResult,
    RawVultureResult,
)
from canopy.config import Config, LayerConfig

_MOCK_DISCOVER = "canopy.aggregator._discover_files"


def _mock_files(file_data: dict[str, int]):
    return patch(_MOCK_DISCOVER, return_value=file_data)


# ---------------------------------------------------------------------------
# Path conversion
# ---------------------------------------------------------------------------


class TestPathToModule:
    def test_simple_path(self):
        result = _path_to_module("src/agrobr/cepea/parsers.py", "src/agrobr/", "agrobr", 2)
        assert result == "agrobr.cepea"

    def test_init_py(self):
        result = _path_to_module("src/agrobr/cepea/__init__.py", "src/agrobr/", "agrobr", 2)
        assert result == "agrobr.cepea"

    def test_root_init(self):
        result = _path_to_module("src/agrobr/__init__.py", "src/agrobr/", "agrobr", 2)
        assert result == "agrobr"

    def test_windows_backslash(self):
        result = _path_to_module("src\\agrobr\\cepea\\parsers.py", "src/agrobr/", "agrobr", 2)
        assert result == "agrobr.cepea"

    def test_deep_truncation(self):
        result = _path_to_module(
            "src/agrobr/cepea/parsers/v1/handler.py", "src/agrobr/", "agrobr", 2
        )
        assert result == "agrobr.cepea"

    def test_depth_one(self):
        result = _path_to_module("src/agrobr/cepea/parsers.py", "src/agrobr/", "agrobr", 1)
        assert result == "agrobr"

    def test_depth_three(self):
        result = _path_to_module("src/agrobr/cepea/parsers/v1.py", "src/agrobr/", "agrobr", 3)
        assert result == "agrobr.cepea.parsers"


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_at_depth(self):
        assert _truncate("agrobr.cepea", 2) == "agrobr.cepea"

    def test_deeper(self):
        assert _truncate("agrobr.cepea.parsers", 2) == "agrobr.cepea"

    def test_shallower(self):
        assert _truncate("agrobr", 2) == "agrobr"

    def test_depth_one(self):
        assert _truncate("agrobr.cepea.parsers", 1) == "agrobr"


# ---------------------------------------------------------------------------
# aggregate — happy path
# ---------------------------------------------------------------------------


class TestAggregateHappyPath:
    def test_two_files_same_module_all_collectors(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {"sub/alpha.py": 100, "sub/beta.py": 50}

        radon = [
            RawRadonResult(
                path="src/mypkg/sub/alpha.py",
                mi=80.0,
                rank="A",
                functions=[RawFunctionCC("func_a", 3, False, "", 1)],
            ),
            RawRadonResult(
                path="src/mypkg/sub/beta.py",
                mi=60.0,
                rank="B",
                functions=[RawFunctionCC("func_b", 5, False, "", 1)],
            ),
        ]
        vulture = [
            RawVultureResult("src/mypkg/sub/alpha.py", 10, "function", "old", 60),
            RawVultureResult("src/mypkg/sub/beta.py", 20, "variable", "tmp", 80),
        ]
        churn = [
            RawChurnResult("src/mypkg/sub/alpha.py", 5),
            RawChurnResult("src/mypkg/sub/beta.py", 3),
        ]
        imports = [RawImportEdge("sub.alpha", "mypkg.sub.beta")]

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=imports,
                radon=radon,
                vulture=vulture,
                churn=churn,
            )

        assert len(result.modules) == 1
        mod = result.modules[0]
        assert mod.name == "mypkg.sub"
        assert mod.lines == 150
        assert mod.funcs == 2
        # MI weighted avg: (80*100 + 60*50) / 150 = 73.33
        assert mod.mi == 73.33
        # CC avg: (3 + 5) / 2 = 4.0
        assert mod.cc == 4.0
        assert mod.dead == 2
        assert mod.churn == 8
        # Self-dep after truncation
        assert len(result.dependencies) == 0


# ---------------------------------------------------------------------------
# aggregate — imports only
# ---------------------------------------------------------------------------


class TestAggregateImportsOnly:
    def test_module_in_imports_no_radon(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {"sub/alpha.py": 80}
        imports = [RawImportEdge("sub.alpha", "mypkg.other.beta")]

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=imports,
                radon=[],
                vulture=[],
                churn=[],
            )

        mod = result.modules[0]
        assert mod.lines == 80
        assert mod.mi == 100.0
        assert mod.cc == 0.0
        assert mod.funcs == 0


# ---------------------------------------------------------------------------
# aggregate — radon only
# ---------------------------------------------------------------------------


class TestAggregateRadonOnly:
    def test_module_in_radon_no_imports(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {"sub/alpha.py": 100}
        radon = [
            RawRadonResult(
                path="src/mypkg/sub/alpha.py",
                mi=75.0,
                rank="A",
                functions=[RawFunctionCC("func_a", 4, False, "", 1)],
            ),
        ]

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=[],
                radon=radon,
                vulture=[],
                churn=[],
            )

        mod = result.modules[0]
        assert mod.mi == 75.0
        assert mod.cc == 4.0
        assert len(result.dependencies) == 0


# ---------------------------------------------------------------------------
# aggregate — all empty
# ---------------------------------------------------------------------------


class TestAggregateAllEmpty:
    def test_no_crash(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {"sub/alpha.py": 10}

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=[],
                radon=[],
                vulture=[],
                churn=[],
            )

        mod = result.modules[0]
        assert mod.lines == 10
        assert mod.mi == 100.0
        assert mod.cc == 0.0
        assert mod.dead == 0
        assert mod.churn == 0


# ---------------------------------------------------------------------------
# CC overloads
# ---------------------------------------------------------------------------


class TestCCOverloads:
    def test_overload_dedup_max_complexity(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {"sub/alpha.py": 100}
        radon = [
            RawRadonResult(
                path="src/mypkg/sub/alpha.py",
                mi=70.0,
                rank="A",
                functions=[
                    RawFunctionCC("process", 2, False, "", 1),
                    RawFunctionCC("process", 5, False, "", 10),
                    RawFunctionCC("process", 3, False, "", 20),
                    RawFunctionCC("helper", 1, False, "", 30),
                ],
            ),
        ]

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=[],
                radon=radon,
                vulture=[],
                churn=[],
            )

        mod = result.modules[0]
        assert mod.funcs == 2
        # CC = avg(max(2,5,3)=5, 1) = 3.0
        assert mod.cc == 3.0


# ---------------------------------------------------------------------------
# Self-dependencies
# ---------------------------------------------------------------------------


class TestSelfDependencies:
    def test_self_dep_removed_after_truncation(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {"sub/a.py": 50, "sub/b.py": 50}
        imports = [RawImportEdge("sub.a", "mypkg.sub.b")]

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=imports,
                radon=[],
                vulture=[],
                churn=[],
            )

        assert len(result.dependencies) == 0


# ---------------------------------------------------------------------------
# Duplicate dependencies after truncation
# ---------------------------------------------------------------------------


class TestDuplicateDependenciesAfterTruncation:
    def test_merge_duplicates_with_weight(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {"a/x.py": 50, "b/p.py": 50}
        imports = [
            RawImportEdge("a.x", "mypkg.b.p"),
            RawImportEdge("a.y", "mypkg.b.q"),
        ]

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=imports,
                radon=[],
                vulture=[],
                churn=[],
            )

        assert len(result.dependencies) == 1
        dep = result.dependencies[0]
        assert dep.from_module == "mypkg.a"
        assert dep.to_module == "mypkg.b"
        assert dep.weight == 2.0


# ---------------------------------------------------------------------------
# Windows paths
# ---------------------------------------------------------------------------


class TestWindowsPaths:
    def test_backslash_in_all_collectors(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {"sub/alpha.py": 100}

        radon = [
            RawRadonResult(
                path="src\\mypkg\\sub\\alpha.py",
                mi=70.0,
                rank="A",
                functions=[RawFunctionCC("func_a", 3, False, "", 1)],
            ),
        ]
        vulture = [
            RawVultureResult("src\\mypkg\\sub\\alpha.py", 10, "function", "old", 60),
        ]
        churn = [RawChurnResult("src\\mypkg\\sub\\alpha.py", 5)]

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=[],
                radon=radon,
                vulture=vulture,
                churn=churn,
            )

        assert len(result.modules) == 1
        mod = result.modules[0]
        assert mod.name == "mypkg.sub"
        assert mod.mi == 70.0
        assert mod.dead == 1
        assert mod.churn == 5


# ---------------------------------------------------------------------------
# __init__.py handling
# ---------------------------------------------------------------------------


class TestInitPyHandling:
    def test_root_and_sub_init(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {
            "__init__.py": 10,
            "sub/__init__.py": 20,
            "sub/alpha.py": 30,
        }
        radon = [
            RawRadonResult(path="src/mypkg/__init__.py", mi=90.0, rank="A"),
            RawRadonResult(path="src/mypkg/sub/__init__.py", mi=80.0, rank="A"),
            RawRadonResult(path="src/mypkg/sub/alpha.py", mi=60.0, rank="B"),
        ]

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=[],
                radon=radon,
                vulture=[],
                churn=[],
            )

        by_name = {m.name: m for m in result.modules}
        assert "mypkg" in by_name
        assert "mypkg.sub" in by_name

        assert by_name["mypkg"].lines == 10
        assert by_name["mypkg"].mi == 90.0

        # mypkg.sub: init(20) + alpha(30) = 50 lines
        # MI weighted: (80*20 + 60*30) / 50 = 68.0
        assert by_name["mypkg.sub"].lines == 50
        assert by_name["mypkg.sub"].mi == 68.0


# ---------------------------------------------------------------------------
# Zero-line file
# ---------------------------------------------------------------------------


class TestModuleZeroLines:
    def test_empty_file(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {"sub/empty.py": 0}
        radon = [
            RawRadonResult(path="src/mypkg/sub/empty.py", mi=100.0, rank="A"),
        ]

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=[],
                radon=radon,
                vulture=[],
                churn=[],
            )

        mod = result.modules[0]
        assert mod.lines == 0
        # weight_total=0 → defaults to MI 100.0
        assert mod.mi == 100.0


# ---------------------------------------------------------------------------
# Depth=1
# ---------------------------------------------------------------------------


class TestDepthOne:
    def test_everything_collapses(self):
        cfg = Config(source="src/mypkg", module_depth=1)
        file_data = {"sub/alpha.py": 50, "other/beta.py": 50}
        imports = [RawImportEdge("sub.alpha", "mypkg.other.beta")]

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=imports,
                radon=[],
                vulture=[],
                churn=[],
            )

        assert len(result.modules) == 1
        assert result.modules[0].name == "mypkg"
        assert result.modules[0].lines == 100
        assert len(result.dependencies) == 0


# ---------------------------------------------------------------------------
# Full simulation (mini agrobr)
# ---------------------------------------------------------------------------


class TestFullSimulation:
    def test_mini_agrobr(self):
        cfg = Config(
            source="src/agrobr",
            module_depth=2,
            layers={
                "core": LayerConfig(modules=["_core"]),
                "data": LayerConfig(modules=["cepea", "conab"]),
            },
        )
        file_data = {
            "__init__.py": 5,
            "_core/__init__.py": 10,
            "_core/base.py": 80,
            "cepea/__init__.py": 5,
            "cepea/parsers.py": 120,
            "conab/__init__.py": 5,
            "conab/fetcher.py": 90,
        }
        radon = [
            RawRadonResult(path="src/agrobr/__init__.py", mi=100.0, rank="A"),
            RawRadonResult(
                path="src/agrobr/_core/base.py",
                mi=65.0,
                rank="A",
                functions=[
                    RawFunctionCC("validate", 4, False, "", 1),
                    RawFunctionCC("transform", 6, False, "", 20),
                ],
            ),
            RawRadonResult(
                path="src/agrobr/cepea/parsers.py",
                mi=45.0,
                rank="B",
                functions=[
                    RawFunctionCC("parse", 8, False, "", 1),
                    RawFunctionCC("clean", 2, False, "", 30),
                ],
            ),
            RawRadonResult(
                path="src/agrobr/conab/fetcher.py",
                mi=55.0,
                rank="B",
                functions=[RawFunctionCC("fetch", 3, False, "", 1)],
            ),
        ]
        vulture = [
            RawVultureResult("src/agrobr/_core/base.py", 50, "function", "old_validate", 60),
            RawVultureResult("src/agrobr/cepea/parsers.py", 100, "variable", "tmp", 80),
            RawVultureResult("src/agrobr/cepea/parsers.py", 110, "function", "legacy", 60),
        ]
        churn = [
            RawChurnResult("src/agrobr/cepea/parsers.py", 12),
            RawChurnResult("src/agrobr/conab/fetcher.py", 3),
            RawChurnResult("src/agrobr/_core/base.py", 7),
        ]
        imports = [
            RawImportEdge("cepea.parsers", "agrobr._core.base"),
            RawImportEdge("conab.fetcher", "agrobr._core.base"),
            RawImportEdge("cepea.parsers", "agrobr.conab.fetcher"),
        ]

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/agrobr",
                imports=imports,
                radon=radon,
                vulture=vulture,
                churn=churn,
            )

        by_name = {m.name: m for m in result.modules}
        assert len(result.modules) == 4

        # agrobr root
        assert by_name["agrobr"].lines == 5
        assert by_name["agrobr"].mi == 100.0
        assert by_name["agrobr"].cc == 0.0

        # agrobr._core
        core = by_name["agrobr._core"]
        assert core.lines == 90
        assert core.mi == 65.0
        assert core.cc == 5.0
        assert core.funcs == 2
        assert core.dead == 1
        assert core.churn == 7

        # agrobr.cepea
        cepea = by_name["agrobr.cepea"]
        assert cepea.lines == 125
        assert cepea.mi == 45.0
        assert cepea.cc == 5.0
        assert cepea.funcs == 2
        assert cepea.dead == 2
        assert cepea.churn == 12

        # agrobr.conab
        conab = by_name["agrobr.conab"]
        assert conab.lines == 95
        assert conab.mi == 55.0
        assert conab.cc == 3.0
        assert conab.funcs == 1
        assert conab.churn == 3

        # Dependencies
        assert len(result.dependencies) == 3
        dep_edges = {(d.from_module, d.to_module) for d in result.dependencies}
        assert ("agrobr.cepea", "agrobr._core") in dep_edges
        assert ("agrobr.conab", "agrobr._core") in dep_edges
        assert ("agrobr.cepea", "agrobr.conab") in dep_edges


# ---------------------------------------------------------------------------
# Modules not in any collector
# ---------------------------------------------------------------------------


class TestModulesNotInCollectors:
    def test_file_exists_no_collector_data(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {"sub/orphan.py": 42}

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=[],
                radon=[],
                vulture=[],
                churn=[],
            )

        mod = result.modules[0]
        assert mod.name == "mypkg.sub"
        assert mod.lines == 42
        assert mod.mi == 100.0
        assert mod.cc == 0.0
        assert mod.funcs == 0
        assert mod.dead == 0
        assert mod.churn == 0


# ---------------------------------------------------------------------------
# Sorted output
# ---------------------------------------------------------------------------


class TestModulesSortedAlphabetically:
    def test_output_sorted(self):
        cfg = Config(source="src/mypkg", module_depth=2)
        file_data = {
            "zebra/z.py": 10,
            "alpha/a.py": 10,
            "mid/m.py": 10,
        }

        with _mock_files(file_data):
            result = aggregate(
                cfg=cfg,
                source_path="/project/src/mypkg",
                imports=[],
                radon=[],
                vulture=[],
                churn=[],
            )

        names = [m.name for m in result.modules]
        assert names == ["mypkg.alpha", "mypkg.mid", "mypkg.zebra"]


# ---------------------------------------------------------------------------
# Vulture exclude_types filtering
# ---------------------------------------------------------------------------


class TestVultureExcludeTypes:
    def test_exclude_attribute_type(self):
        results = [
            RawVultureResult("src/mypkg/sub/a.py", 10, "attribute", "field_x", 60),
            RawVultureResult("src/mypkg/sub/a.py", 20, "function", "old_func", 80),
            RawVultureResult("src/mypkg/sub/a.py", 30, "variable", "tmp", 70),
        ]
        counts = _process_vulture(
            results,
            "src/mypkg/",
            "mypkg",
            2,
            exclude_types=frozenset(["attribute"]),
        )
        assert counts == {"mypkg.sub": 2}

    def test_exclude_multiple_types(self):
        results = [
            RawVultureResult("src/mypkg/sub/a.py", 10, "attribute", "field_x", 60),
            RawVultureResult("src/mypkg/sub/a.py", 20, "function", "old_func", 80),
            RawVultureResult("src/mypkg/sub/a.py", 30, "variable", "tmp", 70),
        ]
        counts = _process_vulture(
            results,
            "src/mypkg/",
            "mypkg",
            2,
            exclude_types=frozenset(["attribute", "variable"]),
        )
        assert counts == {"mypkg.sub": 1}

    def test_no_exclusion_counts_all(self):
        results = [
            RawVultureResult("src/mypkg/sub/a.py", 10, "attribute", "field_x", 60),
            RawVultureResult("src/mypkg/sub/a.py", 20, "function", "old_func", 80),
        ]
        counts = _process_vulture(
            results,
            "src/mypkg/",
            "mypkg",
            2,
            exclude_types=frozenset(),
        )
        assert counts == {"mypkg.sub": 2}
