from __future__ import annotations

import dataclasses
from pathlib import Path

import click

from canopy import __version__, exceptions
from canopy.aggregator import aggregate
from canopy.collectors.git import collect_churn
from canopy.collectors.imports import collect_imports
from canopy.collectors.radon import collect_radon
from canopy.collectors.vulture import collect_vulture
from canopy.config import load_config, resolve_project_name, validate_config
from canopy.layout import assign_layers, collapse_small, compute_layout
from canopy.render import render_svg
from canopy.render.theme import theme_from_config


def _build_config(project_dir, config_path, output_override):
    cfg = load_config(config_path, project_dir=project_dir)
    validate_config(cfg, project_dir)
    if output_override:
        cfg = dataclasses.replace(
            cfg,
            output=dataclasses.replace(cfg.output, path=output_override),
        )
    return cfg


def _run_collectors(source_path, project_dir, cfg):
    radon = collect_radon(source_path)
    vulture = collect_vulture(source_path, min_confidence=cfg.vulture.min_confidence)
    churn = collect_churn(project_dir, days=cfg.git.churn_days)
    imports = collect_imports(source_path)
    return radon, vulture, churn, imports


def _run_pipeline(cfg, source_path, project_dir, radon, vulture, churn, imports):
    project_data = aggregate(
        cfg=cfg,
        source_path=source_path,
        imports=imports,
        radon=radon,
        vulture=vulture,
        churn=churn,
    )
    project_name = resolve_project_name(cfg, project_dir)
    project_data = dataclasses.replace(project_data, project_name=project_name)
    project_data = assign_layers(project_data, cfg)
    project_data = collapse_small(project_data, cfg.thresholds.min_loc)
    layout = compute_layout(project_data, cfg)
    return project_data, layout


def _write_output(cfg, project_data, layout):
    theme = theme_from_config(cfg)
    svg = render_svg(project_data, layout, theme)
    out = Path(cfg.output.path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    n_modules = len(project_data.modules)
    total_lines = sum(m.lines for m in project_data.modules)
    click.echo(f"{out} written ({n_modules} modules, {total_lines} lines)")


@click.group()
@click.version_option(version=__version__, prog_name="canopy")
def main():
    """Canopy — orbital SVG visualizations of codebase health."""


@main.command()
@click.argument("path", default=".")
@click.option("--config", "config_path", default=None, help="Path to canopy.yml")
@click.option("--output", "output_override", default=None, help="Override output path")
def run(path, config_path, output_override):
    """Analyse a project and generate an SVG diagram."""
    try:
        project_dir = str(Path(path).resolve())
        cfg = _build_config(project_dir, config_path, output_override)
        source_path = str(Path(project_dir) / cfg.source)
        radon, vulture, churn, imports = _run_collectors(source_path, project_dir, cfg)
        project_data, layout = _run_pipeline(
            cfg,
            source_path,
            project_dir,
            radon,
            vulture,
            churn,
            imports,
        )
        _write_output(cfg, project_data, layout)
    except exceptions.ConfigError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc
    except exceptions.CollectorError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(2) from exc
    except exceptions.CanopyError as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from exc
