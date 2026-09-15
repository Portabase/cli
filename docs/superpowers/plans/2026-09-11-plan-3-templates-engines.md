# Plan 3 — Templates Jinja2 et moteurs DB (chantier D)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduire les templates Jinja2 versionnés (source `templates/` à la racine, manifest, cache, `TemplateRepository`), le registre de moteurs DB en classes, et les garde-fous CI (`render-check`, `engines-check`, manifest à l'upload, hotfix) — sans encore brancher le rendu sur les commandes (Plan 4). Le CLI reste fonctionnel : les commandes legacy continuent de lire `agent.yml` / `dashboard.yml` (conservés dans `templates/` jusqu'au Plan 4).

**Architecture:** `TemplateRepository` résout une version → dossier local (`./templates` en dev, cache `~/.portabase/cache/templates/<version>/` en binaire), vérifie un `manifest.json` (sha256) et expose des `jinja2.Template`. Chaque `DbEngine` déclare ses champs, génère un `DatabaseSpec`, produit ses variables `.env`, son contexte de template et sa projection `databases.json`. `render_check.py` rend chaque template avec des fixtures et valide le YAML puis `docker compose config`.

**Tech Stack:** Jinja2 3.1, PyYAML, Python 3.12, GitHub Actions, s3cmd, jq.

**Spec:** `docs/superpowers/specs/2026-09-11-cli-refactor-design.md` — sections 5.4, 5.6, 6, 6.1, 9.1 (`render-check`, `engines-check`), 9.3 (hotfix, manifest), 10 (D).

## Global Constraints

- Prérequis : Plans 1 et 2 exécutés.
- Règle de dépendance : `engines → core` uniquement. `services → engines, core`. Vérifié par revue ; ruff ne le détecte pas.
- Déviations spec assumées :
  - `DatabaseSpec` vit dans `core/specs.py` (produit par `engines`, consommé par `services`), pas dans `services/project.py`.
  - Pas de `mysql.yml.j2` : le moteur `mysql` utilise `engines/mariadb.yml.j2`, comme le code legacy (image `mariadb:latest`). Changer d'image casserait les volumes des installs existantes.
- Les fichiers legacy `agent.yml` et `dashboard.yml` sont déplacés tels quels dans `templates/` et restent uploadés (le code legacy les fetch sous `<version>/`). Supprimés au Plan 4.
- Conventions de nommage legacy conservées à l'identique (service `db-pg-<hex2>`, `db-mongo-auth-<hex2>`, db `pg_<hex4>`, user `admin`, firebird user `alice` / `mirror.fdb`, mssql `sa` / `master` / name `MSSQL`, redis/valkey `database: "0"`), pour que les nouvelles installs ressemblent aux anciennes.
- `generate_password` retire `$` et `` ` `` des symboles (Task 1).
- Pas de tests unitaires. `render_check.py` est la vérification exécutable de ce plan et devient un job CI.
- Aucune commande utilisateur ne change dans ce plan.

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `core/utils.py` | modifier | `generate_password` sans `$`/`` ` `` |
| `core/specs.py` | créer | `DatabaseSpec` |
| `services/ports.py` | créer | `PortAllocator` |
| `engines/__init__.py` | créer | `registry` |
| `engines/base.py` | créer | `DbEngine` |
| `engines/registry.py` | créer | `EngineRegistry` |
| `engines/sql.py` | créer | `StandardSqlEngine`, `PostgresEngine`, `PostgresClusterEngine`, `MySqlEngine`, `MariaDbEngine`, `MssqlEngine`, `FirebirdEngine` |
| `engines/redis.py` | créer | `RedisEngine` |
| `engines/valkey.py` | créer | `ValkeyEngine` |
| `engines/mongo.py` | créer | `MongoEngine` |
| `engines/sqlite.py` | créer | `SqliteEngine` |
| `engines/docker_volume.py` | créer | `DockerVolumeEngine` |
| `templates/agent.yml.j2`, `dashboard.yml.j2`, `engines/*.yml.j2` | créer | templates Jinja2 |
| `templates/engines.map.json` | créer | clé moteur → template |
| `templates/agent.yml`, `dashboard.yml` | déplacer depuis `.github/assets/templates/` | legacy |
| `services/templates.py` | créer | `Manifest`, `TemplateRepository` |
| `scripts/render_check.py` | créer | validation des templates |
| `.github/workflows/ci.yml` | modifier | jobs `render-check`, `engines-check` |
| `.github/workflows/templates-upload.yml` | modifier | source `templates/`, manifest |
| `.github/workflows/templates-hotfix.yml` | créer | re-upload d'une version |
| `pyproject.toml` | modifier | `jinja2` |
| `.gitleaks.toml` | modifier | chemin `templates/` déjà allowlisté ; retirer `.github/assets/templates` |

---

### Task 1 : `core/specs.py`, `services/ports.py`, mot de passe

**Files:**
- Create: `core/specs.py`
- Create: `services/ports.py`
- Modify: `core/utils.py:70-92` (`generate_password`)

**Interfaces:**
- Produces: `DatabaseSpec` (frozen dataclass) avec `env_prefix`, `is_service`, `with_options()` ; `PortAllocator().free() -> int` ; `generate_password(length=16)` sans `$` ni `` ` ``.

- [ ] **Step 1: `core/specs.py`**

```python
"""Typed view of one databases.json entry plus what the CLI needs to render it."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class DatabaseSpec:
    id: str
    engine: str
    name: str
    managed: bool = False           # True: a Compose service is rendered for it
    host: str | None = None         # service name when managed, remote host otherwise
    port: int | None = None         # container/remote port (what the agent connects to)
    host_port: int | None = None    # published port on the Docker host (managed only)
    database: str | None = None
    username: str | None = None
    password: str | None = None
    root_password: str | None = None  # firebird
    path: str | None = None         # sqlite
    volume: str | None = None       # docker-volume
    container: str | None = None    # docker-volume
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def env_prefix(self) -> str:
        if not self.host:
            raise ValueError("env_prefix requires a host/service name")
        return self.host.upper().replace("-", "_")

    @property
    def auth(self) -> bool:
        return bool(self.password)

    def with_options(self, options: dict[str, Any]) -> DatabaseSpec:
        return replace(self, options=dict(options))
```

- [ ] **Step 2: `services/ports.py`**

```python
"""Free TCP port allocation. Remembers ports handed out during the process to avoid duplicates."""

from __future__ import annotations

import socket


class PortAllocator:
    def __init__(self) -> None:
        self._given: set[int] = set()

    def free(self) -> int:
        for _ in range(50):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", 0))
                port = s.getsockname()[1]
            if port not in self._given:
                self._given.add(port)
                return port
        raise RuntimeError("Could not allocate a free port")


class FixedPortAllocator(PortAllocator):
    """Deterministic ports for render checks and fixtures."""

    def __init__(self, start: int = 40000) -> None:
        super().__init__()
        self._next = start

    def free(self) -> int:
        port = self._next
        self._next += 1
        return port
```

- [ ] **Step 3: Corriger `generate_password` dans `core/utils.py`**

Remplacer la ligne `symbols = "!@#$%^&*()-_=+[]{}|;:,.<>?"` par :

```python
    # No '$' (Compose interpolation / shell), no '`' or quotes (shell command args in templates).
    symbols = "!@#%^&*()-_=+[]{}|;:,.<>?"
```

- [ ] **Step 4: Vérifier**

Run: `uv run python -c "
from core.specs import DatabaseSpec
from services.ports import PortAllocator, FixedPortAllocator
from core.utils import generate_password
s = DatabaseSpec(id='1', engine='postgresql', name='x', managed=True, host='db-pg-a1f2', password='p')
print(s.env_prefix, s.auth, s.with_options({'a':1}).options)
p = PortAllocator(); a, b = p.free(), p.free(); print(a != b, FixedPortAllocator().free())
pw = generate_password(); print(len(pw), '\$' not in pw and '\`' not in pw)"`
Expected: `DB_PG_A1F2 True {'a': 1}`, `True 40000`, `16 True`.

- [ ] **Step 5: Commit**

```bash
git add core/specs.py services/ports.py core/utils.py
git commit -m "feat: add DatabaseSpec, PortAllocator; drop shell-unsafe symbols from generated passwords"
```

---

### Task 2 : `engines/base.py` et `engines/registry.py`

**Files:**
- Create: `engines/__init__.py` (rempli Task 4)
- Create: `engines/base.py`
- Create: `engines/registry.py`

**Interfaces:**
- Produces: `DbEngine` ABC :
  - classe-attributs `key`, `display`, `default_port: int | None`, `template: str | None`, `auth_variants=False`, `warning=None`, `has_modes=True`
  - `fields_existing() -> list[Field]`, `fields_new() -> list[Field]`, `option_fields() -> list[Field]`
  - `generate(*, auth: bool, ports: PortAllocator, answers: dict) -> DatabaseSpec`
  - `from_existing(answers: dict) -> DatabaseSpec`
  - `env_vars(spec) -> dict[str, str]`
  - `template_ctx(spec, *, inline: bool = False) -> dict`
  - `agent_entry(spec) -> dict`
  - `describe(spec) -> str` (pour `db list` : « host:port », « Local File », « volume: x »)
  - helpers `new_id()`, `service_name(slug, auth)`, `var(spec, suffix, value, inline)`
- `EngineRegistry(engines)` : `get(key)`, `keys()`, `choices()`, `__iter__`.

- [ ] **Step 1: `engines/base.py`**

```python
"""DbEngine: everything the CLI needs to know about one database engine."""

from __future__ import annotations

import secrets
import uuid
from abc import ABC, abstractmethod
from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from services.ports import PortAllocator

STANDARD_EXISTING_FIELDS = (
    Field("host", "Host", "text", default="localhost"),
    Field("port", "Port", "int"),  # default filled per engine
    Field("database", "Database Name", "text"),
    Field("username", "Username", "text"),
    Field("password", "Password", "secret"),
)


class DbEngine(ABC):
    key: str
    display: str
    default_port: int | None = None
    template: str | None = None      # e.g. "engines/postgresql.yml.j2"; None: no Compose service
    auth_variants: bool = False      # offer with-auth / no-auth when creating a container
    warning: str | None = None       # shown before collecting answers
    has_modes: bool = True           # new/existing choice applies

    # ---- declarations -----------------------------------------------------

    def fields_existing(self) -> list[Field]:
        return [
            Field("port", "Port", "int", default=self.default_port) if f.name == "port" else f
            for f in STANDARD_EXISTING_FIELDS
        ]

    def fields_new(self) -> list[Field]:
        return []

    def option_fields(self) -> list[Field]:
        return []

    # ---- construction -----------------------------------------------------

    @abstractmethod
    def generate(self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]) -> DatabaseSpec: ...

    def from_existing(self, answers: dict[str, Any]) -> DatabaseSpec:
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=answers.get("label") or "External DB",
            managed=False,
            host=answers["host"],
            port=int(answers["port"]),
            database=answers["database"],
            username=answers["username"],
            password=answers["password"],
        )

    # ---- rendering inputs -------------------------------------------------

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        """Variables written to .env for a managed service. Default: PORT, DB, USER, PASS."""
        p = spec.env_prefix
        return {
            f"{p}_PORT": str(spec.host_port),
            f"{p}_DB": spec.database or "",
            f"{p}_USER": spec.username or "",
            f"{p}_PASS": spec.password or "",
        }

    def template_ctx(self, spec: DatabaseSpec, *, inline: bool = False) -> dict[str, Any]:
        return {
            "name": spec.host,
            "volume": f"{spec.host}-data",
            "auth": spec.auth,
            "port_var": self.var(spec, "PORT", spec.host_port, inline),
            "db_var": self.var(spec, "DB", spec.database, inline),
            "user_var": self.var(spec, "USER", spec.username, inline),
            "password_var": self.var(spec, "PASS", spec.password, inline),
        }

    def agent_entry(self, spec: DatabaseSpec) -> dict[str, Any]:
        """Projection to databases.json. Same shape as the legacy CLI."""
        entry: dict[str, Any] = {
            "name": spec.name,
            "database": self.agent_database(spec),
            "type": self.key,
            "username": spec.username or "",
            "password": spec.password or "",
            "port": spec.port,
            "host": spec.host,
            "generated_id": spec.id,
        }
        options = self.non_default_options(spec)
        if options:
            entry["options"] = options
        return entry

    def agent_database(self, spec: DatabaseSpec) -> str:
        return spec.database or ""

    def describe(self, spec: DatabaseSpec) -> str:
        return f"{spec.host}:{spec.port}"

    # ---- helpers ----------------------------------------------------------

    def non_default_options(self, spec: DatabaseSpec) -> dict[str, Any]:
        defaults = {f.name: f.default for f in self.option_fields()}
        return {k: v for k, v in spec.options.items() if k in defaults and v != defaults[k]}

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def service_name(slug: str, auth: bool = False) -> str:
        suffix = "auth-" if auth else ""
        return f"db-{slug}-{suffix}{secrets.token_hex(2)}"

    @staticmethod
    def var(spec: DatabaseSpec, suffix: str, value: Any, inline: bool) -> str:
        return str(value if value is not None else "") if inline else f"${{{spec.env_prefix}_{suffix}}}"
```

- [ ] **Step 2: `engines/registry.py`**

```python
from __future__ import annotations

from collections.abc import Iterable, Iterator

from core.errors import ValidationError
from engines.base import DbEngine


class EngineRegistry:
    def __init__(self, engines: Iterable[DbEngine]) -> None:
        self._by_key: dict[str, DbEngine] = {}
        for engine in engines:
            if engine.key in self._by_key:
                raise ValueError(f"Duplicate engine key: {engine.key}")
            self._by_key[engine.key] = engine

    def get(self, key: str) -> DbEngine:
        try:
            return self._by_key[key]
        except KeyError:
            raise ValidationError(
                f"Unknown engine '{key}'.",
                hint="Available: " + ", ".join(self.keys()),
            ) from None

    def keys(self) -> list[str]:
        return list(self._by_key)

    def choices(self) -> list[str]:
        return self.keys()

    def __iter__(self) -> Iterator[DbEngine]:
        return iter(self._by_key.values())

    def __contains__(self, key: str) -> bool:
        return key in self._by_key
```

- [ ] **Step 3: Vérifier**

Run: `uv run python -c "
from engines.base import DbEngine
from engines.registry import EngineRegistry
from core.errors import ValidationError
print([f.name for f in DbEngine.fields_existing(type('E',(DbEngine,),{'key':'x','display':'X','default_port':1,'generate':lambda *a,**k: None})())])
try: EngineRegistry([]).get('nope')
except ValidationError as e: print(e.message, '|', e.hint)"`
Expected: `['host', 'port', 'database', 'username', 'password']` puis `Unknown engine 'nope'. | Available: `.

- [ ] **Step 4: Commit**

```bash
git add engines/
git commit -m "feat(engines): add DbEngine base class and EngineRegistry"
```

---

### Task 3 : Moteurs SQL (`engines/sql.py`)

**Files:**
- Create: `engines/sql.py`

**Interfaces:**
- Produces: `StandardSqlEngine` et sous-classes `PostgresEngine` (`postgresql`), `PostgresClusterEngine` (`postgresql-cluster`), `MySqlEngine` (`mysql`), `MariaDbEngine` (`mariadb`), `MssqlEngine` (`mssql`), `FirebirdEngine` (`firebird`).

- [ ] **Step 1: Écrire le module**

```python
"""SQL engines rendered as Compose services. Naming mirrors the legacy CLI."""

from __future__ import annotations

import secrets
from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from core.utils import generate_password
from engines.base import DbEngine
from services.ports import PortAllocator


class StandardSqlEngine(DbEngine):
    slug: str            # service name fragment: db-<slug>-xxxx
    db_prefix: str       # generated database name: <db_prefix>_xxxxxxxx
    default_user = "admin"

    def generate(self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]) -> DatabaseSpec:
        db_name = f"{self.db_prefix}_{secrets.token_hex(4)}"
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=db_name,
            managed=True,
            host=self.service_name(self.slug),
            port=self.default_port,
            host_port=ports.free(),
            database=db_name,
            username=self.default_user,
            password=generate_password(16),
            options=dict(answers.get("options", {})),
        )


class PostgresEngine(StandardSqlEngine):
    key, display, default_port = "postgresql", "PostgreSQL", 5432
    template, slug, db_prefix = "engines/postgresql.yml.j2", "pg", "pg"

    def option_fields(self) -> list[Field]:
        return [
            Field(
                "keep_ownership",
                "Keep ownership?",
                "bool",
                default=False,
                help=(
                    "When enabled, omits --no-owner and --no-privileges from the dump. Ownership and role "
                    "assignments are preserved. By default these flags are applied to keep restores portable "
                    "across users and environments."
                ),
            ),
            Field(
                "clean_mode",
                "Clean mode",
                "choice",
                default="clean",
                choices=("clean", "none", "drop_schemas", "drop_database"),
                help=(
                    "How the target database is cleaned before a restore. clean: pg_restore --clean --if-exists. "
                    "none: no pre-clean. drop_schemas: drop every non-system schema CASCADE (works on managed "
                    "Postgres). drop_database: DROP DATABASE + CREATE DATABASE — requires CREATEDB or superuser; "
                    "most managed providers do not allow it."
                ),
            ),
        ]


class PostgresClusterEngine(StandardSqlEngine):
    key, display, default_port = "postgresql-cluster", "PostgreSQL Cluster", 5432
    template, slug, db_prefix = "engines/postgresql.yml.j2", "pg", "pg"
    warning = (
        "Postgres Cluster requires a superuser. Cluster backup/restore uses pg_dumpall, which dumps all "
        "databases and global objects (roles, tablespaces). The provided user must be a Postgres superuser."
    )


class MariaDbEngine(StandardSqlEngine):
    key, display, default_port = "mariadb", "MariaDB", 3306
    template, slug, db_prefix = "engines/mariadb.yml.j2", "mariadb", "mysql"


class MySqlEngine(MariaDbEngine):
    """Legacy behaviour: a 'mysql' container is a MariaDB image. Kept for volume compatibility."""

    key, display = "mysql", "MySQL"


class MssqlEngine(StandardSqlEngine):
    key, display, default_port = "mssql", "Microsoft SQL Server", 1433
    template, slug, db_prefix = "engines/mssql.yml.j2", "mssql", "master"

    def generate(self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]) -> DatabaseSpec:
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name="MSSQL",
            managed=True,
            host=self.service_name(self.slug),
            port=self.default_port,
            host_port=ports.free(),
            database="master",
            username="sa",
            password=generate_password(16),
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        p = spec.env_prefix
        return {f"{p}_PORT": str(spec.host_port), f"{p}_PASS": spec.password or ""}


class FirebirdEngine(StandardSqlEngine):
    key, display, default_port = "firebird", "Firebird", 3050
    template, slug, db_prefix = "engines/firebird.yml.j2", "firebird", "fb"
    DATA_DIR = "/var/lib/firebird/data"

    def generate(self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]) -> DatabaseSpec:
        db_file = "mirror.fdb"
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=db_file,
            managed=True,
            host=self.service_name(self.slug),
            port=self.default_port,
            host_port=ports.free(),
            database=f"{self.DATA_DIR}/{db_file}",
            username="alice",
            password=generate_password(16),
            root_password=generate_password(16),
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        base = super().env_vars(spec)
        # Compose template expects the bare file name; databases.json carries the container path.
        base[f"{spec.env_prefix}_DB"] = (spec.database or "").rsplit("/", 1)[-1]
        base[f"{spec.env_prefix}_ROOT_PASS"] = spec.root_password or ""
        return base

    def template_ctx(self, spec: DatabaseSpec, *, inline: bool = False) -> dict[str, Any]:
        ctx = super().template_ctx(spec, inline=inline)
        ctx["db_var"] = self.var(spec, "DB", (spec.database or "").rsplit("/", 1)[-1], inline)
        ctx["root_password_var"] = self.var(spec, "ROOT_PASS", spec.root_password, inline)
        return ctx
```

- [ ] **Step 2: Vérifier**

Run: `uv run python -c "
from engines.sql import *
from services.ports import FixedPortAllocator
p = FixedPortAllocator()
for E in (PostgresEngine, MySqlEngine, MssqlEngine, FirebirdEngine):
    e = E(); s = e.generate(auth=True, ports=p, answers={'options': {'clean_mode': 'none'}})
    print(E.key, s.host[:9], sorted(e.env_vars(s)), e.agent_entry(s).get('options'), e.template_ctx(s)['port_var'])
print(PostgresEngine().agent_entry(PostgresEngine().generate(auth=True, ports=p, answers={})).get('options'))"`
Expected (hex variable) :
```
postgresql db-pg-xxx ['DB_PG_XXXX_DB', 'DB_PG_XXXX_PASS', 'DB_PG_XXXX_PORT', 'DB_PG_XXXX_USER'] {'clean_mode': 'none'} ${DB_PG_XXXX_PORT}
mysql db-mariad [... 4 vars] None ...
mssql db-mssql- [..._PASS, ..._PORT] None ...
firebird db-fireb [..._DB, ..._PASS, ..._PORT, ..._ROOT_PASS, ..._USER] None ...
None
```
La dernière ligne : options par défaut → pas de clé `options`.

- [ ] **Step 3: Commit**

```bash
git add engines/sql.py
git commit -m "feat(engines): add SQL engines (postgresql, cluster, mysql, mariadb, mssql, firebird)"
```

---

### Task 4 : Redis, Valkey, Mongo, SQLite, Docker volume, registre

**Files:**
- Create: `engines/redis.py`, `engines/valkey.py`, `engines/mongo.py`, `engines/sqlite.py`, `engines/docker_volume.py`
- Modify: `engines/__init__.py`

**Interfaces:**
- Produces: `RedisEngine`, `ValkeyEngine`, `MongoEngine`, `SqliteEngine`, `DockerVolumeEngine` ; `engines.registry: EngineRegistry` (instance module-level) ; `engines.ALL: tuple[DbEngine, ...]`.

- [ ] **Step 1: `engines/redis.py`**

```python
from __future__ import annotations

import secrets
from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from core.utils import generate_password
from engines.base import DbEngine
from services.ports import PortAllocator


class RedisEngine(DbEngine):
    key, display, default_port = "redis", "Redis", 6379
    template = "engines/redis.yml.j2"
    auth_variants = True

    def fields_existing(self) -> list[Field]:
        return [
            Field("host", "Host", "text", default="localhost"),
            Field("port", "Port", "int", default=self.default_port),
            Field("database", "Database index", "text", default="0"),
            Field("username", "Username (empty if none)", "text", default=""),
            Field("password", "Password (empty if none)", "text", default=""),
        ]

    def generate(self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]) -> DatabaseSpec:
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=f"redis_{secrets.token_hex(4)}",
            managed=True,
            host=self.service_name("redis", auth),
            port=self.default_port,
            host_port=ports.free(),
            database="0",
            username="",
            password=generate_password(16) if auth else None,
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        p = spec.env_prefix
        out = {f"{p}_PORT": str(spec.host_port)}
        if spec.auth:
            out[f"{p}_PASS"] = spec.password or ""
        return out

    def agent_database(self, spec: DatabaseSpec) -> str:
        return spec.database or "0"
```

- [ ] **Step 2: `engines/valkey.py`**

Identique à Redis sauf identité et template :

```python
from __future__ import annotations

import secrets
from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from core.utils import generate_password
from engines.base import DbEngine
from services.ports import PortAllocator


class ValkeyEngine(DbEngine):
    key, display, default_port = "valkey", "Valkey", 6379
    template = "engines/valkey.yml.j2"
    auth_variants = True

    def fields_existing(self) -> list[Field]:
        return [
            Field("host", "Host", "text", default="localhost"),
            Field("port", "Port", "int", default=self.default_port),
            Field("database", "Database index", "text", default="0"),
            Field("username", "Username (empty if none)", "text", default=""),
            Field("password", "Password (empty if none)", "text", default=""),
        ]

    def generate(self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]) -> DatabaseSpec:
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=f"valkey_{secrets.token_hex(4)}",
            managed=True,
            host=self.service_name("valkey", auth),
            port=self.default_port,
            host_port=ports.free(),
            database="0",
            username="",
            password=generate_password(16) if auth else None,
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        p = spec.env_prefix
        out = {f"{p}_PORT": str(spec.host_port)}
        if spec.auth:
            out[f"{p}_PASS"] = spec.password or ""
        return out

    def agent_database(self, spec: DatabaseSpec) -> str:
        return spec.database or "0"
```

- [ ] **Step 3: `engines/mongo.py`**

```python
from __future__ import annotations

import secrets
from typing import Any

from core.specs import DatabaseSpec
from core.utils import generate_password
from engines.base import DbEngine
from services.ports import PortAllocator


class MongoEngine(DbEngine):
    key, display, default_port = "mongodb", "MongoDB", 27017
    template = "engines/mongodb.yml.j2"
    auth_variants = True

    def generate(self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]) -> DatabaseSpec:
        db_name = f"mongo_{secrets.token_hex(4)}"
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=db_name,
            managed=True,
            host=self.service_name("mongo", auth),
            port=self.default_port,
            host_port=ports.free(),
            database=db_name,
            username="admin" if auth else "",
            password=generate_password(16) if auth else None,
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        p = spec.env_prefix
        out = {f"{p}_PORT": str(spec.host_port), f"{p}_DB": spec.database or ""}
        if spec.auth:
            out[f"{p}_USER"] = spec.username or ""
            out[f"{p}_PASS"] = spec.password or ""
        return out
```

- [ ] **Step 4: `engines/sqlite.py`**

```python
"""SQLite: a file mounted into the agent. No Compose service."""

from __future__ import annotations

from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from engines.base import DbEngine
from services.ports import PortAllocator

CONFIG_DIR = "/config"


class SqliteEngine(DbEngine):
    key, display = "sqlite", "SQLite"
    template = None
    auth_variants = False

    def fields_existing(self) -> list[Field]:
        return [Field("path", "Database Path (relative or absolute)", "text")]

    def fields_new(self) -> list[Field]:
        return [Field("name", "Database Name", "text", default="local")]

    def generate(self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]) -> DatabaseSpec:
        name = str(answers.get("name") or "local")
        if not name.endswith(".sqlite"):
            name += ".sqlite"
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=name,
            managed=False,
            path=name,                                # relative: ./name mounted to /config/name
            database=f"{CONFIG_DIR}/{name}",
        )

    def from_existing(self, answers: dict[str, Any]) -> DatabaseSpec:
        raw = str(answers["path"])
        absolute = raw.startswith("/")
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=answers.get("label") or "External DB",
            managed=False,
            path=raw,
            database=raw if absolute else f"{CONFIG_DIR}/{raw}",
        )

    @staticmethod
    def mount_for(spec: DatabaseSpec) -> tuple[str, str] | None:
        """(host_path, container_path) if the file must be bind-mounted into the agent."""
        if spec.database and spec.database.startswith(f"{CONFIG_DIR}/"):
            rel = spec.database[len(CONFIG_DIR) + 1 :]
            return (f"./{rel}", spec.database)
        return None

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        return {}

    def agent_entry(self, spec: DatabaseSpec) -> dict[str, Any]:
        return {"name": spec.name, "database": spec.database, "type": self.key, "generated_id": spec.id}

    def describe(self, spec: DatabaseSpec) -> str:
        return "Local File"
```

- [ ] **Step 5: `engines/docker_volume.py`**

```python
"""Docker volume backup target. Requires the Docker socket on the agent. No Compose service."""

from __future__ import annotations

from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from engines.base import DbEngine
from services.ports import PortAllocator


class DockerVolumeEngine(DbEngine):
    key, display = "docker-volume", "Docker Volume"
    template = None
    has_modes = False
    warning = "Requires the Docker socket. It will be mounted on the agent (/var/run/docker.sock)."

    def fields_existing(self) -> list[Field]:
        return [
            Field("volume", "Volume Name (e.g. databases_sqlite-data)", "text"),
            Field("container", "Container Name (optional, enables auto-restart after restore)", "text", default=""),
        ]

    def fields_new(self) -> list[Field]:
        return self.fields_existing()

    def generate(self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]) -> DatabaseSpec:
        return self.from_existing(answers)

    def from_existing(self, answers: dict[str, Any]) -> DatabaseSpec:
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=answers.get("label") or "Docker Volume",
            managed=False,
            volume=str(answers["volume"]).strip(),
            container=(str(answers.get("container") or "").strip() or None),
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        return {}

    def agent_entry(self, spec: DatabaseSpec) -> dict[str, Any]:
        entry = {"name": spec.name, "type": self.key, "volume_name": spec.volume, "generated_id": spec.id}
        if spec.container:
            entry["container_name"] = spec.container
        return entry

    def describe(self, spec: DatabaseSpec) -> str:
        return f"volume: {spec.volume}"
```

- [ ] **Step 6: `engines/__init__.py`**

```python
"""Engine registry. Explicit imports keep PyInstaller happy (no dynamic discovery)."""

from __future__ import annotations

from engines.docker_volume import DockerVolumeEngine
from engines.mongo import MongoEngine
from engines.redis import RedisEngine
from engines.registry import EngineRegistry
from engines.sql import (
    FirebirdEngine,
    MariaDbEngine,
    MssqlEngine,
    MySqlEngine,
    PostgresClusterEngine,
    PostgresEngine,
)
from engines.sqlite import SqliteEngine
from engines.valkey import ValkeyEngine

ALL = (
    PostgresEngine(),
    PostgresClusterEngine(),
    MySqlEngine(),
    MariaDbEngine(),
    SqliteEngine(),
    FirebirdEngine(),
    MongoEngine(),
    RedisEngine(),
    ValkeyEngine(),
    MssqlEngine(),
    DockerVolumeEngine(),
)

registry = EngineRegistry(ALL)

__all__ = ["ALL", "EngineRegistry", "registry"]
```

L'ordre = ordre d'affichage dans le select (identique au legacy).

- [ ] **Step 7: Vérifier**

Run: `uv run python -c "
from engines import registry
from services.ports import FixedPortAllocator
p = FixedPortAllocator()
print(registry.keys())
for e in registry:
    if e.template is None: continue
    for auth in ((True, False) if e.auth_variants else (True,)):
        s = e.generate(auth=auth, ports=p, answers={})
        ctx = e.template_ctx(s); assert ctx['name'] == s.host and set(e.env_vars(s)) >= {s.env_prefix + '_PORT'}
        print(f'{e.key:20} auth={auth!s:5} {s.host:24} env={len(e.env_vars(s))} entry.db={e.agent_entry(s)[\"database\"]!r}')
sq = registry.get('sqlite'); s = sq.generate(auth=False, ports=p, answers={'name':'x'}); print(sq.agent_entry(s), sq.mount_for(s))
dv = registry.get('docker-volume'); print(dv.agent_entry(dv.from_existing({'volume':'v','container':''})))"`
Expected: 11 clés dans l'ordre legacy ; une ligne par moteur/variante avec `entry.db` = `'0'` pour redis/valkey, `'master'` mssql, `/var/lib/firebird/data/mirror.fdb` firebird ; sqlite `{'name': 'x.sqlite', 'database': '/config/x.sqlite', 'type': 'sqlite', 'generated_id': ...} ('./x.sqlite', '/config/x.sqlite')` ; docker-volume sans `container_name`.

- [ ] **Step 8: Commit**

```bash
git add engines/
git commit -m "feat(engines): add redis, valkey, mongodb, sqlite, docker-volume engines and registry"
```

---

### Task 5 : Templates Jinja2

**Files:**
- Create: `templates/agent.yml.j2`, `templates/dashboard.yml.j2`
- Create: `templates/engines/postgresql.yml.j2`, `mariadb.yml.j2`, `mssql.yml.j2`, `firebird.yml.j2`, `mongodb.yml.j2`, `redis.yml.j2`, `valkey.yml.j2`
- Create: `templates/engines.map.json`
- Move: `.github/assets/templates/agent.yml` → `templates/agent.yml`, `dashboard.yml` → `templates/dashboard.yml`
- Modify: `pyproject.toml` (`jinja2`), `.gitleaks.toml`

**Interfaces:**
- Produces: contrat de contexte.
  - `agent.yml.j2` : `host_gateway: bool`, `docker_socket: bool`, `mounts: list[{host, container}]`, `services: list[{name, volume, body}]`, `tz_var, edge_key_var, log_level_var, polling_var: str`.
  - `dashboard.yml.j2` : `db_mode: "external"|"internal"|"custom"`, `project_name_var, host_port_var, tz_var, log_level_var, project_secret_var, project_url_var, pg_port_var, postgres_db_var, postgres_user_var, postgres_password_var: str`.
  - `engines/*.yml.j2` : `name, volume, auth, port_var, db_var, user_var, password_var` (+ `root_password_var` firebird).

- [ ] **Step 1: Ajouter Jinja2**

Run: `uv add "jinja2>=3.1"`
Expected: `pyproject.toml` et `uv.lock` mis à jour.

- [ ] **Step 2: Déplacer les templates legacy**

Run: `mkdir -p templates/engines && git mv .github/assets/templates/agent.yml templates/agent.yml && git mv .github/assets/templates/dashboard.yml templates/dashboard.yml && rmdir .github/assets/templates 2>/dev/null; ls templates`

- [ ] **Step 3: `templates/agent.yml.j2`**

```jinja
services:
  agent:
    restart: unless-stopped
    image: portabase/agent:latest
    volumes:
      - ./databases.json:/config/config.json
{%- for m in mounts %}
      - {{ m.host }}:{{ m.container }}
{%- endfor %}
{%- if docker_socket %}
      - /var/run/docker.sock:/var/run/docker.sock
{%- endif %}
{%- if host_gateway %}
    extra_hosts:
      - "localhost:host-gateway"
{%- endif %}
    environment:
      TZ: "{{ tz_var }}"
      EDGE_KEY: "{{ edge_key_var }}"
      LOG_LEVEL: "{{ log_level_var }}"
      POLLING: "{{ polling_var }}"
    networks:
      - portabase
{% for s in services %}
{{ s.body }}
{%- endfor %}
{% if services %}
volumes:
{%- for s in services %}
  {{ s.volume }}:
{%- endfor %}
{% endif %}
networks:
  portabase:
    name: portabase_network
    external: true
```

- [ ] **Step 4: `templates/dashboard.yml.j2`**

```jinja
name: {{ project_name_var }}
services:
  portabase:
    container_name: {{ project_name_var }}-app
    image: portabase/portabase:latest
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - "{{ host_port_var }}:80"
    environment:
      - TZ={{ tz_var }}
      - LOG_LEVEL={{ log_level_var }}
      - PROJECT_SECRET={{ project_secret_var }}
      - PROJECT_URL={{ project_url_var }}
    volumes:
      - portabase-data:/data
{%- if db_mode == "external" %}
    depends_on:
      db:
        condition: service_healthy
{%- endif %}
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 60s
{%- if db_mode == "external" %}
  db:
    container_name: {{ project_name_var }}-pg
    image: postgres:17-alpine
    restart: unless-stopped
    ports:
      - "{{ pg_port_var }}:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB={{ postgres_db_var }}
      - POSTGRES_USER={{ postgres_user_var }}
      - POSTGRES_PASSWORD={{ postgres_password_var }}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U {{ postgres_user_var }} -d {{ postgres_db_var }}"]
      interval: 10s
      timeout: 5s
      retries: 5
{%- endif %}
volumes:
{%- if db_mode == "external" %}
  postgres-data:
{%- endif %}
  portabase-data:
```

- [ ] **Step 5: Templates moteurs**

`templates/engines/postgresql.yml.j2` :

```jinja
  {{ name }}:
    image: postgres:17-alpine
    restart: unless-stopped
    networks:
      - portabase
    ports:
      - "{{ port_var }}:5432"
    volumes:
      - {{ volume }}:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB={{ db_var }}
      - POSTGRES_USER={{ user_var }}
      - POSTGRES_PASSWORD={{ password_var }}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U {{ user_var }} -d {{ db_var }}"]
      interval: 10s
      timeout: 5s
      retries: 5
```

`templates/engines/mariadb.yml.j2` :

```jinja
  {{ name }}:
    image: mariadb:latest
    restart: unless-stopped
    networks:
      - portabase
    ports:
      - "{{ port_var }}:3306"
    environment:
      - MYSQL_DATABASE={{ db_var }}
      - MYSQL_USER={{ user_var }}
      - MYSQL_PASSWORD={{ password_var }}
      - MYSQL_RANDOM_ROOT_PASSWORD=yes
    volumes:
      - {{ volume }}:/var/lib/mysql
    healthcheck:
      test: ["CMD-SHELL", "mariadb-admin ping -h localhost -u {{ user_var }} -p{{ password_var }}"]
      interval: 10s
      timeout: 5s
      retries: 5
```

`templates/engines/mssql.yml.j2` :

```jinja
  {{ name }}:
    image: mcr.microsoft.com/azure-sql-edge:latest
    restart: unless-stopped
    networks:
      - portabase
    ports:
      - "{{ port_var }}:1433"
    environment:
      - ACCEPT_EULA=Y
      - MSSQL_SA_PASSWORD={{ password_var }}
    volumes:
      - {{ volume }}:/var/opt/mssql
    healthcheck:
      test: ["CMD-SHELL", "cat /proc/net/tcp6 | grep -q '059901' || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 20
```

`templates/engines/firebird.yml.j2` :

```jinja
  {{ name }}:
    image: firebirdsql/firebird
    restart: unless-stopped
    networks:
      - portabase
    ports:
      - "{{ port_var }}:3050"
    volumes:
      - {{ volume }}:/var/lib/firebird/data
    environment:
      - FIREBIRD_DATABASE={{ db_var }}
      - FIREBIRD_USER={{ user_var }}
      - FIREBIRD_PASSWORD={{ password_var }}
      - FIREBIRD_ROOT_PASSWORD={{ root_password_var }}
      - FIREBIRD_DATABASE_DEFAULT_CHARSET=UTF8
    healthcheck:
      test: ["CMD-SHELL", "nc -z localhost 3050"]
      interval: 10s
      timeout: 5s
      retries: 5
```

`templates/engines/mongodb.yml.j2` :

```jinja
  {{ name }}:
    image: mongo:latest
    restart: unless-stopped
    networks:
      - portabase
    ports:
      - "{{ port_var }}:27017"
    environment:
{%- if auth %}
      - MONGO_INITDB_ROOT_USERNAME={{ user_var }}
      - MONGO_INITDB_ROOT_PASSWORD={{ password_var }}
{%- endif %}
      - MONGO_INITDB_DATABASE={{ db_var }}
{%- if auth %}
    command: mongod --auth
{%- endif %}
    volumes:
      - {{ volume }}:/data/db
    healthcheck:
      test: ["CMD-SHELL", "mongosh --eval 'db.runCommand({ping:1})' --quiet"]
      interval: 10s
      timeout: 5s
      retries: 5
```

`templates/engines/redis.yml.j2` :

```jinja
  {{ name }}:
    image: redis:latest
    restart: unless-stopped
    ports:
      - "{{ port_var }}:6379"
    volumes:
      - {{ volume }}:/data
{%- if auth %}
    environment:
      - REDIS_PASSWORD={{ password_var }}
    command: ["redis-server", "--requirepass", "{{ password_var }}", "--appendonly", "yes"]
{%- else %}
    command: ["redis-server", "--appendonly", "yes"]
{%- endif %}
    networks:
      - portabase
      - default
    healthcheck:
      test: ["CMD-SHELL", "redis-cli {% if auth %}-a {{ password_var }} {% endif %}ping | grep PONG"]
      interval: 10s
      timeout: 5s
      retries: 5
```

`templates/engines/valkey.yml.j2` :

```jinja
  {{ name }}:
    image: valkey/valkey:latest
    restart: unless-stopped
{%- if auth %}
    command: --requirepass "{{ password_var }}"
{%- else %}
    environment:
      - ALLOW_EMPTY_PASSWORD=yes
{%- endif %}
    ports:
      - "{{ port_var }}:6379"
    volumes:
      - {{ volume }}:/data
    networks:
      - portabase
      - default
    healthcheck:
      test: ["CMD-SHELL", "valkey-cli {% if auth %}-a {{ password_var }} {% endif %}ping | grep PONG"]
      interval: 10s
      timeout: 5s
      retries: 5
```

Différence assumée vs snippets legacy : `restart: unless-stopped` ajouté sur redis et valkey (spec §5.7).

- [ ] **Step 6: `templates/engines.map.json`**

```json
{
  "postgresql": "engines/postgresql.yml.j2",
  "postgresql-cluster": "engines/postgresql.yml.j2",
  "mysql": "engines/mariadb.yml.j2",
  "mariadb": "engines/mariadb.yml.j2",
  "mssql": "engines/mssql.yml.j2",
  "firebird": "engines/firebird.yml.j2",
  "mongodb": "engines/mongodb.yml.j2",
  "redis": "engines/redis.yml.j2",
  "valkey": "engines/valkey.yml.j2"
}
```

- [ ] **Step 7: `.gitleaks.toml`**

Retirer la ligne `'''\.github/assets/templates/.*''',` de `paths`.

- [ ] **Step 8: Rendu manuel de contrôle**

Run: `uv run python -c "
import jinja2, yaml
env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'), undefined=jinja2.StrictUndefined, keep_trailing_newline=True, autoescape=False)
body = env.get_template('engines/redis.yml.j2').render(name='db-redis-auth-ab12', volume='db-redis-auth-ab12-data', auth=True, port_var='\${DB_REDIS_AUTH_AB12_PORT}', db_var='', user_var='', password_var='\${DB_REDIS_AUTH_AB12_PASS}')
out = env.get_template('agent.yml.j2').render(host_gateway=True, docker_socket=True, mounts=[{'host':'./x.sqlite','container':'/config/x.sqlite'}], services=[{'name':'db-redis-auth-ab12','volume':'db-redis-auth-ab12-data','body':body}], tz_var='\${TZ}', edge_key_var='\${EDGE_KEY}', log_level_var='\${LOG_LEVEL}', polling_var='\${POLLING}')
print(out); d = yaml.safe_load(out); print(sorted(d['services']), d['volumes'], d['services']['agent']['extra_hosts'])
for mode in ('external','internal','custom'):
    o = env.get_template('dashboard.yml.j2').render(db_mode=mode, project_name_var='pb', host_port_var='8887', tz_var='\${TZ}', log_level_var='\${LOG_LEVEL}', project_secret_var='\${PROJECT_SECRET}', project_url_var='\${PROJECT_URL}', pg_port_var='\${PG_PORT}', postgres_db_var='\${POSTGRES_DB}', postgres_user_var='\${POSTGRES_USER}', postgres_password_var='\${POSTGRES_PASSWORD}')
    print(mode, sorted(yaml.safe_load(o)['services']), sorted(yaml.safe_load(o)['volumes']))"`
Expected: compose agent imprimé avec socket, extra_hosts, mount sqlite, service redis ; `['agent', 'db-redis-auth-ab12'] {'db-redis-auth-ab12-data': None} ['localhost:host-gateway']` ; dashboard `external ['db', 'portabase'] ['portabase-data', 'postgres-data']`, `internal ['portabase'] ['portabase-data']`, `custom ['portabase'] ['portabase-data']`.

- [ ] **Step 9: Commit**

```bash
git add templates/ pyproject.toml uv.lock .gitleaks.toml
git commit -m "feat(templates): add Jinja2 compose templates at repo root, move legacy templates"
```

---

### Task 6 : `services/templates.py` — `Manifest`, `TemplateRepository`

**Files:**
- Create: `services/templates.py`

**Interfaces:**
- Consumes: `HttpClient`, `GlobalConfig.cache_dir`, `core.version`, `TemplateError`.
- Produces:
  - `Manifest(schema, version, files: dict[str, FileEntry], engines: dict[str, str], generated_at, commit)` avec `from_json(data)`, `from_directory(dir, version)`.
  - `TemplateRepository(http, cache_dir, version, base_url=TEMPLATE_BASE_URL, local_dir: Path | None = None)` : `resolve() -> Path` (dossier prêt, fetch si besoin), `get(name) -> jinja2.Template`, `engine_template(key) -> jinja2.Template`, `manifest -> Manifest`, propriété `source: str` (`local` / `cache` / `remote`).
  - `TemplateRepository.from_environment(http, config) -> TemplateRepository` : lit `PORTABASE_TEMPLATES_DIR`, `PORTABASE_TEMPLATES_VERSION`, détection dev (`./templates` à côté de `main.py` si non frozen).
  - `TEMPLATE_BASE_URL` importée depuis `core/config.py` (inchangée).

- [ ] **Step 1: Écrire le module**

```python
"""Versioned remote templates with manifest verification and a local cache.

Resolution order: explicit local dir (dev) → cache hit → remote fetch. No 'latest' fallback:
a CLI version only ever renders with the templates published for that exact version.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import jinja2

from core.config import TEMPLATE_BASE_URL, GlobalConfig
from core.errors import NetworkError, TemplateError
from core.version import UNKNOWN, current_version
from services.http import HttpClient

MANIFEST_NAME = "manifest.json"
SUPPORTED_SCHEMA = 1


@dataclass(frozen=True)
class FileEntry:
    sha256: str
    size: int


@dataclass(frozen=True)
class Manifest:
    schema: int
    version: str
    files: dict[str, FileEntry]
    engines: dict[str, str]
    generated_at: str = ""
    commit: str = ""

    @classmethod
    def from_json(cls, data: dict) -> Manifest:
        try:
            schema = int(data["schema"])
            if schema != SUPPORTED_SCHEMA:
                raise TemplateError(
                    f"Unsupported template manifest schema {schema} (this CLI supports {SUPPORTED_SCHEMA}).",
                    hint="Update the CLI: portabase update",
                )
            files = {
                name: FileEntry(sha256=str(e["sha256"]).lower(), size=int(e["size"]))
                for name, e in data["files"].items()
            }
            return cls(
                schema=schema,
                version=str(data["version"]),
                files=files,
                engines=dict(data.get("engines", {})),
                generated_at=str(data.get("generated_at", "")),
                commit=str(data.get("commit", "")),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise TemplateError("Template manifest is malformed.", cause=e) from e

    @classmethod
    def from_directory(cls, directory: Path, version: str) -> Manifest:
        """Manifest computed from a local directory (dev mode / render checks)."""
        files = {}
        for path in sorted(directory.rglob("*.j2")):
            rel = path.relative_to(directory).as_posix()
            files[rel] = FileEntry(sha256=_sha256(path), size=path.stat().st_size)
        engines_map = directory / "engines.map.json"
        engines = json.loads(engines_map.read_text(encoding="utf-8")) if engines_map.exists() else {}
        return cls(schema=SUPPORTED_SCHEMA, version=version, files=files, engines=engines)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class TemplateRepository:
    def __init__(
        self,
        http: HttpClient,
        cache_dir: Path,
        version: str,
        *,
        base_url: str = TEMPLATE_BASE_URL,
        local_dir: Path | None = None,
    ) -> None:
        self.http = http
        self.version = version
        self.base_url = base_url.rstrip("/")
        self.local_dir = local_dir
        self.cache_dir = cache_dir / "templates" / version
        self._manifest: Manifest | None = None
        self._env: jinja2.Environment | None = None
        self.source = "unresolved"

    # ---- construction -----------------------------------------------------

    @classmethod
    def from_environment(cls, http: HttpClient, config: GlobalConfig) -> TemplateRepository:
        version = os.environ.get("PORTABASE_TEMPLATES_VERSION") or current_version()
        local = os.environ.get("PORTABASE_TEMPLATES_DIR")
        local_dir = Path(local) if local else None
        if local_dir is None and not getattr(sys, "frozen", False):
            candidate = Path(__file__).resolve().parent.parent / "templates"
            if (candidate / "agent.yml.j2").exists():
                local_dir = candidate
        return cls(http, config.cache_dir, version, local_dir=local_dir)

    # ---- resolution -------------------------------------------------------

    @property
    def manifest(self) -> Manifest:
        if self._manifest is None:
            self.resolve()
        assert self._manifest is not None
        return self._manifest

    def resolve(self) -> Path:
        """Ensure a verified template directory exists locally and return it."""
        if self.local_dir is not None:
            if not (self.local_dir / "agent.yml.j2").exists():
                raise TemplateError(f"Template directory {self.local_dir} has no agent.yml.j2.")
            self._manifest = Manifest.from_directory(self.local_dir, self.version)
            self.source = "local"
            return self.local_dir

        if self.version == UNKNOWN:
            raise TemplateError(
                "Cannot resolve template version (CLI version unknown).",
                hint="Set PORTABASE_TEMPLATES_DIR to a local templates folder or PORTABASE_TEMPLATES_VERSION.",
            )

        remote_manifest = self._fetch_manifest()
        if remote_manifest is None:
            cached = self._cached_manifest()
            if cached is None:
                raise TemplateError(
                    f"Templates for version {self.version} are unavailable and not cached.",
                    hint="Check your internet connection, or set PORTABASE_TEMPLATES_DIR.",
                )
            self._manifest = cached
            self.source = "cache"
            self._verify_cache_complete(cached)
            return self.cache_dir

        if remote_manifest.version != self.version:
            raise TemplateError(
                f"Template manifest is for version {remote_manifest.version}, expected {self.version}."
            )
        self._sync(remote_manifest)
        self._manifest = remote_manifest
        self.source = "remote"
        return self.cache_dir

    # ---- access -----------------------------------------------------------

    def get(self, name: str) -> jinja2.Template:
        directory = self.resolve()
        if name not in self.manifest.files:
            raise TemplateError(f"Template '{name}' is not part of version {self.version}.")
        if self._env is None:
            self._env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(str(directory)),
                undefined=jinja2.StrictUndefined,
                keep_trailing_newline=True,
                autoescape=False,
            )
        try:
            return self._env.get_template(name)
        except jinja2.TemplateError as e:
            raise TemplateError(f"Template '{name}' failed to load: {e}", cause=e) from e

    def engine_template(self, engine_key: str) -> jinja2.Template:
        name = self.manifest.engines.get(engine_key)
        if name is None:
            raise TemplateError(f"No template mapped for engine '{engine_key}' in version {self.version}.")
        return self.get(name)

    # ---- internals --------------------------------------------------------

    def _url(self, name: str) -> str:
        return f"{self.base_url}/{self.version}/{name}"

    def _fetch_manifest(self) -> Manifest | None:
        try:
            return Manifest.from_json(self.http.get_json(self._url(MANIFEST_NAME)))
        except NetworkError:
            return None

    def _cached_manifest(self) -> Manifest | None:
        path = self.cache_dir / MANIFEST_NAME
        if not path.exists():
            return None
        try:
            return Manifest.from_json(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TemplateError):
            return None

    def _verify_cache_complete(self, manifest: Manifest) -> None:
        for name, entry in manifest.files.items():
            path = self.cache_dir / name
            if not path.exists() or _sha256(path) != entry.sha256:
                raise TemplateError(
                    f"Cached template '{name}' is missing or corrupt and the network is unavailable.",
                    hint="Reconnect and retry; the cache will be refreshed.",
                )

    def _sync(self, manifest: Manifest) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for name, entry in manifest.files.items():
            path = self.cache_dir / name
            if path.exists() and path.stat().st_size == entry.size and _sha256(path) == entry.sha256:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            try:
                self.http.download(self._url(name), tmp)
            except NetworkError as e:
                raise TemplateError(f"Could not download template '{name}'.", cause=e) from e
            if tmp.stat().st_size != entry.size or _sha256(tmp) != entry.sha256:
                tmp.unlink(missing_ok=True)
                raise TemplateError(f"Template '{name}' failed integrity check (sha256 mismatch).")
            os.replace(tmp, path)
        for stale in self.cache_dir.rglob("*.j2"):
            if stale.relative_to(self.cache_dir).as_posix() not in manifest.files:
                stale.unlink(missing_ok=True)
        (self.cache_dir / MANIFEST_NAME).write_text(
            json.dumps(
                {
                    "schema": manifest.schema,
                    "version": manifest.version,
                    "generated_at": manifest.generated_at,
                    "commit": manifest.commit,
                    "files": {n: {"sha256": e.sha256, "size": e.size} for n, e in manifest.files.items()},
                    "engines": manifest.engines,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
```

`TEMPLATE_BASE_URL` reste définie dans `core/config.py` (le legacy `core/network.py` l'importe de là) ; `services/templates.py` l'importe depuis `core.config`. Pas de circularité : `core` n'importe jamais `services`.

- [ ] **Step 2: Vérifier en mode local (dev)**

Run: `uv run python -c "
from pathlib import Path
from services.http import HttpClient
from services.templates import TemplateRepository
from core.config import GlobalConfig
r = TemplateRepository.from_environment(HttpClient(), GlobalConfig())
print(r.source, r.resolve(), r.source, len(r.manifest.files), r.manifest.engines['mysql'])
print(r.engine_template('redis').render(name='n', volume='v', auth=False, port_var='1', db_var='', user_var='', password_var='')[:40].strip())"`
Expected: `unresolved <repo>/templates local 9 engines/mariadb.yml.j2` puis `n:` (début du service rendu).

- [ ] **Step 3: Vérifier le mode remote contre un serveur local**

```bash
# Terminal 1 — publie templates/ comme S3 sous la version 99.0.0 avec un manifest
mkdir -p /tmp/pb-s3/99.0.0 && cp -r templates/. /tmp/pb-s3/99.0.0/ && cd /tmp/pb-s3/99.0.0 && \
uv --directory /home/soluce/Documents/PROJETS/Portabase/cli run python -c "
import json, hashlib, pathlib
files = {p.as_posix(): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'size': p.stat().st_size} for p in sorted(pathlib.Path('.').rglob('*.j2'))}
json.dump({'schema':1,'version':'99.0.0','generated_at':'now','commit':'x','files':files,'engines':json.load(open('engines.map.json'))}, open('manifest.json','w'), indent=2)" && \
cd /tmp/pb-s3 && python3 -m http.server 8765
```

Terminal 2 :
```bash
uv run python -c "
import tempfile; from pathlib import Path
from services.http import HttpClient
from services.templates import TemplateRepository
cache = Path(tempfile.mkdtemp())
r = TemplateRepository(HttpClient(), cache, '99.0.0', base_url='http://127.0.0.1:8765')
print(r.resolve(), r.source, sorted(p.name for p in (cache/'templates'/'99.0.0').iterdir()))
r2 = TemplateRepository(HttpClient(), cache, '99.0.0', base_url='http://127.0.0.1:8765'); r2.resolve(); print('second:', r2.source)
r3 = TemplateRepository(HttpClient(), cache, '99.0.0', base_url='http://127.0.0.1:1'); r3.resolve(); print('offline:', r3.source)
try: TemplateRepository(HttpClient(), Path(tempfile.mkdtemp()), '99.0.0', base_url='http://127.0.0.1:1').resolve()
except Exception as e: print('offline no cache:', type(e).__name__, e.code)
try: TemplateRepository(HttpClient(), cache, '98.0.0', base_url='http://127.0.0.1:8765').resolve()
except Exception as e: print('missing version:', type(e).__name__, e.code)"
```
Expected: `... remote ['agent.yml.j2', 'dashboard.yml.j2', 'engines', 'manifest.json']`, `second: remote` (manifest re-fetché, fichiers en cache non re-téléchargés), `offline: cache`, `offline no cache: TemplateError E_TEMPLATE`, `missing version: TemplateError E_TEMPLATE`. Arrêter le serveur.

- [ ] **Step 4: Commit**

```bash
git add services/templates.py
git commit -m "feat(services): add TemplateRepository with manifest verification and cache"
```

---

### Task 7 : `scripts/render_check.py`

**Files:**
- Create: `scripts/render_check.py`

**Interfaces:**
- Consumes: `TemplateRepository` (mode local), `engines.registry`, `FixedPortAllocator`.
- Produces: script exécutable, exit 0 si tous les rendus sont du YAML valide (et `docker compose config` valide si Docker disponible), exit 1 sinon. Réutilisé par la CI (Task 8) et remplacé par un appel à `ComposeRenderer` au Plan 4.

- [ ] **Step 1: Écrire le script**

```python
#!/usr/bin/env python3
"""Render every template with fixture contexts and validate the output.

Usage: uv run python scripts/render_check.py [--templates DIR] [--no-compose]
Exit 0 on success. Prints one line per rendered case.
"""

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

from core.config import GlobalConfig  # noqa: E402
from engines import registry  # noqa: E402
from services.http import HttpClient  # noqa: E402
from services.ports import FixedPortAllocator  # noqa: E402
from services.templates import TemplateRepository  # noqa: E402

AGENT_GLOBALS = {
    "tz_var": "${TZ}",
    "edge_key_var": "${EDGE_KEY}",
    "log_level_var": "${LOG_LEVEL}",
    "polling_var": "${POLLING}",
}
AGENT_ENV = 'TZ="UTC"\nEDGE_KEY="x"\nLOG_LEVEL="info"\nPOLLING="5"\n'
DASHBOARD_VARS = {
    "project_name_var": "pb",
    "host_port_var": "${HOST_PORT}",
    "tz_var": "${TZ}",
    "log_level_var": "${LOG_LEVEL}",
    "project_secret_var": "${PROJECT_SECRET}",
    "project_url_var": "${PROJECT_URL}",
    "pg_port_var": "${PG_PORT}",
    "postgres_db_var": "${POSTGRES_DB}",
    "postgres_user_var": "${POSTGRES_USER}",
    "postgres_password_var": "${POSTGRES_PASSWORD}",
}
DASHBOARD_ENV = (
    'HOST_PORT="8887"\nTZ="UTC"\nLOG_LEVEL="info"\nPROJECT_SECRET="s"\nPROJECT_URL="http://localhost"\n'
    'PG_PORT="5433"\nPOSTGRES_DB="pb"\nPOSTGRES_USER="pb"\nPOSTGRES_PASSWORD="p"\n'
)


class Failure(Exception):
    pass


def validate(label: str, compose: str, env_text: str, use_compose: bool) -> None:
    try:
        doc = yaml.safe_load(compose)
    except yaml.YAMLError as e:
        raise Failure(f"{label}: invalid YAML: {e}\n{compose}") from e
    if not isinstance(doc, dict) or "services" not in doc:
        raise Failure(f"{label}: no services key\n{compose}")
    if use_compose:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "docker-compose.yml").write_text(compose, encoding="utf-8")
            Path(tmp, ".env").write_text(env_text, encoding="utf-8")
            Path(tmp, "databases.json").write_text('{"databases": []}', encoding="utf-8")
            proc = subprocess.run(
                ["docker", "compose", "-p", "rendercheck", "config", "--quiet"],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                raise Failure(f"{label}: docker compose config failed:\n{proc.stderr}\n{compose}")
    print(f"ok  {label}")


def agent_cases(repo: TemplateRepository) -> list[tuple[str, str, str]]:
    ports = FixedPortAllocator()
    cases = []
    # 1. empty agent, all toggles off
    cases.append(("agent/empty", render_agent(repo, [], False, False, []), AGENT_ENV))
    # 2. toggles on, sqlite mount
    cases.append(
        (
            "agent/toggles",
            render_agent(repo, [], True, True, [{"host": "./x.sqlite", "container": "/config/x.sqlite"}]),
            AGENT_ENV,
        )
    )
    # 3. one case per engine/variant
    all_services, all_env = [], AGENT_ENV
    for engine in registry:
        if engine.template is None:
            continue
        for auth in (True, False) if engine.auth_variants else (True,):
            spec = engine.generate(auth=auth, ports=ports, answers={})
            env = engine.env_vars(spec)
            env_text = AGENT_ENV + "".join(f'{k}="{v}"\n' for k, v in env.items())
            body = repo.engine_template(engine.key).render(**engine.template_ctx(spec))
            service = {"name": spec.host, "volume": f"{spec.host}-data", "body": body}
            cases.append((f"agent/{engine.key}{'/auth' if auth else '/noauth' if engine.auth_variants else ''}",
                          render_agent(repo, [service], False, False, []), env_text))
            all_services.append(service)
            all_env += "".join(f'{k}="{v}"\n' for k, v in env.items())
    # 4. everything at once
    cases.append(("agent/all", render_agent(repo, all_services, True, True, []), all_env))
    return cases


def render_agent(repo, services, host_gateway, docker_socket, mounts) -> str:
    return repo.get("agent.yml.j2").render(
        services=services, host_gateway=host_gateway, docker_socket=docker_socket, mounts=mounts, **AGENT_GLOBALS
    )


def dashboard_cases(repo: TemplateRepository) -> list[tuple[str, str, str]]:
    return [
        (f"dashboard/{mode}", repo.get("dashboard.yml.j2").render(db_mode=mode, **DASHBOARD_VARS), DASHBOARD_ENV)
        for mode in ("external", "internal", "custom")
    ]


def engines_check(repo: TemplateRepository) -> None:
    mapped = repo.manifest.engines
    for engine in registry:
        if engine.template is None:
            continue
        if mapped.get(engine.key) != engine.template:
            raise Failure(f"engines.map.json: {engine.key} -> {mapped.get(engine.key)} but code says {engine.template}")
        if engine.template not in repo.manifest.files:
            raise Failure(f"{engine.key}: template {engine.template} not found")
    for key in mapped:
        if key not in registry:
            raise Failure(f"engines.map.json maps unknown engine '{key}'")
    print(f"ok  engines-check ({len(mapped)} mapped)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--templates", default=os.environ.get("PORTABASE_TEMPLATES_DIR", "templates"))
    parser.add_argument("--no-compose", action="store_true", help="Skip docker compose config validation")
    args = parser.parse_args()

    use_compose = not args.no_compose and shutil.which("docker") is not None
    if not use_compose:
        print("note: docker not available, YAML validation only")
    repo = TemplateRepository(HttpClient(), GlobalConfig().cache_dir, "local", local_dir=Path(args.templates))
    try:
        engines_check(repo)
        for label, compose, env_text in agent_cases(repo) + dashboard_cases(repo):
            validate(label, compose, env_text, use_compose)
    except Failure as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Exécuter**

Run: `uv run python scripts/render_check.py`
Expected: `ok  engines-check (9 mapped)` puis une ligne `ok` par cas : `agent/empty`, `agent/toggles`, `agent/postgresql`, `agent/postgresql-cluster`, `agent/mysql`, `agent/mariadb`, `agent/firebird`, `agent/mongodb/auth`, `agent/mongodb/noauth`, `agent/redis/auth`, `agent/redis/noauth`, `agent/valkey/auth`, `agent/valkey/noauth`, `agent/mssql`, `agent/all`, `dashboard/external`, `dashboard/internal`, `dashboard/custom`. Exit 0.

Si `docker compose config` échoue sur un cas : lire l'erreur, corriger le template (pas le script).

- [ ] **Step 3: Ruff sur le script**

Run: `uv run ruff check scripts/ && uv run ruff format scripts/`

- [ ] **Step 4: Commit**

```bash
git add scripts/render_check.py
git commit -m "ci: add render_check script validating every template with fixtures"
```

---

### Task 8 : CI — `render-check`, `engines-check`, manifest à l'upload, hotfix

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/templates-upload.yml`
- Create: `.github/workflows/templates-hotfix.yml`

- [ ] **Step 1: Ajouter le job `render-check` à `ci.yml`** (après `test`)

```yaml
  render-check:
    name: render-check
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - uses: astral-sh/setup-uv@caf0cab7a618c569241d31dcd442f54681755d39 # v3
      - name: Install
        run: uv sync --frozen --all-groups
      - name: Render and validate templates (YAML + docker compose config)
        run: uv run python scripts/render_check.py --templates templates
```

Le job `engines-check` de la spec est couvert par la fonction `engines_check()` du même script (une seule exécution, deux vérifications). Pas de job séparé.

- [ ] **Step 2: `templates-upload.yml` — source et manifest**

Remplacer les deux étapes d'upload par :

```yaml
      - name: Generate manifest
        env:
          VERSION: ${{ inputs.version }}
        run: |
          set -euo pipefail
          CLEAN_VERSION="${VERSION#v}"
          cd templates
          FILES=$(find . -name '*.j2' -type f | sort | while read -r f; do
            rel="${f#./}"
            printf '{"%s":{"sha256":"%s","size":%s}}\n' "$rel" "$(sha256sum "$f" | cut -d' ' -f1)" "$(stat -c%s "$f")"
          done | jq -s 'add')
          jq -n \
            --arg version "$CLEAN_VERSION" \
            --arg commit "$GITHUB_SHA" \
            --arg date "$(date -u +%FT%TZ)" \
            --argjson files "$FILES" \
            --argjson engines "$(cat engines.map.json)" \
            '{schema:1, version:$version, generated_at:$date, commit:$commit, files:$files, engines:$engines}' \
            > manifest.json
          cat manifest.json

      - name: Upload versioned templates
        env:
          VERSION: ${{ inputs.version }}
        run: |
          CLEAN_VERSION="${VERSION#v}"
          s3cmd $S3CMD_ARGS sync templates/ \
            "s3://${{ secrets.S3_BUCKET }}/cli/public/templates/${CLEAN_VERSION}/" --acl-public --delete-removed

      - name: Upload latest templates (stable only, legacy fallback)
        if: ${{ !inputs.is_prerelease }}
        run: |
          s3cmd $S3CMD_ARGS sync templates/ \
            "s3://${{ secrets.S3_BUCKET }}/cli/public/templates/latest/" --acl-public
```

`latest/` reste alimenté pour les vieux binaires (fallback legacy). Le nouveau code ne le lit jamais. À retirer quand plus aucune version legacy n'est supportée.

- [ ] **Step 3: `templates-hotfix.yml`**

```yaml
name: Templates hotfix

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Existing CLI version to re-publish templates for (e.g. 26.09.0). Templates must stay compatible with that version's code."
        required: true
        type: string

permissions: {}

jobs:
  hotfix:
    uses: ./.github/workflows/templates-upload.yml
    with:
      version: ${{ inputs.version }}
      is_prerelease: true   # never touch latest/ from a hotfix
    secrets:
      S3_ENDPOINT: ${{ secrets.S3_ENDPOINT }}
      S3_ACCESS_KEY: ${{ secrets.S3_ACCESS_KEY }}
      S3_SECRET_KEY: ${{ secrets.S3_SECRET_KEY }}
      S3_BUCKET: ${{ secrets.S3_BUCKET }}
```

- [ ] **Step 4: Valider les YAML**

Run: `for f in .github/workflows/ci.yml .github/workflows/templates-upload.yml .github/workflows/templates-hotfix.yml; do uv run python -c "import yaml,sys; yaml.safe_load(open('$f')); print('ok $f')"; done`

- [ ] **Step 5: Tester la génération du manifest en local**

Run: `cd templates && FILES=$(find . -name '*.j2' -type f | sort | while read -r f; do rel="${f#./}"; printf '{"%s":{"sha256":"%s","size":%s}}\n' "$rel" "$(sha256sum "$f" | cut -d' ' -f1)" "$(stat -c%s "$f")"; done | jq -s 'add') && jq -n --arg version 0.0.0 --arg commit x --arg date now --argjson files "$FILES" --argjson engines "$(cat engines.map.json)" '{schema:1, version:$version, generated_at:$date, commit:$commit, files:$files, engines:$engines}' | uv run python -c "import json,sys; from services.templates import Manifest; m = Manifest.from_json(json.load(sys.stdin)); print(len(m.files), 'files,', len(m.engines), 'engines')"; cd ..`
Expected: `9 files, 9 engines`.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/
git commit -m "ci: render-check job, manifest generation on template upload, hotfix workflow"
```

---

### Task 9 : PR et release candidate

- [ ] **Step 1: Lint complet et PR**

Run: `uv run ruff check . && uv run ruff format --check . && uv run python scripts/render_check.py --no-compose`
Puis :
```bash
git checkout -b refactor/templates-engines
git push -u origin refactor/templates-engines
```
PR « feat: Jinja2 templates, engine registry, template repository ». Checks attendus verts : `lint`, `test`, `render-check`, `gitleaks`, `plumber`, `build-smoke`.

- [ ] **Step 2: Release candidate**

Après merge : Bump version `26.08.0rc2` (ou suivant), channel `rc`. Vérifier sur S3 que `cli/public/templates/26.08.0rc2/` contient `manifest.json`, `agent.yml.j2`, `engines/`, **et** `agent.yml` / `dashboard.yml` legacy. Installer le binaire rc et lancer `portabase agent test-rc` (code legacy) : doit fonctionner comme avant (fetch `agent.yml` sous la version exacte).

---

## Self-review

**Spec coverage :**
- §5.4 `TemplateRepository` : résolution version/env/dev ✔, cache ✔, manifest sha256+size ✔, suppression fichiers obsolètes ✔, pas de `latest` côté client ✔, Jinja2 `StrictUndefined` ✔, schéma inconnu → `TemplateError` ✔, version ≠ → `TemplateError` ✔.
- §5.6 templates : `agent.yml.j2` avec `mounts`, `docker_socket`, `host_gateway`, `services`, `volumes` ✔ ; moteurs avec `{% if auth %}` ✔ ; `dashboard.yml.j2` avec `db_mode` ✔.
- §6 moteurs : hiérarchie, hooks, registre imports explicites ✔ ; `agent_database` hook ✔ ; Redis/Valkey séparés ✔ ; `describe` pour `db list` (Plan 4).
- §6.1 options : `option_fields`, `non_default_options`, projection ✔ ; parsing `-o` et prompts → Plan 4 (flow).
- §9.1 `render-check` ✔, `engines-check` (fusionné dans le script) ✔. §9.3 manifest ✔, hotfix ✔.
- §10 D : shippable en rc, legacy intact ✔.

**Placeholders :** aucun.

**Cohérence :** `DbEngine.template_ctx` produit `name/volume/auth/*_var` = variables consommées par tous les `.j2` ✔ ; `FirebirdEngine.template_ctx` ajoute `root_password_var` consommé par `firebird.yml.j2` ✔ ; `render_check.render_agent` passe `AGENT_GLOBALS` = variables `*_var` de `agent.yml.j2` ✔ ; `Manifest.engines` clé → `TemplateRepository.engine_template` ✔ ; `FixedPortAllocator` défini Task 1, utilisé Task 7 ✔.

**Écarts connus :**
- `DatabaseSpec.host_port` est `None` pour les specs chargées depuis une install legacy tant que Plan 4 ne lit pas `.env` ; sans effet ici.
