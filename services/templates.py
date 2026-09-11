from __future__ import annotations

import os
import sys
from pathlib import Path

import jinja2

from core.errors import TemplateError

TEMPLATES_DIR = "templates"
ROOT_TEMPLATE = "agent.yml.j2"


class TemplateRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._env: jinja2.Environment | None = None

    @classmethod
    def bundled(cls) -> TemplateRepository:
        override = os.environ.get("PORTABASE_TEMPLATES_DIR")
        if override:
            return cls(Path(override))
        bundle = getattr(sys, "_MEIPASS", None)
        base = Path(bundle) if bundle else Path(__file__).resolve().parent.parent
        return cls(base / TEMPLATES_DIR)

    def resolve(self) -> Path:
        if not (self.root / ROOT_TEMPLATE).exists():
            raise TemplateError(
                f"No templates found in {self.root}.",
                hint=(
                    "The CLI ships its own templates; either the build is broken "
                    "or PORTABASE_TEMPLATES_DIR points at the wrong folder."
                ),
            )
        return self.root

    def names(self) -> list[str]:
        return sorted(
            p.relative_to(self.root).as_posix() for p in self.root.rglob("*.j2")
        )

    def get(self, name: str) -> jinja2.Template:
        root = self.resolve()
        if self._env is None:
            self._env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(str(root)),
                undefined=jinja2.StrictUndefined,
                keep_trailing_newline=True,
                autoescape=False,  # noqa: S701 — renders YAML, not HTML
            )
        try:
            return self._env.get_template(name)
        except jinja2.TemplateNotFound as e:
            raise TemplateError(
                f"Template '{name}' is missing from {root}.", cause=e
            ) from e
        except jinja2.TemplateError as e:
            raise TemplateError(
                f"Template '{name}' failed to load: {e}", cause=e
            ) from e
