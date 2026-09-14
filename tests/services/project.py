import dataclasses
import json

import pytest

from core.errors import ConfigError, ValidationError
from engines import registry
from services.compose_facts import CA_BUNDLE_IN_CONTAINER
from services.envfile import EnvFile
from services.project import (
    AgentProject,
    AuthProvider,
    DashboardProject,
    detect_kind,
    spec_from_entry,
)
from tests.support import EXISTING_ANSWERS

PG = registry.get("postgresql")
FIREBIRD = registry.get("firebird")
SQLITE = registry.get("sqlite")
VOLUME = registry.get("docker-volume")
KEYCLOAK = AuthProvider(
    kind="oidc",
    id="my-kc",
    values={
        "issuer": "https://kc.example",
        "client": "c",
        "secret": "s",
        "title": "",
        "pkce": True,
        "host": "",
    },
)
GITHUB = AuthProvider(
    kind="oauth",
    id="github",
    values={"client": "gc", "secret": "gs", "title": "GitHub"},
)


def detect_kind_cases(tmp_path):
    agent, dashboard, empty = (tmp_path / name for name in ("a", "d", "e"))
    for folder in (agent, dashboard, empty):
        folder.mkdir()
    (agent / "databases.json").write_text("{}", encoding="utf-8")
    (dashboard / ".env").write_text("PROJECT_SECRET=s\n", encoding="utf-8")
    assert detect_kind(agent) == "agent"
    assert detect_kind(dashboard) == "dashboard"
    with pytest.raises(ConfigError, match="not a Portabase agent or dashboard"):
        detect_kind(empty)


def spec_from_entry_managed(tmp_path):
    env = EnvFile(tmp_path / ".env")
    env.merge({"DB_FB_AB12_PORT": "40001", "DB_FB_AB12_ROOT_PASS": "root"})
    entry = {
        "name": "fb",
        "database": "/data/mirror.fdb",
        "type": "firebird",
        "username": "alice",
        "password": "pw",
        "port": 3050,
        "host": "db-fb-ab12",
        "generated_id": "id-1",
        "options": {"x": 1},
    }
    spec = spec_from_entry(entry, env)
    assert spec.managed
    assert (spec.id, spec.engine, spec.host, spec.port, spec.host_port) == (
        "id-1",
        "firebird",
        "db-fb-ab12",
        3050,
        40001,
    )
    assert (spec.password, spec.root_password) == ("pw", "root")
    assert spec.options == {"x": 1}
    assert spec.path is None


def spec_from_entry_external(tmp_path):
    entry = {**EXISTING_ANSWERS, "type": "postgresql", "port": "5432", "password": ""}
    spec = spec_from_entry(entry, EnvFile(tmp_path / ".env"))
    assert not spec.managed
    assert spec.host_port is None
    assert spec.port == 5432
    assert spec.password is None
    assert spec.id


def spec_from_entry_sqlite_and_volume(tmp_path):
    env = EnvFile(tmp_path / ".env")
    sqlite = spec_from_entry({"type": "sqlite", "database": "/config/app.sqlite"}, env)
    volume = spec_from_entry(
        {"type": "docker-volume", "volume_name": "v", "container_name": ""}, env
    )
    assert (sqlite.path, sqlite.host) == ("/config/app.sqlite", None)
    assert (volume.volume, volume.container) == ("v", None)


def agent_create_does_not_write_env(agent):
    assert agent.path.is_dir()
    assert not agent.env.exists
    assert agent.env.get("POLLING") == "5"


def agent_add_managed_merges_env(agent, ports):
    spec = PG.generate(auth=True, ports=ports, answers={})
    agent.add(spec, PG)
    assert agent.managed == [spec]
    assert agent.env.get(f"{spec.env_prefix}_PORT") == "40000"
    assert agent.env.get(f"{spec.env_prefix}_PASS") == spec.password


def agent_add_external_leaves_env(agent):
    before = agent.env.as_dict()
    agent.add(PG.from_existing(EXISTING_ANSWERS), PG)
    assert agent.env.as_dict() == before
    assert agent.managed == []


def agent_add_refuses_a_duplicate_service_name(agent, ports):
    first = PG.generate(auth=True, ports=ports, answers={})
    agent.add(first, PG)
    clash = dataclasses.replace(
        PG.generate(auth=True, ports=ports, answers={}), host=first.host
    )
    with pytest.raises(ConfigError, match="share the service name"):
        agent.add(clash, PG)


def agent_remove_purges_its_env_prefix(agent, ports):
    keep = PG.generate(auth=True, ports=ports, answers={})
    gone = PG.generate(auth=True, ports=ports, answers={})
    agent.add(keep, PG)
    agent.add(gone, PG)
    agent.remove(gone, PG)
    assert agent.databases == [keep]
    assert not any(key.startswith(gone.env_prefix) for key in agent.env.as_dict())
    assert agent.env.get(f"{keep.env_prefix}_PORT") == "40000"
    assert agent.env.get("EDGE_KEY") == "x"


def agent_find(agent, ports):
    first = dataclasses.replace(
        PG.generate(auth=True, ports=ports, answers={}), id="aaaa-1111", name="main"
    )
    second = dataclasses.replace(
        PG.generate(auth=True, ports=ports, answers={}), id="aaab-2222", name="other"
    )
    agent.add(first, PG)
    agent.add(second, PG)
    assert agent.find("aaaa-1111") is first
    assert agent.find("aaab") is second
    assert agent.find("main") is first
    with pytest.raises(ValidationError, match="No database matching"):
        agent.find("zzz")
    with pytest.raises(ValidationError, match="matches several"):
        agent.find("aaa")


def agent_settings(agent):
    assert agent.setting("polling") == 5
    assert agent.setting("host_gateway") is False
    assert agent.setting("retry_attempts") is None
    agent.set("polling", 30)
    agent.set("host_gateway", True)
    agent.set("retry_attempts", 3)
    assert agent.env.get("POLLING") == "30"
    assert agent.host_gateway is True
    assert agent.extra_env == ["RETRY_ATTEMPTS"]
    assert set(agent.settings()) == set(agent.registry.names())
    agent.unset("retry_attempts")
    assert agent.env.get("RETRY_ATTEMPTS") is None
    assert agent.extra_env == []


@pytest.mark.parametrize("name", ["key", "tz", "polling", "log_level", "host_gateway"])
def agent_core_settings_cannot_be_unset(agent, name):
    with pytest.raises(ValidationError, match="cannot be unset"):
        agent.unset(name)


def agent_ca_bundle(agent):
    (agent.path / "ca.crt").write_text("pem", encoding="utf-8")
    agent.ca_bundle = "ca.crt"
    agent.validate()
    assert agent.env.get("SSL_CERT_FILE") == CA_BUNDLE_IN_CONTAINER
    agent.ca_bundle = None
    assert agent.ca_bundle is None
    assert agent.env.get("SSL_CERT_FILE") is None


def agent_missing_ca_bundle(agent):
    agent.ca_bundle = "missing.crt"
    with pytest.raises(ValidationError, match="CA bundle not found"):
        agent.save_state()
    assert not agent.env.exists


def agent_docker_socket_and_sqlite_mounts(agent, ports):
    assert not agent.needs_docker_socket
    agent.add(VOLUME.from_existing({"volume": "v"}), VOLUME)
    for _ in range(2):
        agent.add(
            SQLITE.generate(auth=False, ports=ports, answers={"name": "app"}), SQLITE
        )
    agent.add(SQLITE.from_existing({"path": "/abs/app.db"}), SQLITE)
    assert agent.needs_docker_socket
    assert agent.sqlite_mounts == [("./app.sqlite", "/config/app.sqlite")]


def agent_load_round_trip(agent, ports, renderer):
    spec = FIREBIRD.generate(auth=True, ports=ports, answers={})
    agent.add(spec, FIREBIRD)
    agent.add(VOLUME.from_existing({"volume": "v", "container": "c"}), VOLUME)
    agent.host_gateway = True
    (agent.path / "ca.crt").write_text("pem", encoding="utf-8")
    agent.ca_bundle = "./ca.crt"
    renderer.render_agent(agent).write(agent.path)
    agent.save_state()

    loaded = AgentProject.load(agent.path)
    assert loaded.host_gateway
    assert loaded.ca_bundle == "./ca.crt"
    assert loaded.env.as_dict() == agent.env.as_dict()
    firebird, volume = loaded.databases
    assert firebird.managed
    assert (firebird.id, firebird.host, firebird.host_port) == (
        spec.id,
        spec.host,
        spec.host_port,
    )
    assert (firebird.password, firebird.root_password) == (
        spec.password,
        spec.root_password,
    )
    assert (volume.volume, volume.container) == ("v", "c")


def agent_load_rejects_non_agent_folders(tmp_path):
    with pytest.raises(ConfigError, match="Not a Portabase agent folder"):
        AgentProject.load(tmp_path)
    (tmp_path / ".env").write_text("", encoding="utf-8")
    (tmp_path / "databases.json").write_text("{oops", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON"):
        AgentProject.load(tmp_path)


def agent_load_skips_odd_entries(tmp_path):
    (tmp_path / ".env").write_text("", encoding="utf-8")
    entries = {"databases": ["junk", {"type": "sqlite", "database": "/config/a"}]}
    (tmp_path / "databases.json").write_text(json.dumps(entries), encoding="utf-8")
    assert [database.engine for database in AgentProject.load(tmp_path).databases] == [
        "sqlite"
    ]


def dashboard_load(dashboard, tmp_path):
    dashboard.env.save()
    loaded = DashboardProject.load(dashboard.path)
    assert loaded.env.as_dict() == dashboard.env.as_dict()
    with pytest.raises(ConfigError, match="Not a Portabase dashboard folder"):
        DashboardProject.load(tmp_path)


@pytest.mark.parametrize(
    ("host", "mode"), [(None, "internal"), ("db", "external"), ("pg.example", "custom")]
)
def dashboard_db_mode(dashboard, host, mode):
    if host:
        dashboard.env.set("POSTGRES_HOST", host)
    assert dashboard.db_mode == mode


def dashboard_project_name(dashboard):
    assert dashboard.project_name == "pb"
    dashboard.env.remove("PROJECT_NAME")
    assert dashboard.project_name == dashboard.path.name


def dashboard_settings(dashboard):
    assert dashboard.setting("password_auth") is True
    assert dashboard.setting("api") is False
    assert dashboard.setting("url") == "https://d.example"
    dashboard.set("api", True)
    assert dashboard.env.get("API_ENABLED") == "true"
    dashboard.unset("api")
    assert dashboard.env.get("API_ENABLED") is None


def dashboard_add_providers(dashboard):
    dashboard.add_provider(KEYCLOAK)
    dashboard.add_provider(GITHUB)
    env = dashboard.env.as_dict()
    assert {key: value for key, value in env.items() if key.startswith("AUTH_")} == {
        "AUTH_OIDC_MY_KC_ID": "my-kc",
        "AUTH_OIDC_MY_KC_ISSUER_URL": "https://kc.example",
        "AUTH_OIDC_MY_KC_CLIENT": "c",
        "AUTH_OIDC_MY_KC_SECRET": "s",
        "AUTH_OIDC_MY_KC_PKCE": "true",
        "AUTH_SOCIAL_GITHUB_CLIENT": "gc",
        "AUTH_SOCIAL_GITHUB_SECRET": "gs",
        "AUTH_SOCIAL_GITHUB_TITLE": "GitHub",
    }
    assert dashboard.providers == [
        AuthProvider(
            "oauth", "github", {"client": "gc", "secret": "gs", "title": "GitHub"}
        ),
        AuthProvider(
            "oidc",
            "my-kc",
            {
                "issuer": "https://kc.example",
                "client": "c",
                "secret": "s",
                "pkce": "true",
            },
        ),
    ]


def dashboard_recovers_oidc_id_without_id_variable(dashboard):
    dashboard.env.merge(
        {"AUTH_OIDC_AZURE_AD_CLIENT": "c", "AUTH_OIDC_AZURE_AD_SECRET": "s"}
    )
    assert [provider.id for provider in dashboard.providers] == ["azure-ad"]


def dashboard_add_duplicate_provider(dashboard):
    dashboard.add_provider(GITHUB)
    with pytest.raises(ValidationError, match="already exists"):
        dashboard.add_provider(GITHUB)


def dashboard_remove_provider(dashboard):
    dashboard.add_provider(KEYCLOAK)
    dashboard.add_provider(GITHUB)
    assert dashboard.remove_provider("my-kc").kind == "oidc"
    assert [provider.id for provider in dashboard.providers] == ["github"]
    assert not any(key.startswith("AUTH_OIDC_") for key in dashboard.env.as_dict())
    with pytest.raises(ValidationError, match="No provider named"):
        dashboard.remove_provider("my-kc")


def dashboard_callback_url(dashboard):
    assert (
        dashboard.callback_url("my-kc")
        == "https://d.example/api/auth/sso/callback/my-kc"
    )


def dashboard_defaults_are_valid(dashboard):
    dashboard.validate()


def dashboard_skip_onboarding_needs_an_account(dashboard):
    dashboard.set("skip_onboarding", True)
    dashboard.set("admin_email", "a@b.c")
    with pytest.raises(ValidationError, match="needs an initial account"):
        dashboard.validate()
    dashboard.set("admin_password", "Abcdef1!")
    dashboard.validate()


def dashboard_password_auth_off_needs_a_provider(dashboard):
    dashboard.set("password_auth", False)
    with pytest.raises(ValidationError, match="lock everyone out"):
        dashboard.save_state()
    assert not dashboard.env.exists
    dashboard.add_provider(GITHUB)
    dashboard.save_state()
    assert dashboard.env.exists


@pytest.mark.parametrize("url", ["http://localhost:8887", "http://127.0.0.1"])
def dashboard_providers_need_a_public_url(dashboard, url):
    dashboard.add_provider(GITHUB)
    dashboard.set("url", url)
    with pytest.raises(ValidationError, match="need a public URL"):
        dashboard.validate()
