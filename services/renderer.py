from __future__ import annotations

import contextlib
import difflib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2
import yaml

from core.errors import TemplateError
from core.specs import DatabaseSpec
from engines import EngineRegistry
from services.compose_facts import GENERATED_MARKER, ComposeFacts
from services.envfile import EnvFile
from services.project import (
    COMPOSE_FILE,
    DATABASES_FILE,
    AgentProject,
    DashboardProject,
)
from services.templates import TemplateRepository

LEGACY_BACKUP = "docker-compose.legacy.yml"


@dataclass
class WriteReport:
    backed_up: Path | None = None
    wrote: list[Path] = field(default_factory=list)


@dataclass
class RenderResult:
    compose: str
    databases: list[dict[str, Any]] | None = None

    def validate(self) -> None:
        try:
            doc = yaml.safe_load(self.compose)
        except yaml.YAMLError as e:
            raise TemplateError(
                "Rendered compose is not valid YAML; templates are broken.", cause=e
            ) from e
        if not isinstance(doc, dict) or "services" not in doc:
            raise TemplateError(
                "Rendered compose has no 'services' section; templates are broken."
            )

    def write(self, path: Path) -> WriteReport:
        self.validate()
        report = WriteReport()
        compose_path = path / COMPOSE_FILE
        facts = ComposeFacts(compose_path)
        if facts.exists and not facts.is_generated:
            backup = path / LEGACY_BACKUP
            if not backup.exists():
                shutil.copy2(compose_path, backup)
                report.backed_up = backup
        _atomic_write(compose_path, self.compose)
        report.wrote.append(compose_path)
        if self.databases is not None:
            db_path = path / DATABASES_FILE
            _atomic_write(
                db_path, json.dumps({"databases": self.databases}, indent=2) + "\n"
            )
            with contextlib.suppress(OSError):
                os.chmod(db_path, 0o666)
            report.wrote.append(db_path)
        return report

    def diff_against(self, path: Path) -> str:
        compose_path = path / COMPOSE_FILE
        current = (
            compose_path.read_text(encoding="utf-8") if compose_path.exists() else ""
        )
        return "".join(
            difflib.unified_diff(
                current.splitlines(keepends=True),
                self.compose.splitlines(keepends=True),
                fromfile=f"{COMPOSE_FILE} (current)",
                tofile=f"{COMPOSE_FILE} (rendered)",
            )
        )


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _var(env: EnvFile, key: str, inline: bool) -> str:
    return (env.get(key) or "") if inline else f"${{{key}}}"


class ComposeRenderer:
    def __init__(
        self, templates: TemplateRepository, engines: EngineRegistry, cli_version: str
    ) -> None:
        self.templates = templates
        self.engines = engines
        self.cli_version = cli_version

    def header(self) -> str:
        return f"{GENERATED_MARKER} {self.cli_version}. Do not edit.\n"

    def render_agent(
        self, project: AgentProject, *, inline: bool = False
    ) -> RenderResult:
        env = project.env
        ctx = {
            "host_gateway": project.host_gateway,
            "docker_socket": project.needs_docker_socket,
            "mounts": [{"host": h, "container": c} for h, c in project.sqlite_mounts],
            "services": [self._service(spec, inline) for spec in project.managed],
            "tz_var": _var(env, "TZ", inline),
            "edge_key_var": _var(env, "EDGE_KEY", inline),
            "log_level_var": _var(env, "LOG_LEVEL", inline),
            "polling_var": _var(env, "POLLING", inline),
        }
        compose = self.header() + self._render("agent.yml.j2", ctx)
        databases = [
            self.engines.get(d.engine).agent_entry(d) for d in project.databases
        ]
        return RenderResult(compose=compose, databases=databases)

    def _service(self, spec: DatabaseSpec, inline: bool) -> dict[str, str]:
        engine = self.engines.get(spec.engine)
        template = self.templates.get(engine.template or "")
        body = self._render_template(template, engine.template_ctx(spec, inline=inline))
        return {"name": spec.host or "", "volume": f"{spec.host}-data", "body": body}

    def render_dashboard(
        self, project: DashboardProject, *, inline: bool = False
    ) -> RenderResult:
        env = project.env
        ctx = {
            "db_mode": project.db_mode,
            "project_name_var": project.project_name,
            "host_port_var": _var(env, "HOST_PORT", inline),
            "tz_var": _var(env, "TZ", inline),
            "log_level_var": _var(env, "LOG_LEVEL", inline),
            "project_secret_var": _var(env, "PROJECT_SECRET", inline),
            "project_url_var": _var(env, "PROJECT_URL", inline),
            "pg_port_var": _var(env, "PG_PORT", inline),
            "postgres_db_var": _var(env, "POSTGRES_DB", inline),
            "postgres_user_var": _var(env, "POSTGRES_USER", inline),
            "postgres_password_var": _var(env, "POSTGRES_PASSWORD", inline),
        }
        compose = self.header() + self._render("dashboard.yml.j2", ctx)
        return RenderResult(compose=compose, databases=None)

    def _render(self, name: str, ctx: dict[str, Any]) -> str:
        return self._render_template(self.templates.get(name), ctx)

    @staticmethod
    def _render_template(template: jinja2.Template, ctx: dict[str, Any]) -> str:
        try:
            return template.render(**ctx)
        except jinja2.TemplateError as e:
            raise TemplateError(f"Template rendering failed: {e}", cause=e) from e
