import json
import os
from pathlib import Path

GLOBAL_CONFIG_DIR = Path.home() / ".portabase"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.json"


class GlobalConfig:
    KNOWN_KEYS = ("update_channel",)

    def __init__(self, path: Path = GLOBAL_CONFIG_FILE) -> None:
        self.path = path
        self.cache_dir = path.parent / "cache"

    def all(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, key: str, default=None):
        return self.all().get(key, default)

    def set(self, key: str, value) -> None:
        data = self.all()
        data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    @property
    def update_channel(self) -> str | None:
        return self.get("update_channel")
