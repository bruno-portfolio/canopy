from __future__ import annotations

import dataclasses
from collections import defaultdict

from canopy.models import Dependency, Module, ProjectData


def _collapsed_name(layer: str) -> str:
    return f"_collapsed_{layer}"


def _make_collapsed(layer_name: str, modules: list[Module]) -> Module:
    total_lines = 0
    total_funcs = 0
    mi_weighted_sum = 0.0
    max_cc = 0.0
    total_dead = 0
    total_churn = 0
    for m in modules:
        total_lines += m.lines
        total_funcs += m.funcs
        mi_weighted_sum += m.mi * m.lines
        max_cc = max(max_cc, m.cc)
        total_dead += m.dead
        total_churn += m.churn
    mi = mi_weighted_sum / total_lines if total_lines > 0 else 0.0
    return Module(
        name=_collapsed_name(layer_name),
        lines=total_lines,
        funcs=total_funcs,
        mi=mi,
        cc=max_cc,
        dead=total_dead,
        churn=total_churn,
        layer=layer_name,
        desc=f"+{len(modules)} more",
    )


def _remap_deps(
    deps: list[Dependency],
    collapsed_names: set[str],
    name_to_layer: dict[str, str],
) -> list[Dependency]:
    merged: dict[tuple[str, str], float] = {}
    for dep in deps:
        from_mod = dep.from_module
        to_mod = dep.to_module
        if from_mod in collapsed_names:
            from_mod = _collapsed_name(name_to_layer[from_mod])
        if to_mod in collapsed_names:
            to_mod = _collapsed_name(name_to_layer[to_mod])
        if from_mod == to_mod:
            continue
        key = (from_mod, to_mod)
        merged[key] = merged.get(key, 0.0) + dep.weight
    return [Dependency(f, t, w) for (f, t), w in merged.items()]


def collapse_small(project_data: ProjectData, min_loc: int) -> ProjectData:
    if not project_data.modules:
        return project_data

    by_layer: dict[str, list[Module]] = defaultdict(list)
    for m in project_data.modules:
        by_layer[m.layer].append(m)

    result_modules: list[Module] = []
    collapsed_names: set[str] = set()
    name_to_layer: dict[str, str] = {}

    for layer_name, mods in by_layer.items():
        big = [m for m in mods if m.lines >= min_loc]
        small = [m for m in mods if m.lines < min_loc]
        if len(small) < 2:
            result_modules.extend(mods)
        else:
            result_modules.extend(big)
            result_modules.append(_make_collapsed(layer_name, small))
            for m in small:
                collapsed_names.add(m.name)
                name_to_layer[m.name] = layer_name

    new_deps = _remap_deps(project_data.dependencies, collapsed_names, name_to_layer)

    return dataclasses.replace(
        project_data,
        modules=result_modules,
        dependencies=new_deps,
    )


def collapse_overflow(modules: list[Module], max_count: int) -> list[Module]:
    if len(modules) <= max_count:
        return list(modules)

    sorted_mods = sorted(modules, key=lambda m: m.lines, reverse=True)
    keep = sorted_mods[: max_count - 1]
    rest = sorted_mods[max_count - 1 :]

    layer_name = rest[0].layer if rest else ""
    collapsed = _make_collapsed(layer_name, rest)
    return [*keep, collapsed]
