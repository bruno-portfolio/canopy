from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from canopy.collectors import RawVultureResult
from canopy.collectors.vulture import collect_vulture
from canopy.exceptions import CollectorError
from tests.conftest import make_proc


class TestHappyPath:
    @patch("canopy.collectors.vulture.subprocess.run")
    def test_happy_path_exit_3(self, mock_run):
        output = (
            "src/app.py:10: unused function 'old_handler' (60% confidence)\n"
            "src/utils.py:25: unused variable 'temp' (80% confidence)\n"
        )
        mock_run.return_value = make_proc(returncode=3, stdout=output)

        results = collect_vulture("src")

        assert len(results) == 2
        assert results[0] == RawVultureResult(
            path="src/app.py",
            lineno=10,
            kind="function",
            name="old_handler",
            confidence=60,
        )
        assert results[1] == RawVultureResult(
            path="src/utils.py",
            lineno=25,
            kind="variable",
            name="temp",
            confidence=80,
        )

    @patch("canopy.collectors.vulture.subprocess.run")
    def test_no_dead_code_exit_0(self, mock_run):
        mock_run.return_value = make_proc(returncode=0)

        results = collect_vulture("src")

        assert results == []


class TestErrorHandling:
    @patch("canopy.collectors.vulture.subprocess.run")
    def test_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError

        with pytest.raises(CollectorError, match="vulture not found"):
            collect_vulture("src")

    @patch("canopy.collectors.vulture.subprocess.run")
    def test_error_exit_1(self, mock_run):
        mock_run.return_value = make_proc(returncode=1, stderr="crash")

        with pytest.raises(CollectorError, match="vulture failed"):
            collect_vulture("src")

    @patch("canopy.collectors.vulture.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("vulture", 60)

        with pytest.raises(CollectorError, match="timed out"):
            collect_vulture("src")


class TestParsing:
    @patch("canopy.collectors.vulture.subprocess.run")
    def test_confidence_filtering(self, mock_run):
        output = "src/app.py:1: unused function 'f' (90% confidence)\n"
        mock_run.return_value = make_proc(returncode=3, stdout=output)

        results = collect_vulture("src", min_confidence=80)

        assert len(results) == 1
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "--min-confidence=80" in args

    @patch("canopy.collectors.vulture.subprocess.run")
    def test_all_types_parsed(self, mock_run):
        lines = [
            "a.py:1: unused function 'f' (60% confidence)",
            "a.py:2: unused method 'm' (60% confidence)",
            "a.py:3: unused variable 'v' (60% confidence)",
            "a.py:4: unused import 'i' (60% confidence)",
            "a.py:5: unused class 'C' (60% confidence)",
            "a.py:6: unused property 'p' (60% confidence)",
            "a.py:7: unused attribute 'a' (60% confidence)",
        ]
        mock_run.return_value = make_proc(returncode=3, stdout="\n".join(lines))

        results = collect_vulture("src")

        kinds = [r.kind for r in results]
        assert kinds == [
            "function",
            "method",
            "variable",
            "import",
            "class",
            "property",
            "attribute",
        ]

    @patch("canopy.collectors.vulture.subprocess.run")
    def test_unparseable_line_skipped(self, mock_run):
        output = (
            "some garbage line\n"
            "src/app.py:10: unused function 'f' (60% confidence)\n"
            "another garbage\n"
        )
        mock_run.return_value = make_proc(returncode=3, stdout=output)

        results = collect_vulture("src")

        assert len(results) == 1
        assert results[0].name == "f"
