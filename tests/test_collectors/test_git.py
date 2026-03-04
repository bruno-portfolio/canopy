from __future__ import annotations

import subprocess
import warnings
from unittest.mock import patch

from canopy.collectors import RawChurnResult
from canopy.collectors.git import collect_churn
from tests.conftest import make_proc


class TestHappyPath:
    @patch("canopy.collectors.git.subprocess.run")
    def test_happy_path(self, mock_run):
        mock_run.side_effect = [
            make_proc(stdout=".git\n"),
            make_proc(stdout="false\n"),
            make_proc(stdout="src/app.py\nsrc/utils.py\nsrc/app.py\n"),
        ]

        results = collect_churn("/project")

        assert len(results) == 2
        result_dict = {r.path: r.commit_count for r in results}
        assert result_dict["src/app.py"] == 2
        assert result_dict["src/utils.py"] == 1


class TestShallowClone:
    @patch("canopy.collectors.git.subprocess.run")
    def test_shallow_clone(self, mock_run):
        mock_run.side_effect = [
            make_proc(stdout=".git\n"),
            make_proc(stdout="true\n"),
        ]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            results = collect_churn("/project")

        assert results == []
        assert len(w) == 1
        assert "Shallow clone" in str(w[0].message)


class TestGitUnavailable:
    @patch("canopy.collectors.git.subprocess.run")
    def test_git_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            results = collect_churn("/project")

        assert results == []
        assert len(w) == 1
        assert "git not available" in str(w[0].message)

    @patch("canopy.collectors.git.subprocess.run")
    def test_not_a_repo(self, mock_run):
        mock_run.return_value = make_proc(returncode=128, stderr="fatal")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            results = collect_churn("/project")

        assert results == []
        assert len(w) == 1
        assert "not a git repository" in str(w[0].message)

    @patch("canopy.collectors.git.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("git", 60)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            results = collect_churn("/project")

        assert results == []
        assert len(w) == 1
        assert "git not available" in str(w[0].message)


class TestParsing:
    @patch("canopy.collectors.git.subprocess.run")
    def test_empty_log(self, mock_run):
        mock_run.side_effect = [
            make_proc(stdout=".git\n"),
            make_proc(stdout="false\n"),
            make_proc(stdout=""),
        ]

        results = collect_churn("/project")

        assert results == []

    @patch("canopy.collectors.git.subprocess.run")
    def test_blank_lines_filtered(self, mock_run):
        mock_run.side_effect = [
            make_proc(stdout=".git\n"),
            make_proc(stdout="false\n"),
            make_proc(stdout="\napp.py\n\nutils.py\n\n"),
        ]

        results = collect_churn("/project")

        assert len(results) == 2

    @patch("canopy.collectors.git.subprocess.run")
    def test_multiple_commits_same_file(self, mock_run):
        lines = "app.py\n" * 5
        mock_run.side_effect = [
            make_proc(stdout=".git\n"),
            make_proc(stdout="false\n"),
            make_proc(stdout=lines),
        ]

        results = collect_churn("/project")

        assert len(results) == 1
        assert results[0] == RawChurnResult(path="app.py", commit_count=5)
