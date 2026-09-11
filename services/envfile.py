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
            for i, line in enumerate(env._lines):
                m = _LINE.match(line)
                if m and not line.lstrip().startswith("#"):
                    env._index[m.group(1)] = i
        return env

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def get(self, key: str, default: str | None = None) -> str | None:
        i = self._index.get(key)
        if i is None:
            return default
        m = _LINE.match(self._lines[i])
        return _unquote(m.group(2)) if m else default

    def as_dict(self) -> dict[str, str]:
        return {k: self.get(k) or "" for k in self._index}

    def set(self, key: str, value: str) -> None:
        line = f"{key}={_quote(str(value))}"
        i = self._index.get(key)
        if i is None:
            self._lines.append(line)
            self._index[key] = len(self._lines) - 1
        else:
            self._lines[i] = line

    def merge(self, mapping: Mapping[str, str]) -> None:
        for k, v in mapping.items():
            self.set(k, v)

    def remove(self, key: str) -> None:
        i = self._index.pop(key, None)
        if i is None:
            return
        del self._lines[i]
        self._index = {k: (n - 1 if n > i else n) for k, n in self._index.items()}

    def remove_prefix(self, prefix: str) -> None:
        for key in [k for k in self._index if k.startswith(prefix + "_")]:
            self.remove(key)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text("\n".join(self._lines) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
