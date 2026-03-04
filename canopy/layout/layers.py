from __future__ import annotations

import dataclasses

from canopy import config, models

_UNCATEGORIZED = "uncategorized"


def _match_layer(module_name: str, cfg: config.Config) -> str:
    parts = module_name.split(".")[1:]
    for layer_name, layer_config in cfg.layers.items():
        for suffix in layer_config.modules:
            if suffix in parts:
                return layer_name
    return _UNCATEGORIZED


def _default_label(name: str) -> str:
    return name.replace("_", " ").strip().title()


def _build_layer_list(
    cfg: config.Config,
    has_uncategorized: bool,
) -> list[models.Layer]:
    layers: list[models.Layer] = []
    for ring, (name, layer_config) in enumerate(cfg.layers.items()):
        label = layer_config.label or _default_label(name)
        layers.append(models.Layer(name=name, ring=ring, label=label))
    if has_uncategorized:
        layers.append(
            models.Layer(
                name=_UNCATEGORIZED,
                ring=len(cfg.layers),
                label=_default_label(_UNCATEGORIZED),
            )
        )
    return layers


def assign_layers(
    project_data: models.ProjectData,
    cfg: config.Config,
) -> models.ProjectData:
    if not project_data.modules:
        return dataclasses.replace(project_data, layers=[])

    has_uncategorized = False
    updated_modules: list[models.Module] = []
    for module in project_data.modules:
        layer = _match_layer(module.name, cfg)
        if layer == _UNCATEGORIZED:
            has_uncategorized = True
        updated_modules.append(dataclasses.replace(module, layer=layer))

    layers = _build_layer_list(cfg, has_uncategorized)

    return dataclasses.replace(
        project_data,
        modules=updated_modules,
        layers=layers,
    )
