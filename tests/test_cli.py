from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from canopy.cli import main
from canopy.exceptions import CanopyError, CollectorError, ConfigError
from tests.conftest import make_proc

_PATCH_SUBPROCESS = "subprocess.run"
_PATCH_DISCOVER = "canopy.aggregator._discover_files"


# ---------------------------------------------------------------------------
# Unit tests — mock internal helpers to test CLI wiring, exit codes, messages
# ---------------------------------------------------------------------------


class TestRunSuccess:
    @patch("canopy.cli._write_output")
    @patch("canopy.cli._run_pipeline")
    @patch("canopy.cli._run_collectors")
    @patch("canopy.cli._build_config")
    def test_run_exit_zero(self, mock_build, mock_collectors, mock_pipeline, mock_write):
        mock_build.return_value = MagicMock(source=".", output=MagicMock(path="out.svg"))
        mock_collectors.return_value = ([], [], [], [])
        mock_pipeline.return_value = (MagicMock(modules=[]), MagicMock())

        runner = CliRunner()
        result = runner.invoke(main, ["run", "."])

        assert result.exit_code == 0

    @patch("canopy.cli._write_output")
    @patch("canopy.cli._run_pipeline")
    @patch("canopy.cli._run_collectors")
    @patch("canopy.cli._build_config")
    def test_run_default_path(self, mock_build, mock_collectors, mock_pipeline, mock_write):
        mock_build.return_value = MagicMock(source=".", output=MagicMock(path="out.svg"))
        mock_collectors.return_value = ([], [], [], [])
        mock_pipeline.return_value = (MagicMock(modules=[]), MagicMock())

        runner = CliRunner()
        result = runner.invoke(main, ["run"])

        assert result.exit_code == 0
        mock_build.assert_called_once()


class TestRunErrors:
    @patch("canopy.cli._build_config", side_effect=ConfigError("bad config"))
    def test_config_error_exit_1(self, _mock):
        runner = CliRunner()
        result = runner.invoke(main, ["run", "."])

        assert result.exit_code == 1

    @patch("canopy.cli._build_config", side_effect=ConfigError("bad config"))
    def test_config_error_stderr(self, _mock):
        runner = CliRunner()
        result = runner.invoke(main, ["run", "."])

        assert "bad config" in result.output

    @patch("canopy.cli._run_collectors", side_effect=CollectorError("radon failed"))
    @patch("canopy.cli._build_config")
    def test_collector_error_exit_2(self, mock_build, _mock):
        mock_build.return_value = MagicMock(source=".", output=MagicMock(path="out.svg"))

        runner = CliRunner()
        result = runner.invoke(main, ["run", "."])

        assert result.exit_code == 2

    @patch("canopy.cli._build_config", side_effect=CanopyError("something"))
    def test_generic_canopy_error_exit_1(self, _mock):
        runner = CliRunner()
        result = runner.invoke(main, ["run", "."])

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Integration test — mock only subprocess + _discover_files
# ---------------------------------------------------------------------------


class TestRunIntegration:
    @staticmethod
    def _make_dispatcher(py_path):
        mi_data = {str(py_path): {"mi": 55.0, "rank": "B"}}
        cc_data = {
            str(py_path): [
                {
                    "type": "function",
                    "name": "main",
                    "complexity": 2,
                    "classname": "",
                    "lineno": 1,
                }
            ]
        }

        def dispatcher(args, **_kwargs):
            cmd = args[0] if args else ""
            if cmd == "radon":
                if args[1] == "mi":
                    return make_proc(stdout=json.dumps(mi_data))
                return make_proc(stdout=json.dumps(cc_data))
            if cmd == "vulture":
                return make_proc(returncode=0)
            if cmd == "git":
                return make_proc(returncode=128, stderr="not a repo")
            return make_proc()

        return dispatcher

    @patch(_PATCH_DISCOVER)
    @patch(_PATCH_SUBPROCESS)
    def test_end_to_end_mocked_subprocess(self, mock_subproc, mock_discover, tmp_path):
        py_file = tmp_path / "app.py"
        py_file.write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")

        mock_subproc.side_effect = self._make_dispatcher(py_file)
        mock_discover.return_value = {"app.py": 3}

        out_svg = tmp_path / "output" / "canopy.svg"
        runner = CliRunner()
        result = runner.invoke(main, ["run", str(tmp_path), "--output", str(out_svg)])

        assert result.exit_code == 0, f"output: {result.output}"
        assert out_svg.exists()
        assert "<svg" in out_svg.read_text(encoding="utf-8")

    @patch(_PATCH_DISCOVER)
    @patch(_PATCH_SUBPROCESS)
    def test_run_stdout_message(self, mock_subproc, mock_discover, tmp_path):
        py_file = tmp_path / "app.py"
        py_file.write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")

        mock_subproc.side_effect = self._make_dispatcher(py_file)
        mock_discover.return_value = {"app.py": 3}

        out_svg = tmp_path / "canopy.svg"
        runner = CliRunner()
        result = runner.invoke(main, ["run", str(tmp_path), "--output", str(out_svg)])

        assert "written" in result.output
        assert "modules" in result.output
        assert "lines" in result.output

    @patch(_PATCH_DISCOVER)
    @patch(_PATCH_SUBPROCESS)
    def test_run_output_creates_parent_dirs(self, mock_subproc, mock_discover, tmp_path):
        py_file = tmp_path / "app.py"
        py_file.write_text("x = 1\n", encoding="utf-8")

        mock_subproc.side_effect = self._make_dispatcher(py_file)
        mock_discover.return_value = {"app.py": 1}

        out_svg = tmp_path / "deep" / "nested" / "canopy.svg"
        runner = CliRunner()
        result = runner.invoke(main, ["run", str(tmp_path), "--output", str(out_svg)])

        assert result.exit_code == 0
        assert out_svg.exists()
