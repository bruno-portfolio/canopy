from __future__ import annotations

import subprocess
import warnings
from collections import Counter

from canopy import exceptions
from canopy.collectors import RawChurnResult, normalize_path

_TIMEOUT_SECONDS = 60


def _run_git(
    args: list[str],
    cwd: str,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as err:
        raise exceptions.CollectorError("git not found") from err
    except subprocess.TimeoutExpired as err:
        raise exceptions.CollectorError(f"git timed out after {_TIMEOUT_SECONDS} seconds") from err


def _is_shallow_clone(project_path: str) -> bool:
    proc = _run_git(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=project_path,
    )
    return proc.stdout.strip() == "true"


def _parse_file_counts(stdout: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped:
            counts[normalize_path(stripped)] += 1
    return counts


def collect_churn(
    project_path: str,
    days: int = 30,
) -> list[RawChurnResult]:
    check = _run_git(
        ["git", "rev-parse", "--git-dir"],
        cwd=project_path,
    )
    if check.returncode != 0:
        raise exceptions.CollectorError("not a git repository")

    if _is_shallow_clone(project_path):
        warnings.warn(
            "Shallow clone detected — churn data unavailable",
            stacklevel=2,
        )
        return []

    proc = _run_git(
        [
            "git",
            "log",
            f"--since={days} days ago",
            "--name-only",
            "--pretty=format:",
            "--",
            "*.py",
        ],
        cwd=project_path,
    )

    counts = _parse_file_counts(proc.stdout)

    return [RawChurnResult(path=path, commit_count=count) for path, count in counts.items()]
