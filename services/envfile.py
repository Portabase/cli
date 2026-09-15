from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

_LINE = re.compile(r"""^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$""")


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        inner = raw[1:-1]
        if raw[0] == '"':
            return inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return raw.split(" #", 1)[0].rstrip()


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass
class EnvFile:
    path: Path
    _lines: list[str] = field(default_factory=list)
    _index: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> EnvFile:
        env = cls(path)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            env._lines = text.splitlines()
            for index, line in enumerate(env._lines):
                match = _LINE.match(line)
                if match and not line.lstrip().startswith("#"):
                    env._index[match.group(1)] = index
        return env

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def get(self, key: str, default: str | None = None) -> str | None:
        index = self._index.get(key)
        if index is None:
            return default
        match = _LINE.match(self._lines[index])
        return _unquote(match.group(2)) if match else default

    def as_dict(self) -> dict[str, str]:
        return {key: self.get(key) or "" for key in self._index}

    def set(self, key: str, value: str) -> None:
        line = f"{key}={_quote(str(value))}"
        index = self._index.get(key)
        if index is None:
            self._lines.append(line)
            self._index[key] = len(self._lines) - 1
        else:
            self._lines[index] = line

    def merge(self, mapping: Mapping[str, str]) -> None:
        for key, value in mapping.items():
            self.set(key, value)

    def remove(self, key: str) -> None:
        index = self._index.pop(key, None)
        if index is None:
            return
        del self._lines[index]
        self._index = {
            name: (position - 1 if position > index else position)
            for name, position in self._index.items()
        }

    def remove_prefix(self, prefix: str) -> None:
        for key in [name for name in self._index if name.startswith(prefix + "_")]:
            self.remove(key)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text("\n".join(self._lines) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
