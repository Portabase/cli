import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

import pytest

from core.config import GlobalConfig
from core.errors import UpdateError
from core.version import UNKNOWN
from services import updater
from services.updater import (
    RELEASES_URL,
    Release,
    UpdateChecker,
    Updater,
    platform_asset_name,
)
from tests.support import FakeHttp

LATEST = f"{RELEASES_URL}/latest"
PAYLOAD = b"new binary"


def _api_release(tag, prerelease=False, assets=()):
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "assets": [
            {"name": name, "browser_download_url": f"https://dl/{name}"}
            for name in assets
        ],
    }


def _sha(data=PAYLOAD):
    return hashlib.sha256(data).hexdigest()


def _published(checksums=None, *, binary=True):
    name = platform_asset_name()
    assets = {}
    http = FakeHttp()
    if binary:
        assets[name] = f"https://dl/{name}"
        http.files[assets[name]] = PAYLOAD
    if checksums is not None:
        assets["checksums.txt"] = "https://dl/checksums.txt"
        http.text["https://dl/checksums.txt"] = checksums
    return Updater(http, "1.0.0"), Release("2.0.0", assets, False)


@pytest.fixture
def config(tmp_path):
    return GlobalConfig(tmp_path / "config.json")


@pytest.fixture
def downloads(monkeypatch, tmp_path):
    folder = tmp_path / "downloads"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def release_from_api():
    data = _api_release("v1.2.3", prerelease=True, assets=["a", "b"])
    assert Release.from_api(data) == Release(
        "1.2.3", {"a": "https://dl/a", "b": "https://dl/b"}, True
    )
    assert Release.from_api({}) == Release("", {}, False)


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Linux", "x86_64", "portabase_linux_amd64"),
        ("Linux", "aarch64", "portabase_linux_arm64"),
        ("Darwin", "arm64", "portabase_macos_arm64"),
        ("Darwin", "x86_64", "portabase_macos_amd64"),
        ("Windows", "AMD64", "portabase_windows_amd64.exe"),
    ],
)
def asset_name_per_platform(monkeypatch, system, machine, expected):
    monkeypatch.setattr(updater.platform, "system", lambda: system)
    monkeypatch.setattr(updater.platform, "machine", lambda: machine)
    assert platform_asset_name() == expected


def frozen_flag(monkeypatch):
    assert not updater.is_frozen()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert updater.is_frozen()


@pytest.mark.parametrize(
    ("channel", "current", "expected"),
    [
        (None, "1.0.0", False),
        (None, "1.0.0rc1", True),
        ("beta", "1.0.0", True),
        ("stable", "1.0.0rc1", False),
    ],
)
def checker_include_prerelease(config, channel, current, expected):
    if channel:
        config.set("update_channel", channel)
    assert UpdateChecker(FakeHttp(), config, current).include_prerelease is expected


def checker_stable_uses_latest(config):
    http = FakeHttp(json={LATEST: _api_release("1.1.0")})
    assert UpdateChecker(http, config, "1.0.0").available() == "1.1.0"
    assert http.calls == [LATEST]


def checker_beta_uses_the_first_release(config):
    config.set("update_channel", "beta")
    releases = [_api_release("1.1.0rc1", True), _api_release("1.0.0")]
    http = FakeHttp(json={RELEASES_URL: releases})
    assert UpdateChecker(http, config, "1.0.0").available() == "1.1.0rc1"


def checker_beta_without_releases(config):
    config.set("update_channel", "beta")
    http = FakeHttp(json={RELEASES_URL: []})
    assert UpdateChecker(http, config, "1.0.0").available() is None


@pytest.mark.parametrize("tag", ["1.0.0", "0.9.0", "1.0.0rc1"])
def checker_nothing_newer(config, tag):
    http = FakeHttp(json={LATEST: _api_release(tag)})
    assert UpdateChecker(http, config, "1.0.0").available() is None


def checker_unknown_version_never_checks(config):
    http = FakeHttp()
    assert UpdateChecker(http, config, UNKNOWN).available() is None
    assert http.calls == []


def checker_network_error_is_silent(config):
    assert UpdateChecker(FakeHttp(), config, "1.0.0").available() is None
    assert not (config.cache_dir / "release.json").exists()


def checker_caches_the_release(config):
    http = FakeHttp(json={LATEST: _api_release("1.1.0")})
    checker = UpdateChecker(http, config, "1.0.0")
    assert checker.latest() == Release("1.1.0", {}, False)
    assert checker.latest() == Release("1.1.0", {}, False)
    assert http.calls == [LATEST]
    checker.latest(force=True)
    assert http.calls == [LATEST, LATEST]


def checker_refetches_an_expired_cache(config):
    http = FakeHttp(json={LATEST: _api_release("1.1.0")})
    checker = UpdateChecker(http, config, "1.0.0")
    checker.latest()
    data = json.loads(checker.cache_file.read_text(encoding="utf-8"))
    data["checked_at"] = time.time() - updater.CACHE_TTL - 1
    checker.cache_file.write_text(json.dumps(data), encoding="utf-8")
    checker.latest()
    assert http.calls == [LATEST, LATEST]


def checker_channel_change_invalidates_the_cache(config):
    http = FakeHttp(
        json={
            LATEST: _api_release("1.1.0"),
            RELEASES_URL: [_api_release("1.2.0rc1", True)],
        }
    )
    checker = UpdateChecker(http, config, "1.0.0")
    assert checker.available() == "1.1.0"
    config.set("update_channel", "beta")
    assert checker.available() == "1.2.0rc1"


def checker_survives_a_corrupt_cache(config):
    http = FakeHttp(json={LATEST: _api_release("1.1.0")})
    checker = UpdateChecker(http, config, "1.0.0")
    checker.cache_file.parent.mkdir(parents=True)
    checker.cache_file.write_text("{oops", encoding="utf-8")
    assert checker.available() == "1.1.0"


@pytest.mark.parametrize("line", ["{sha}  {name}", "{sha} *{name}", "{SHA}  {name}"])
def updater_download_verified(downloads, line):
    name = platform_asset_name()
    listed = line.format(sha=_sha(), SHA=_sha().upper(), name=name)
    updater, release = _published(f"deadbeef  other\n{listed}\n")
    progress = []
    path = updater.download(release, progress.append)
    assert path.read_bytes() == PAYLOAD
    assert path.parent == downloads
    assert progress == [len(PAYLOAD)]


@pytest.mark.parametrize(
    ("checksums", "message"),
    [
        (None, "has no checksums.txt"),
        ("abc  other_asset\n", "not listed in checksums.txt"),
        ("{bad}  {name}\n", "Checksum mismatch"),
    ],
)
def updater_download_refused(downloads, checksums, message):
    if checksums is not None:
        checksums = checksums.format(bad=_sha(b"tampered"), name=platform_asset_name())
    updater, release = _published(checksums)
    with pytest.raises(UpdateError, match=message):
        updater.download(release)
    assert list(downloads.iterdir()) == []


def updater_no_binary_for_this_platform():
    updater, release = _published(f"{_sha()}  x\n", binary=False)
    with pytest.raises(UpdateError, match="No binary for this platform") as exc:
        updater.download(release)
    assert exc.value.hint == "Available: checksums.txt"
    updater, empty = _published(None, binary=False)
    with pytest.raises(UpdateError) as exc:
        updater.download(empty)
    assert exc.value.hint is None


def updater_expected_size():
    updater, release = _published(None)
    assert updater.expected_size(release) == len(PAYLOAD)
    assert updater.expected_size(Release("2.0.0", {}, False)) is None


def updater_install_replaces_and_keeps_a_backup(tmp_path):
    target = tmp_path / "bin" / "portabase"
    target.parent.mkdir()
    target.write_bytes(b"old")
    tmp = tmp_path / "download"
    tmp.write_bytes(PAYLOAD)
    Updater(FakeHttp(), "1.0.0").install(tmp, target)
    assert target.read_bytes() == PAYLOAD
    assert (target.stat().st_mode & 0o777) == 0o755
    assert target.with_name("portabase.old").read_bytes() == b"old"
    assert not tmp.exists()


def updater_install_fresh(tmp_path):
    target = tmp_path / "new" / "bin" / "portabase"
    tmp = tmp_path / "download"
    tmp.write_bytes(PAYLOAD)
    Updater(FakeHttp(), "1.0.0").install(tmp, target)
    assert target.read_bytes() == PAYLOAD
    assert not target.with_name("portabase.old").exists()


def updater_target_path_frozen(monkeypatch, tmp_path):
    exe = tmp_path / "portabase"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert Updater(FakeHttp(), "1.0.0").target_path() == exe.resolve()


def updater_target_path_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(updater.platform, "system", lambda: "Windows")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    expected = Path(tmp_path) / "Portabase" / "portabase.exe"
    assert Updater(FakeHttp(), "1.0.0").target_path() == expected
