from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from engines import registry
from services.ports import FixedPortAllocator
from services.project import AgentProject, DashboardProject
from services.renderer import ComposeRenderer
from services.templates import TemplateRepository
from tests.support import AGENT_ENV, DASHBOARD_MODES, ROOT, Rendered

collect_ignore = ["conftest.py", "support.py"]


def pytest_pycollect_makeitem(collector, name, obj):
    # Tests have no test_ prefix (python_functions = "[!_]*"): never collect a
    # callable that a test module only imports (functions, lru_cache wrappers,
    # pytest.mark decorators kept in constants).
    if callable(obj) and getattr(obj, "__module__", None) != collector.module.__name__:
        return []
    return None


@pytest.fixture
def ports() -> FixedPortAllocator:
    return FixedPortAllocator()


@pytest.fixture
def templates() -> TemplateRepository:
    return TemplateRepository(ROOT / "templates")


@pytest.fixture
def renderer(templates: TemplateRepository) -> ComposeRenderer:
    return ComposeRenderer(templates, registry, "test")


@pytest.fixture
def agent(tmp_path: Path) -> AgentProject:
    return AgentProject.create(tmp_path / "agent", dict(AGENT_ENV), host_gateway=False)


@pytest.fixture
def dashboard_for(tmp_path: Path) -> Callable[..., DashboardProject]:
    def build(mode: str = "internal", **env: str) -> DashboardProject:
        folder = tmp_path / f"dashboard-{len(list(tmp_path.iterdir()))}"
        return DashboardProject.create(folder, {**DASHBOARD_MODES[mode], **env})

    return build


@pytest.fixture
def dashboard(dashboard_for: Callable[..., DashboardProject]) -> DashboardProject:
    return dashboard_for(PROJECT_URL="https://d.example")


@pytest.fixture
def render_engine(
    tmp_path: Path, renderer: ComposeRenderer, ports: FixedPortAllocator
) -> Callable[..., Rendered]:
    """Generate one database of an engine, add it to a fresh agent, render it."""

    def render(
        key: str,
        *,
        auth: bool = True,
        inline: bool = False,
        answers: dict[str, Any] | None = None,
    ) -> Rendered:
        engine = registry.get(key)
        spec = engine.generate(auth=auth, ports=ports, answers=answers or {})
        folder = tmp_path / f"{key}-{len(list(tmp_path.iterdir()))}"
        project = AgentProject.create(folder, dict(AGENT_ENV), host_gateway=False)
        project.add(spec, engine)
        result = renderer.render_agent(project, inline=inline)
        result.validate()
        return Rendered(
            spec,
            yaml.safe_load(result.compose),
            project.env.as_dict(),
            result.databases or [],
        )

    return render
