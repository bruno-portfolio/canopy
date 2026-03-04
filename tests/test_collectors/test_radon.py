from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from canopy.collectors.radon import collect_radon
from canopy.exceptions import CollectorError


def _make_proc(returncode: int = 0, stdout: str = "{}", stderr: str = "") -> MagicMock:
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestHappyPath:
    @patch("canopy.collectors.radon.subprocess.run")
    def test_happy_path(self, mock_run):
        mi_data = {"src/app.py": {"mi": 65.0, "rank": "A"}}
        cc_data = {
            "src/app.py": [
                {
                    "type": "function",
                    "name": "main",
                    "complexity": 3,
                    "classname": "",
                    "lineno": 10,
                }
            ]
        }
        mock_run.side_effect = [
            _make_proc(stdout=json.dumps(mi_data)),
            _make_proc(stdout=json.dumps(cc_data)),
        ]

        results = collect_radon("src")

        assert len(results) == 1
        assert results[0].path == "src/app.py"
        assert results[0].mi == 65.0
        assert results[0].rank == "A"
        assert len(results[0].functions) == 1
        assert results[0].functions[0].name == "main"
        assert results[0].functions[0].complexity == 3

    @patch("canopy.collectors.radon.subprocess.run")
    def test_empty_project(self, mock_run):
        mock_run.side_effect = [
            _make_proc(stdout="{}"),
            _make_proc(stdout="{}"),
        ]

        results = collect_radon("src")

        assert results == []


class TestErrorHandling:
    @patch("canopy.collectors.radon.subprocess.run")
    def test_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError

        with pytest.raises(CollectorError, match="radon not found"):
            collect_radon("src")

    @patch("canopy.collectors.radon.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("radon", 60)

        with pytest.raises(CollectorError, match="timed out"):
            collect_radon("src")

    @patch("canopy.collectors.radon.subprocess.run")
    def test_nonzero_exit(self, mock_run):
        mock_run.return_value = _make_proc(returncode=1, stderr="error msg")

        with pytest.raises(CollectorError, match="radon failed"):
            collect_radon("src")


class TestPathNormalization:
    @patch("canopy.collectors.radon.subprocess.run")
    def test_windows_paths(self, mock_run):
        mi_data = {"src\\app.py": {"mi": 50.0, "rank": "B"}}
        cc_data = {"src\\app.py": []}
        mock_run.side_effect = [
            _make_proc(stdout=json.dumps(mi_data)),
            _make_proc(stdout=json.dumps(cc_data)),
        ]

        results = collect_radon("src")

        assert results[0].path == "src/app.py"


class TestFunctions:
    @patch("canopy.collectors.radon.subprocess.run")
    def test_no_functions(self, mock_run):
        mi_data = {"src/constants.py": {"mi": 100.0, "rank": "A"}}
        cc_data: dict[str, list[str]] = {}
        mock_run.side_effect = [
            _make_proc(stdout=json.dumps(mi_data)),
            _make_proc(stdout=json.dumps(cc_data)),
        ]

        results = collect_radon("src")

        assert results[0].functions == []

    @patch("canopy.collectors.radon.subprocess.run")
    def test_multiple_functions(self, mock_run):
        mi_data = {"src/utils.py": {"mi": 45.0, "rank": "A"}}
        cc_data = {
            "src/utils.py": [
                {"type": "function", "name": "a", "complexity": 1, "classname": "", "lineno": 1},
                {"type": "method", "name": "b", "complexity": 5, "classname": "Foo", "lineno": 10},
                {"type": "function", "name": "c", "complexity": 2, "classname": "", "lineno": 20},
            ]
        }
        mock_run.side_effect = [
            _make_proc(stdout=json.dumps(mi_data)),
            _make_proc(stdout=json.dumps(cc_data)),
        ]

        results = collect_radon("src")

        assert len(results[0].functions) == 3
        assert results[0].functions[1].is_method is True
        assert results[0].functions[1].classname == "Foo"
