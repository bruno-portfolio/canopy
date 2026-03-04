from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from canopy.config import (
    Config,
    GitConfig,
    LayerConfig,
    OutputConfig,
    ThresholdsConfig,
    VultureConfig,
)
from canopy.models import Module


def make_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


@pytest.fixture
def sample_module() -> Module:
    return Module(
        name="agrobr.cepea",
        lines=270,
        funcs=5,
        mi=41.35,
        cc=3.3,
        dead=1,
        churn=9,
        layer="market",
        desc="Price indicators",
    )


@pytest.fixture
def sample_config() -> Config:
    return Config(
        project="agrobr",
        source="src/agrobr",
        module_depth=2,
        layers={
            "core": LayerConfig(modules=["_core"]),
            "infra": LayerConfig(
                modules=["_cache", "_validation"],
                label="Infrastructure",
            ),
        },
        vulture=VultureConfig(min_confidence=60, exclude_types=["attribute"]),
        git=GitConfig(churn_days=30),
        thresholds=ThresholdsConfig(
            mi_healthy=40,
            mi_moderate=20,
            churn_high=20,
            min_loc=50,
        ),
        output=OutputConfig(path="docs/canopy.svg", width=1000, height=800),
        ignore=["tests/**"],
    )


@pytest.fixture
def tmp_config_file(tmp_path):
    def _factory(content: str, filename: str = "canopy.yml") -> str:
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        return str(path)

    return _factory
