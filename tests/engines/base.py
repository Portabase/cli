import json
import re

import pytest

from core.specs import DatabaseSpec
from engines import registry
from engines.base import DbEngine, StandardSqlEngine
from services.envfile import EnvFile
from services.project import spec_from_entry

MANAGED = [engine for engine in registry if engine.template is not None]
VARIANTS = [
    pytest.param(engine, auth, id=f"{engine.key}-{'auth' if auth else 'noauth'}")
    for engine in MANAGED
    for auth in ((True, False) if engine.auth_variants else (True,))
]


@pytest.mark.parametrize(("engine", "auth"), VARIANTS)
def generate_is_unique(engine, auth, ports):
    first = engine.generate(auth=auth, ports=ports, answers={})
    second = engine.generate(auth=auth, ports=ports, answers={})
    assert first.id != second.id
    assert first.host != second.host
    assert first.host_port != second.host_port


@pytest.mark.parametrize(("engine", "auth"), VARIANTS)
def env_vars_are_prefixed_strings(engine, auth, ports):
    spec = engine.generate(auth=auth, ports=ports, answers={})
    env = engine.env_vars(spec)
    assert env[f"{spec.env_prefix}_PORT"] == str(spec.host_port)
    assert all(key.startswith(spec.env_prefix + "_") for key in env)
    assert all(isinstance(value, str) for value in env.values())


@pytest.mark.parametrize(("engine", "auth"), VARIANTS)
def template_ctx_points_at_env_vars(engine, auth, ports):
    spec = engine.generate(auth=auth, ports=ports, answers={})
    ctx = engine.template_ctx(spec)
    assert (ctx["name"], ctx["volume"], ctx["auth"]) == (
        spec.host,
        f"{spec.host}-data",
        auth,
    )
    for key in ("port_var", "db_var", "user_var", "password_var"):
        assert re.fullmatch(rf"\$\{{{spec.env_prefix}_[A-Z_]+\}}", ctx[key])


@pytest.mark.parametrize(("engine", "auth"), VARIANTS)
def agent_entry_survives_databases_json(engine, auth, ports, tmp_path):
    spec = engine.generate(auth=auth, ports=ports, answers={})
    entry = json.loads(json.dumps(engine.agent_entry(spec)))
    env = EnvFile(tmp_path / ".env")
    env.merge(engine.env_vars(spec))
    loaded = spec_from_entry(entry, env)
    assert loaded.managed
    assert (loaded.id, loaded.engine, loaded.host, loaded.port, loaded.host_port) == (
        spec.id,
        spec.engine,
        spec.host,
        spec.port,
        spec.host_port,
    )
    assert (loaded.password, loaded.root_password) == (
        spec.password,
        spec.root_password,
    )


def service_name_format():
    assert re.fullmatch(r"db-pg-[0-9a-f]{4}", DbEngine.service_name("pg"))
    assert re.fullmatch(
        r"db-pg-auth-[0-9a-f]{4}", DbEngine.service_name("pg", auth=True)
    )


def var_references_or_escapes():
    spec = DatabaseSpec(id="1", engine="postgresql", name="n", host="db-pg-ab12")
    assert DbEngine.var(spec, "PASS", "x", inline=False) == "${DB_PG_AB12_PASS}"
    assert DbEngine.var(spec, "PASS", 'a"b\\c', inline=True) == 'a\\"b\\\\c'
    assert DbEngine.var(spec, "PASS", None, inline=True) == ""
    assert DbEngine.var(spec, "PORT", 5432, inline=True) == "5432"


def engine_without_required_attributes_is_refused():
    with pytest.raises(TypeError, match="missing required engine attribute"):

        class Broken(StandardSqlEngine):
            key, display = "broken", "Broken"


def abstract_engine_may_be_incomplete():
    class Base(DbEngine):
        abstract = True

    assert Base.abstract


def template_must_live_under_engines():
    with pytest.raises(TypeError, match="must be a path under 'engines/'"):

        class Misplaced(StandardSqlEngine):
            key, display, default_port = "misplaced", "Misplaced", 1
            template, slug, db_prefix = "misplaced.yml.j2", "m", "m"
