from __future__ import annotations

import re
import sys
import tomllib
from functools import lru_cache
from pathlib import Path

UNKNOWN = "unknown"
_PRE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-.]?(rc|alpha|beta|a|b)(\d*))?$", re.I)


@lru_cache(maxsize=1)
def current_version() -> str:
    try:
        bundled = getattr(sys, "_MEIPASS", None)
        base = Path(bundled) if bundled else Path(__file__).parent.parent
        with open(base / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError, AttributeError):
        return UNKNOWN


def is_prerelease(version: str) -> bool:
    m = _PRE.match(version.strip().lstrip("v"))
    return bool(m and m.group(4))


def parse_version(version: str) -> tuple[int, int, int, int, int]:
    m = _PRE.match(version.strip().lstrip("v"))
    if not m:
        return (0, 0, 0, 0, 0)
    major, minor, patch = (int(m.group(i)) for i in (1, 2, 3))
    tag = (m.group(4) or "").lower()
    rank = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2, "": 3}[tag]
    num = int(m.group(5)) if m.group(5) else 0
    return (major, minor, patch, rank, num)
