from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from canopy import config, models
from canopy.collectors import (
    RawChurnResult,
    RawImportEdge,
    RawRadonResult,
    RawVultureResult,
    normalize_path,
)

_MI_DEFAULT = 100.0
_CC_DEFAULT = 0.0


@dataclass
class _RadonAccum:
    mi_weighted_sum: float = 0.0
    mi_weight_total: int = 0
    func_complexities: list[int] = field(default_factory=list)


def _source_prefix(cfg: config.Config) -> str:
    source = normalize_path(cfg.source)
    if source == ".":
        return ""
    return source.rstrip("/") + "/"


def _root_package(source_path: str) -> str:
    return Path(source_path).name


def _truncate(module_name: str, depth: int) -> str:
    parts = module_name.split(".")
    return ".".join(parts[:depth])


def _strip_source_prefix(path: str, source_prefix: str, source_path: str = "") -> str:
    normalized = normalize_path(path)
    # Handle absolute paths from collectors by making them relative to source_path
    if source_path:
        norm_source = normalize_path(source_path).rstrip("/") + "/"
        if normalized.startswith(norm_source):
            return normalized[len(norm_source) :]
    if source_prefix and normalized.startswith(source_prefix):
        return normalized[len(source_prefix) :]
    return normalized


def _relative_path_to_module(
    relative_path: str,
    root_package: str,
    depth: int,
) -> str:
    path = normalize_path(relative_path)
    if path.endswith(".py"):
        path = path[:-3]
    if path.endswith("/__init__") or path == "__init__":
        path = path.rsplit("/__init__", 1)[0] if "/__init__" in path else ""
    module = root_package + "." + path.replace("/", ".") if path else root_package
    return _truncate(module, depth)


def _path_to_module(
    path: str,
    source_prefix: str,
    root_package: str,
    depth: int,
    source_path: str = "",
) -> str:
    stripped = _strip_source_prefix(path, source_prefix, source_path)
    return _relative_path_to_module(stripped, root_package, depth)


def _discover_files(source_path: str) -> dict[str, int]:
    result: dict[str, int] = {}
    root = Path(source_path)
    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        relative = normalize_path(str(py_file.relative_to(root)))
        try:
            line_count = len(py_file.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeDecodeError):
            line_count = 0
        result[relative] = line_count
    return result


def _process_radon(
    radon_results: list[RawRadonResult],
    file_lines: dict[str, int],
    source_prefix: str,
    root_package: str,
    depth: int,
    source_path: str = "",
) -> dict[str, _RadonAccum]:
    accum: dict[str, _RadonAccum] = {}
    for result in radon_results:
        relative = _strip_source_prefix(result.path, source_prefix, source_path)
        module = _relative_path_to_module(relative, root_package, depth)
        lines = file_lines.get(relative, 0)

        if module not in accum:
            accum[module] = _RadonAccum()
        acc = accum[module]
        acc.mi_weighted_sum += result.mi * lines
        acc.mi_weight_total += lines

        func_max: dict[str, int] = {}
        for func in result.functions:
            key = f"{func.classname}.{func.name}" if func.classname else func.name
            func_max[key] = max(func_max.get(key, 0), func.complexity)

        acc.func_complexities.extend(func_max.values())

    return accum


def _process_vulture(
    vulture_results: list[RawVultureResult],
    source_prefix: str,
    root_package: str,
    depth: int,
    source_path: str = "",
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in vulture_results:
        module = _path_to_module(result.path, source_prefix, root_package, depth, source_path)
        counts[module] = counts.get(module, 0) + 1
    return counts


def _process_churn(
    churn_results: list[RawChurnResult],
    source_prefix: str,
    root_package: str,
    depth: int,
    source_path: str = "",
) -> dict[str, int]:
    totals: dict[str, int] = {}
    for result in churn_results:
        module = _path_to_module(result.path, source_prefix, root_package, depth, source_path)
        totals[module] = totals.get(module, 0) + result.commit_count
    return totals


def _process_imports(
    imports: list[RawImportEdge],
    root_package: str,
    depth: int,
) -> list[models.Dependency]:
    edge_counts: dict[tuple[str, str], int] = {}
    for edge in imports:
        if edge.source_module:
            source = _truncate(root_package + "." + edge.source_module, depth)
        else:
            source = _truncate(root_package, depth)
        target = _truncate(edge.target_module, depth)

        if source == target:
            continue

        key = (source, target)
        edge_counts[key] = edge_counts.get(key, 0) + 1

    return [
        models.Dependency(from_module=src, to_module=tgt, weight=float(count))
        for (src, tgt), count in sorted(edge_counts.items())
    ]


def aggregate(
    *,
    cfg: config.Config,
    source_path: str,
    imports: list[RawImportEdge],
    radon: list[RawRadonResult],
    vulture: list[RawVultureResult],
    churn: list[RawChurnResult],
) -> models.ProjectData:
    prefix = _source_prefix(cfg)
    root = _root_package(source_path)
    depth = cfg.module_depth

    file_data = _discover_files(source_path)

    module_lines: dict[str, int] = {}
    for rel_path, lines in file_data.items():
        module = _relative_path_to_module(rel_path, root, depth)
        module_lines[module] = module_lines.get(module, 0) + lines

    radon_data = _process_radon(radon, file_data, prefix, root, depth, source_path)
    vulture_data = _process_vulture(vulture, prefix, root, depth, source_path)
    churn_data = _process_churn(churn, prefix, root, depth, source_path)
    deps = _process_imports(imports, root, depth)

    all_modules = set(module_lines.keys())

    modules: list[models.Module] = []
    for name in sorted(all_modules):
        lines = module_lines.get(name, 0)

        radon_acc = radon_data.get(name)
        if radon_acc and radon_acc.mi_weight_total > 0:
            mi = radon_acc.mi_weighted_sum / radon_acc.mi_weight_total
        else:
            mi = _MI_DEFAULT

        if radon_acc and radon_acc.func_complexities:
            cc = sum(radon_acc.func_complexities) / len(radon_acc.func_complexities)
        else:
            cc = _CC_DEFAULT

        funcs = len(radon_acc.func_complexities) if radon_acc else 0

        modules.append(
            models.Module(
                name=name,
                lines=lines,
                funcs=funcs,
                mi=round(mi, 2),
                cc=round(cc, 2),
                dead=vulture_data.get(name, 0),
                churn=churn_data.get(name, 0),
            )
        )

    return models.ProjectData(modules=modules, dependencies=deps)
