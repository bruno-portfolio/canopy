from __future__ import annotations

import json
import subprocess

from canopy import exceptions
from canopy.collectors import RawFunctionCC, RawRadonResult, normalize_path

_TIMEOUT_SECONDS = 60


def _run_radon(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as err:
        raise exceptions.CollectorError("radon not found — pip install radon") from err
    except subprocess.TimeoutExpired as err:
        raise exceptions.CollectorError(
            f"radon timed out after {_TIMEOUT_SECONDS} seconds"
        ) from err


def _parse_mi(stdout: str) -> dict[str, tuple[float, str]]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as err:
        raise exceptions.CollectorError("Failed to parse radon output") from err

    result: dict[str, tuple[float, str]] = {}
    for path, info in data.items():
        normalized = normalize_path(path)
        result[normalized] = (info["mi"], info["rank"])
    return result


def _parse_cc(stdout: str) -> dict[str, list[RawFunctionCC]]:
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as err:
        raise exceptions.CollectorError("Failed to parse radon output") from err

    result: dict[str, list[RawFunctionCC]] = {}
    for path, functions in data.items():
        normalized = normalize_path(path)
        funcs: list[RawFunctionCC] = []
        for func in functions:
            funcs.append(
                RawFunctionCC(
                    name=func["name"],
                    complexity=func["complexity"],
                    is_method=func["type"] == "method",
                    classname=func.get("classname", ""),
                    lineno=func["lineno"],
                )
            )
        result[normalized] = funcs
    return result


def collect_radon(source_path: str) -> list[RawRadonResult]:
    mi_proc = _run_radon(["radon", "mi", "-j", source_path])
    if mi_proc.returncode != 0:
        raise exceptions.CollectorError(f"radon failed: {mi_proc.stderr}")

    cc_proc = _run_radon(["radon", "cc", "-j", source_path])
    if cc_proc.returncode != 0:
        raise exceptions.CollectorError(f"radon failed: {cc_proc.stderr}")

    mi_data = _parse_mi(mi_proc.stdout)
    cc_data = _parse_cc(cc_proc.stdout)

    results: list[RawRadonResult] = []
    for path, (mi, rank) in mi_data.items():
        functions = cc_data.get(path, [])
        results.append(
            RawRadonResult(
                path=path,
                mi=mi,
                rank=rank,
                functions=functions,
            )
        )

    return results
