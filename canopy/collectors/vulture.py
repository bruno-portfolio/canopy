from __future__ import annotations

import re
import subprocess

from canopy import exceptions
from canopy.collectors import RawVultureResult, normalize_path

_TIMEOUT_SECONDS = 60

_LINE_PATTERN = re.compile(
    r"^(.+):(\d+): unused (\w+) '(.+?)' \((\d+)% confidence(?:,\s*\d+\s+lines?)?\)$"
)


def collect_vulture(
    source_path: str,
    min_confidence: int = 60,
) -> list[RawVultureResult]:
    try:
        proc = subprocess.run(
            [
                "vulture",
                source_path,
                f"--min-confidence={min_confidence}",
            ],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as err:
        raise exceptions.CollectorError("vulture not found — pip install vulture") from err
    except subprocess.TimeoutExpired as err:
        raise exceptions.CollectorError(
            f"vulture timed out after {_TIMEOUT_SECONDS} seconds"
        ) from err

    if proc.returncode == 0:
        return []

    if proc.returncode != 3:
        raise exceptions.CollectorError(f"vulture failed: {proc.stderr}")

    results: list[RawVultureResult] = []
    for line in proc.stdout.splitlines():
        match = _LINE_PATTERN.match(line)
        if not match:
            continue
        results.append(
            RawVultureResult(
                path=normalize_path(match.group(1)),
                lineno=int(match.group(2)),
                kind=match.group(3),
                name=match.group(4),
                confidence=int(match.group(5)),
            )
        )

    return results
