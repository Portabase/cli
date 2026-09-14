from __future__ import annotations

import re
import sys
import tomllib
from functools import lru_cache
from pathlib import Path

UNKNOWN = "unknown"
_PRE = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?:[-.]?(rc|alpha|beta|a|b)(\d*)(?:\.(\d+))?)?$", re.I
)


@lru_cache(maxsize=1)
def current_version() -> str:
    try:
        bundled = getattr(sys, "_MEIPASS", None)
        base = Path(bundled) if bundled else Path(__file__).parent.parent
        with open(base / "pyproject.toml", "rb") as file:
            return tomllib.load(file)["project"]["version"]
    except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError, AttributeError):
        return UNKNOWN


def is_prerelease(version: str) -> bool:
    match = _PRE.match(version.strip().lstrip("v"))
    return bool(match and match.group(4))


def parse_version(version: str) -> tuple[int, int, int, int, int, int]:
    match = _PRE.match(version.strip().lstrip("v"))
    if not match:
        return (0, 0, 0, 0, 0, 0)
    major, minor, patch = (int(match.group(group)) for group in (1, 2, 3))
    tag = (match.group(4) or "").lower()
    rank = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2, "": 3}[tag]
    num, sub = match.group(5), match.group(6)
    if not num:
        num, sub = sub, None  # "beta.2" is beta 2, like "beta2"
    return (major, minor, patch, rank, int(num or 0), int(sub or 0))
