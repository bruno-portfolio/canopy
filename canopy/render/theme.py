from __future__ import annotations

from dataclasses import dataclass

from canopy.config import Config


@dataclass(frozen=True)
class HealthColors:
    base: str
    dark: str
    light: str
    glow: str


@dataclass(frozen=True)
class Theme:
    # Canvas
    width: int = 1000
    height: int = 800

    # Background gradient stops
    bg_inner: str = "#111820"
    bg_mid: str = "#0a0e14"
    bg_outer: str = "#06080c"

    # Health palettes
    healthy: HealthColors = HealthColors(
        base="#2ea043", dark="#1a7f37", light="#56d364", glow="#2ea04355"
    )
    moderate: HealthColors = HealthColors(
        base="#d29922", dark="#9e6a03", light="#e3b341", glow="#d2992255"
    )
    complex: HealthColors = HealthColors(
        base="#da3633", dark="#b62324", light="#f85149", glow="#da363355"
    )

    # Thresholds
    mi_healthy: int = 40
    mi_moderate: int = 20
    churn_high: int = 20

    # Ring
    ring_default: str = "#30363d"
    ring_infra: str = "#bc8cff"

    # Dependencies
    dep_core_infra: str = "#bc8cff"
    dep_light: str = "#21262d"
    dep_significant: str = "#58a6ff"

    # Churn
    churn_stroke: str = "#bc8cff"

    # Dead code
    dead_fill: str = "#1b1f23"
    dead_opacity: float = 0.7

    # Stars
    star_fill: str = "#c9d1d9"
    star_count: int = 60
    star_min_r: float = 0.3
    star_max_r: float = 1.2
    star_min_opacity: float = 0.1
    star_max_opacity: float = 0.5

    # Text
    text_primary: str = "#c9d1d9"
    text_secondary: str = "#8b949e"
    text_muted: str = "#484f58"
    text_very_muted: str = "#30363d"

    # Watermark
    watermark_fill: str = "#161b22"

    # Node glow
    ambient_opacity: float = 0.08
    ambient_opacity_core: float = 0.15

    # Core decoration
    core_ring_stroke: str = "#da3633"
    core_ring_radius: float = 50.0


def health_colors(theme: Theme, mi: float) -> HealthColors:
    if mi >= theme.mi_healthy:
        return theme.healthy
    if mi >= theme.mi_moderate:
        return theme.moderate
    return theme.complex


def default_theme() -> Theme:
    return Theme()


def theme_from_config(cfg: Config) -> Theme:
    return Theme(
        width=cfg.output.width,
        height=cfg.output.height,
        mi_healthy=cfg.thresholds.mi_healthy,
        mi_moderate=cfg.thresholds.mi_moderate,
        churn_high=cfg.thresholds.churn_high,
    )
