import json

import pytest

from core.config import GlobalConfig


@pytest.fixture
def config(tmp_path):
    return GlobalConfig(tmp_path / "home" / ".portabase" / "config.json")


def missing_file_reads_as_empty(config):
    assert config.all() == {}
    assert config.get("update_channel", "stable") == "stable"
    assert config.update_channel is None


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", ""])
def unreadable_file_reads_as_empty(config, content):
    config.path.parent.mkdir(parents=True)
    config.path.write_text(content, encoding="utf-8")
    assert config.all() == {}


def set_creates_the_file_and_keeps_other_keys(config):
    config.set("update_channel", "beta")
    config.set("other", 1)
    assert json.loads(config.path.read_text(encoding="utf-8")) == {
        "update_channel": "beta",
        "other": 1,
    }
    assert config.update_channel == "beta"
    assert not config.path.with_suffix(".json.tmp").exists()


def cache_dir_is_next_to_the_file(config):
    assert config.cache_dir == config.path.parent / "cache"
