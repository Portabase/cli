from __future__ import annotations

import secrets
import uuid
from abc import ABC, abstractmethod
from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from core.utils import escape_yaml_double_quoted, generate_password
from services.ports import PortAllocator

STANDARD_EXISTING_FIELDS = (
    Field("host", "Host", "text", default="localhost"),
    Field("port", "Port", "int"),
    Field("database", "Database Name", "text"),
    Field("username", "Username", "text"),
    Field("password", "Password", "secret"),
)


class DbEngine(ABC):
    key: str
    display: str
    default_port: int | None = None
    template: str | None = None
    auth_variants: bool = False
    warning: str | None = None
    has_modes: bool = True
    label_default: str = "External DB"

    abstract: bool = False
    required: tuple[str, ...] = ("key", "display")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls.abstract = "abstract" in cls.__dict__ and cls.__dict__["abstract"]
        if cls.abstract:
            return
        missing = [name for name in cls.required if not getattr(cls, name, None)]
        if missing:
            raise TypeError(
                f"{cls.__module__}.{cls.__qualname__} is missing required engine "
                f"attribute(s): {', '.join(missing)}. Set them as class attributes, "
                "or set `abstract = True` if this class is only a base for others."
            )
        if cls.template is not None and not cls.template.startswith("engines/"):
            raise TypeError(
                f"{cls.__qualname__}.template must be a path under 'engines/', "
                f"got {cls.template!r} (e.g. 'engines/{cls.key}.yml.j2')."
            )

    def fields_existing(self) -> list[Field]:
        return [
            Field("port", "Port", "int", default=self.default_port)
            if field.name == "port"
            else field
            for field in STANDARD_EXISTING_FIELDS
        ]

    def fields_new(self) -> list[Field]:
        return []

    def option_fields(self) -> list[Field]:
        return []

    @abstractmethod
    def generate(
        self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]
    ) -> DatabaseSpec: ...

    def from_existing(self, answers: dict[str, Any]) -> DatabaseSpec:
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=answers.get("label") or self.label_default,
            managed=False,
            host=answers["host"],
            port=int(answers["port"]),
            database=answers["database"],
            username=answers["username"],
            password=answers["password"],
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        prefix = spec.env_prefix
        return {
            f"{prefix}_PORT": str(spec.host_port),
            f"{prefix}_DB": spec.database or "",
            f"{prefix}_USER": spec.username or "",
            f"{prefix}_PASS": spec.password or "",
        }

    def template_ctx(
        self, spec: DatabaseSpec, *, inline: bool = False
    ) -> dict[str, Any]:
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

    def non_default_options(self, spec: DatabaseSpec) -> dict[str, Any]:
        defaults = {field.name: field.default for field in self.option_fields()}
        return {
            key: value
            for key, value in spec.options.items()
            if key in defaults and value != defaults[key]
        }

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def service_name(slug: str, auth: bool = False) -> str:
        suffix = "auth-" if auth else ""
        return f"db-{slug}-{suffix}{secrets.token_hex(2)}"

    @staticmethod
    def var(spec: DatabaseSpec, suffix: str, value: Any, inline: bool) -> str:
        if inline:
            return escape_yaml_double_quoted(str(value if value is not None else ""))
        return f"${{{spec.env_prefix}_{suffix}}}"


class StandardSqlEngine(DbEngine):
    abstract = True
    required = (*DbEngine.required, "template", "default_port", "slug", "db_prefix")

    slug: str
    db_prefix: str
    default_user = "admin"

    def generate(
        self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]
    ) -> DatabaseSpec:
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
