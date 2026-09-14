import re
import tomllib

import pytest

from core.version import current_version, is_prerelease, parse_version
from tests.support import ROOT

ZERO = (0, 0, 0, 0, 0, 0)


def current_version_reads_pyproject():
    with open(ROOT / "pyproject.toml", "rb") as file:
        expected = tomllib.load(file)["project"]["version"]
    assert current_version() == expected


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("26.08.12", (26, 8, 12, 3, 0, 0)),
        ("v1.2.3", (1, 2, 3, 3, 0, 0)),
        (" 1.2.3 ", (1, 2, 3, 3, 0, 0)),
        ("1.2.3rc1", (1, 2, 3, 2, 1, 0)),
        ("1.2.3-rc2", (1, 2, 3, 2, 2, 0)),
        ("1.2.3.beta4", (1, 2, 3, 1, 4, 0)),
        ("1.2.3b", (1, 2, 3, 1, 0, 0)),
        ("1.2.3-alpha", (1, 2, 3, 0, 0, 0)),
        ("1.2.3a7", (1, 2, 3, 0, 7, 0)),
        ("1.2.3RC1", (1, 2, 3, 2, 1, 0)),
        ("1.2.3-beta.2", (1, 2, 3, 1, 2, 0)),
        ("26.09.0rc1.2", (26, 9, 0, 2, 1, 2)),
        ("unknown", ZERO),
        ("1.2", ZERO),
        ("1.2.3.4", ZERO),
    ],
)
def parse_version_cases(version, expected):
    assert parse_version(version) == expected


@pytest.mark.parametrize(
    ("older", "newer"),
    [
        ("1.0.0-alpha1", "1.0.0-beta1"),
        ("1.0.0-beta9", "1.0.0rc1"),
        ("1.0.0-beta.1", "1.0.0-beta.2"),
        ("1.0.0-beta.3", "1.0.0rc1"),
        ("1.0.0rc1", "1.0.0rc1.1"),
        ("1.0.0rc1.9", "1.0.0rc2"),
        ("1.0.0rc9", "1.0.0"),
        ("1.0.9", "1.0.10"),
        ("26.08.12", "26.09.0"),
    ],
)
def parse_version_ordering(older, newer):
    assert parse_version(older) < parse_version(newer)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.0.0", False),
        ("v1.0.0", False),
        ("1.0.0rc1", True),
        ("1.0.0-beta", True),
        ("1.0.0-beta.1", True),
        ("26.09.0rc1.2", True),
        ("garbage", False),
    ],
)
def is_prerelease_cases(version, expected):
    assert is_prerelease(version) is expected


def _bump_patterns():
    workflow = (ROOT / ".github" / "workflows" / "bump.yml").read_text(encoding="utf-8")
    patterns = re.findall(r"=~ (\^\S+\$) \]\]", workflow)
    assert len(patterns) == 2, "bump.yml version checks changed; update this test"
    return patterns


@pytest.mark.parametrize(
    "version",
    [
        "26.09.0",
        "26.09.0rc1",
        "26.09.0rc1.2",
        "26.09.0-beta.1",
        "26.09.0.alpha3",
        "26.09.0b",
        "26.09",
        "26.09.0-dev1",
    ],
)
def bump_versions_are_understood(version):
    if any(re.fullmatch(pattern, version) for pattern in _bump_patterns()):
        assert parse_version(version) != ZERO
        assert is_prerelease(version) is not re.fullmatch(r"\d+\.\d+\.\d+", version)
