import dataclasses
import json
import re

import pytest
import yaml

from core.errors import TemplateError
from engines import registry
from services.compose_facts import CA_BUNDLE_IN_CONTAINER, GENERATED_MARKER
from services.renderer import LEGACY_BACKUP, RenderResult
from tests.support import agent_service

TEMPLATED = [engine for engine in registry if engine.template is not None]
VARIANTS = [
    (engine, auth)
    for engine in TEMPLATED
    for auth in ((True, False) if engine.auth_variants else (True,))
]
VAR = re.compile(r"\$\{([A-Za-z0-9_]+)\}")
# Values that break an unquoted "- KEY=value" item or a naive double-quoted one.
NASTY = ["abc:", "a: b", "#start", 'q"uote', "back\\slash", "ends\\", "{x}", "[y]"]


def _parse(result):
    result.validate()
    return yaml.safe_load(result.compose)


def _assert_vars_defined(compose, env):
    missing = set(VAR.findall(compose)) - set(env.as_dict())
    assert not missing, f"compose references undefined variables: {missing}"


def _password_values(service):
    values = []
    for item in service.get("environment") or []:
        assert isinstance(item, str), f"environment item parsed as {item!r}"
        key, _, value = item.partition("=")
        if key.endswith("PASSWORD") and key != "MYSQL_RANDOM_ROOT_PASSWORD":
            values.append(value)
    command = service.get("command")
    if isinstance(command, list) and "--requirepass" in command:
        values.append(command[command.index("--requirepass") + 1])
    return values


def header_marks_the_file_as_generated(renderer):
    assert renderer.header() == f"{GENERATED_MARKER} test. Do not edit.\n"


def agent_without_databases(agent, renderer):
    result = renderer.render_agent(agent)
    assert _parse(result) == {
        "services": {"agent": agent_service()},
        "networks": {"portabase": {"name": "portabase_network", "external": True}},
    }
    assert result.databases == []


def agent_inline(agent, renderer):
    result = renderer.render_agent(agent, inline=True)
    assert _parse(result)["services"] == {"agent": agent_service(inline=True)}
    assert "${" not in result.compose


def agent_with_every_option(agent, renderer, ports):
    sqlite, volume = registry.get("sqlite"), registry.get("docker-volume")
    agent.host_gateway = True
    agent.add(sqlite.generate(auth=False, ports=ports, answers={"name": "x"}), sqlite)
    agent.add(volume.from_existing({"volume": "v"}), volume)
    agent.ca_bundle = "./ca.crt"
    agent.set("retry_attempts", 3)
    result = renderer.render_agent(agent)
    expected = agent_service(
        "./x.sqlite:/config/x.sqlite",
        "/var/run/docker.sock:/var/run/docker.sock",
        f"./ca.crt:{CA_BUNDLE_IN_CONTAINER}:ro",
    )
    expected["extra_hosts"] = ["localhost:host-gateway"]
    expected["environment"]["RETRY_ATTEMPTS"] = "${RETRY_ATTEMPTS}"
    expected["environment"]["SSL_CERT_FILE"] = "${SSL_CERT_FILE}"
    assert _parse(result)["services"] == {"agent": expected}
    assert [entry["type"] for entry in result.databases or []] == [
        "sqlite",
        "docker-volume",
    ]
    _assert_vars_defined(result.compose, agent.env)


def agent_with_every_engine(agent, renderer, ports):
    specs = []
    for engine, auth in VARIANTS:
        spec = engine.generate(auth=auth, ports=ports, answers={})
        agent.add(spec, engine)
        specs.append(spec)
    result = renderer.render_agent(agent)
    doc = _parse(result)
    assert set(doc["services"]) == {"agent", *(spec.host for spec in specs)}
    assert set(doc["volumes"]) == {f"{spec.host}-data" for spec in specs}
    assert result.databases == [
        registry.get(spec.engine).agent_entry(spec) for spec in specs
    ]
    _assert_vars_defined(result.compose, agent.env)


@pytest.mark.parametrize("password", NASTY)
@pytest.mark.parametrize("engine", TEMPLATED, ids=lambda engine: engine.key)
def agent_inline_keeps_passwords_intact(engine, password, agent, renderer, ports):
    spec = dataclasses.replace(
        engine.generate(auth=True, ports=ports, answers={}),
        password=password,
        root_password=password if engine.key == "firebird" else None,
    )
    agent.add(spec, engine)
    doc = _parse(renderer.render_agent(agent, inline=True))
    values = _password_values(doc["services"][spec.host])
    assert values
    assert all(value == password for value in values)


@pytest.mark.parametrize(
    ("mode", "services", "volumes"),
    [
        ("external", {"portabase", "db"}, {"postgres-data", "portabase-data"}),
        ("internal", {"portabase"}, {"portabase-data"}),
        ("custom", {"portabase"}, {"portabase-data"}),
    ],
)
def dashboard_modes(dashboard_for, renderer, mode, services, volumes):
    project = dashboard_for(mode)
    result = renderer.render_dashboard(project)
    doc = _parse(result)
    assert doc["name"] == "pb"
    assert set(doc["services"]) == services
    assert set(doc["volumes"]) == volumes
    assert ("depends_on" in doc["services"]["portabase"]) is (mode == "external")
    assert result.databases is None
    _assert_vars_defined(result.compose, project.env)


def dashboard_inline(dashboard_for, renderer):
    result = renderer.render_dashboard(dashboard_for("external"), inline=True)
    doc = _parse(result)
    assert "${" not in result.compose
    assert doc["services"]["portabase"]["ports"] == ["8887:80"]
    assert "POSTGRES_PASSWORD=p" in doc["services"]["db"]["environment"]


@pytest.mark.parametrize("password", NASTY)
def dashboard_inline_keeps_passwords_intact(password, dashboard_for, renderer):
    project = dashboard_for(
        "external", POSTGRES_PASSWORD=password, PROJECT_SECRET=password
    )
    doc = _parse(renderer.render_dashboard(project, inline=True))
    assert _password_values(doc["services"]["db"]) == [password]
    assert f"PROJECT_SECRET={password}" in doc["services"]["portabase"]["environment"]


@pytest.mark.parametrize("compose", ["services: [unclosed", "name: x\n", "- a\n"])
def validate_rejects_broken_compose(compose):
    with pytest.raises(TemplateError):
        RenderResult(compose).validate()


def write_new_folder(tmp_path):
    folder = tmp_path / "new"
    result = RenderResult("services: {}\n", databases=[{"type": "sqlite"}])
    report = result.write(folder)
    compose, databases = folder / "docker-compose.yml", folder / "databases.json"
    assert report.wrote == [compose, databases]
    assert report.backed_up is None
    assert compose.read_text(encoding="utf-8") == "services: {}\n"
    assert json.loads(databases.read_text(encoding="utf-8")) == {
        "databases": [{"type": "sqlite"}]
    }
    assert not list(folder.glob("*.tmp"))


def write_skips_databases_for_dashboards(tmp_path):
    RenderResult("services: {}\n").write(tmp_path)
    assert not (tmp_path / "databases.json").exists()


def write_backs_up_a_hand_written_compose_once(tmp_path, renderer):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("services: {legacy: {}}\n", encoding="utf-8")
    generated = RenderResult(renderer.header() + "services: {}\n")

    report = generated.write(tmp_path)
    assert report.backed_up == tmp_path / LEGACY_BACKUP
    assert report.backed_up.read_text(encoding="utf-8") == "services: {legacy: {}}\n"

    compose.write_text("services: {edited: {}}\n", encoding="utf-8")
    assert generated.write(tmp_path).backed_up is None
    backup = (tmp_path / LEGACY_BACKUP).read_text(encoding="utf-8")
    assert backup == "services: {legacy: {}}\n"


def write_leaves_a_generated_compose_alone(tmp_path, renderer):
    generated = RenderResult(renderer.header() + "services: {}\n")
    generated.write(tmp_path)
    assert generated.write(tmp_path).backed_up is None
    assert not (tmp_path / LEGACY_BACKUP).exists()


def write_refuses_an_invalid_compose(tmp_path):
    with pytest.raises(TemplateError):
        RenderResult("nope: 1\n").write(tmp_path)
    assert not (tmp_path / "docker-compose.yml").exists()


def diff_against_the_current_file(tmp_path):
    result = RenderResult("services:\n  a: {}\n")
    assert "+services:" in result.diff_against(tmp_path)
    result.write(tmp_path)
    assert result.diff_against(tmp_path) == ""
    changed = RenderResult("services:\n  b: {}\n").diff_against(tmp_path)
    assert "-  a: {}" in changed
    assert "+  b: {}" in changed
