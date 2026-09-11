#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.specs import DatabaseSpec  # noqa: E402
from engines import registry  # noqa: E402
from engines.base import DbEngine  # noqa: E402
from services.envfile import EnvFile  # noqa: E402
from services.ports import FixedPortAllocator  # noqa: E402
from services.project import AgentProject, DashboardProject  # noqa: E402
from services.renderer import ComposeRenderer  # noqa: E402
from services.templates import TemplateRepository  # noqa: E402

AGENT_ENV = {"TZ": "UTC", "EDGE_KEY": "x", "LOG_LEVEL": "info", "POLLING": "5"}
DASHBOARD_BASE = {
    "HOST_PORT": "8887",
    "PROJECT_SECRET": "s",
    "PROJECT_URL": "http://localhost:8887",
    "PROJECT_NAME": "pb",
    "TZ": "UTC",
    "LOG_LEVEL": "info",
}
DASHBOARD_PG = {
    "POSTGRES_DB": "pb",
    "POSTGRES_USER": "pb",
    "POSTGRES_PASSWORD": "p",
    "PG_PORT": "5433",
    "DATABASE_URL": "postgresql://pb:p@db:5432/pb",
}


class Failure(Exception):
    pass


def env_text(project: AgentProject | DashboardProject) -> str:
    return "".join(f'{k}="{v}"\n' for k, v in project.env.as_dict().items())


def validate(label: str, compose: str, env: str, use_compose: bool) -> None:
    try:
        doc = yaml.safe_load(compose)
    except yaml.YAMLError as e:
        raise Failure(f"{label}: invalid YAML: {e}\n{compose}") from e
    if not isinstance(doc, dict) or "services" not in doc:
        raise Failure(f"{label}: no services key\n{compose}")
    if use_compose:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "docker-compose.yml").write_text(compose, encoding="utf-8")
            Path(tmp, ".env").write_text(env, encoding="utf-8")
            Path(tmp, "databases.json").write_text(
                '{"databases": []}', encoding="utf-8"
            )
            proc = subprocess.run(
                ["docker", "compose", "-p", "rendercheck", "config", "--quiet"],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                raise Failure(
                    f"{label}: docker compose config failed:\n{proc.stderr}\n{compose}"
                )
    print(f"ok  {label}")


def agent_project(
    tmp: Path,
    pairs: list[tuple[DatabaseSpec, DbEngine]],
    *,
    host_gateway: bool = False,
    sqlite: bool = False,
    docker_volume: bool = False,
) -> AgentProject:
    env = EnvFile(tmp / ".env")
    env.merge(AGENT_ENV)
    project = AgentProject(tmp, env, [], host_gateway)
    for spec, engine in pairs:
        project.add(spec, engine)
    if sqlite:
        sq = registry.get("sqlite")
        project.add(
            sq.generate(auth=False, ports=FixedPortAllocator(), answers={"name": "x"}),
            sq,
        )
    if docker_volume:
        dv = registry.get("docker-volume")
        project.add(dv.from_existing({"volume": "v"}), dv)
    return project


def agent_cases(renderer: ComposeRenderer) -> list[tuple[str, str, str]]:
    ports = FixedPortAllocator()
    tmp = Path(tempfile.mkdtemp())
    cases: list[tuple[str, str, str]] = []

    empty = agent_project(tmp, [])
    cases.append(("agent/empty", renderer.render_agent(empty).compose, env_text(empty)))

    toggles = agent_project(tmp, [], host_gateway=True, sqlite=True, docker_volume=True)
    cases.append(
        ("agent/toggles", renderer.render_agent(toggles).compose, env_text(toggles))
    )

    everything: list[tuple[DatabaseSpec, DbEngine]] = []
    for engine in registry:
        if engine.template is None:
            continue
        for auth in (True, False) if engine.auth_variants else (True,):
            spec = engine.generate(auth=auth, ports=ports, answers={})
            one = agent_project(tmp, [(spec, engine)])
            variant = ("/auth" if auth else "/noauth") if engine.auth_variants else ""
            cases.append(
                (
                    f"agent/{engine.key}{variant}",
                    renderer.render_agent(one).compose,
                    env_text(one),
                )
            )
            everything.append((spec, engine))

    combined = agent_project(tmp, everything, host_gateway=True, sqlite=True)
    cases.append(
        ("agent/all", renderer.render_agent(combined).compose, env_text(combined))
    )
    return cases


def dashboard_cases(renderer: ComposeRenderer) -> list[tuple[str, str, str]]:
    tmp = Path(tempfile.mkdtemp())
    variants = {
        "external": {**DASHBOARD_BASE, **DASHBOARD_PG, "POSTGRES_HOST": "db"},
        "internal": DASHBOARD_BASE,
        "custom": {**DASHBOARD_BASE, **DASHBOARD_PG, "POSTGRES_HOST": "remote"},
    }
    cases = []
    for mode, values in variants.items():
        env = EnvFile(tmp / f".env.{mode}")
        env.merge(values)
        project = DashboardProject(tmp, env)
        if project.db_mode != mode:
            raise Failure(f"db_mode mismatch: {project.db_mode} != {mode}")
        cases.append(
            (
                f"dashboard/{mode}",
                renderer.render_dashboard(project).compose,
                env_text(project),
            )
        )
    return cases


def engines_check(repo: TemplateRepository) -> None:
    shipped = set(repo.names())
    used = set()
    for engine in registry:
        if engine.template is None:
            continue
        if engine.template not in shipped:
            raise Failure(
                f"{engine.key}: template {engine.template} not found in {repo.root}"
            )
        used.add(engine.template)
    orphans = {
        name for name in shipped if name.startswith("engines/") and name not in used
    }
    if orphans:
        raise Failure(
            f"template(s) not used by any engine: {', '.join(sorted(orphans))}"
        )
    print(f"ok  engines-check ({len(used)} templates, {len(registry.keys())} engines)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--templates", default=os.environ.get("PORTABASE_TEMPLATES_DIR", "templates")
    )
    parser.add_argument(
        "--no-compose",
        action="store_true",
        help="Skip docker compose config validation",
    )
    args = parser.parse_args()

    use_compose = not args.no_compose and shutil.which("docker") is not None
    if not use_compose:
        print("note: docker not available, YAML validation only")
    repo = TemplateRepository(Path(args.templates))
    renderer = ComposeRenderer(repo, registry, "render-check")
    try:
        engines_check(repo)
        for label, compose, env in agent_cases(renderer) + dashboard_cases(renderer):
            validate(label, compose, env, use_compose)
    except Failure as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
