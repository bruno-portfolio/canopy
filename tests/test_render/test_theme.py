from __future__ import annotations

import pytest

from canopy.config import Config, OutputConfig, ThresholdsConfig
from canopy.render.theme import (
    HealthColors,
    Theme,
    default_theme,
    health_colors,
    theme_from_config,
)


class TestThemeDefaults:
    def test_default_dimensions(self):
        t = Theme()
        assert t.width == 1000
        assert t.height == 800

    def test_default_bg_colors(self):
        t = Theme()
        assert t.bg_inner == "#111820"
        assert t.bg_mid == "#0a0e14"
        assert t.bg_outer == "#06080c"

    def test_default_thresholds(self):
        t = Theme()
        assert t.mi_healthy == 40
        assert t.mi_moderate == 20
        assert t.churn_high == 20

    def test_default_star_count(self):
        t = Theme()
        assert t.star_count == 60

    def test_default_core_ring(self):
        t = Theme()
        assert t.core_ring_stroke == "#da3633"
        assert t.core_ring_radius == 50.0


class TestHealthColors:
    def test_healthy_above_threshold(self):
        t = Theme()
        hc = health_colors(t, 50.0)
        assert hc is t.healthy

    def test_healthy_at_boundary(self):
        t = Theme()
        hc = health_colors(t, 40.0)
        assert hc is t.healthy

    def test_moderate_range(self):
        t = Theme()
        hc = health_colors(t, 30.0)
        assert hc is t.moderate

    def test_moderate_at_boundary(self):
        t = Theme()
        hc = health_colors(t, 20.0)
        assert hc is t.moderate

    def test_complex_below_moderate(self):
        t = Theme()
        hc = health_colors(t, 10.0)
        assert hc is t.complex

    def test_complex_zero(self):
        t = Theme()
        hc = health_colors(t, 0.0)
        assert hc is t.complex

    def test_custom_thresholds(self):
        t = Theme(mi_healthy=80, mi_moderate=50)
        assert health_colors(t, 90.0) is t.healthy
        assert health_colors(t, 60.0) is t.moderate
        assert health_colors(t, 30.0) is t.complex


class TestThemeFromConfig:
    def test_copies_dimensions(self):
        cfg = Config(output=OutputConfig(width=1200, height=900))
        t = theme_from_config(cfg)
        assert t.width == 1200
        assert t.height == 900

    def test_copies_thresholds(self):
        cfg = Config(thresholds=ThresholdsConfig(mi_healthy=60, mi_moderate=30, churn_high=15))
        t = theme_from_config(cfg)
        assert t.mi_healthy == 60
        assert t.mi_moderate == 30
        assert t.churn_high == 15

    def test_preserves_default_colors(self):
        cfg = Config()
        t = theme_from_config(cfg)
        assert t.healthy == Theme().healthy
        assert t.bg_inner == Theme().bg_inner

    def test_default_theme_function(self):
        t = default_theme()
        assert t == Theme()


class TestHealthColorsImmutability:
    def test_frozen_theme(self):
        t = Theme()
        with pytest.raises(AttributeError):
            t.width = 500  # type: ignore[misc]

    def test_frozen_health_colors(self):
        hc = HealthColors(base="#fff", dark="#000", light="#ccc", glow="#aaa")
        with pytest.raises(AttributeError):
            hc.base = "#000"  # type: ignore[misc]
