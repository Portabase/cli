from core.specs import DatabaseSpec
from engines import registry
from engines.docker_volume import DockerVolumeEngine
from tests.support import agent_service, field_specs

VOLUME = registry.get("docker-volume")
SOCKET = "/var/run/docker.sock:/var/run/docker.sock"


def attributes():
    assert type(VOLUME) is DockerVolumeEngine
    assert (VOLUME.key, VOLUME.display, VOLUME.default_port) == (
        "docker-volume",
        "Docker Volume",
        None,
    )
    assert VOLUME.template is None
    assert (VOLUME.auth_variants, VOLUME.has_modes) == (False, False)
    assert "/var/run/docker.sock" in (VOLUME.warning or "")


def generate(ports):
    answers = {"volume": " data ", "container": "app", "label": "Files"}
    spec = VOLUME.generate(auth=False, ports=ports, answers=answers)
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="docker-volume",
        name="Files",
        volume="data",
        container="app",
    )
    assert VOLUME.describe(spec) == "volume: data"


def env_vars():
    assert VOLUME.env_vars(VOLUME.from_existing({"volume": "v"})) == {}


def agent_entry():
    bare = VOLUME.from_existing({"volume": "v"})
    with_container = VOLUME.from_existing({"volume": "v", "container": "app"})
    assert VOLUME.agent_entry(bare) == {
        "name": "Docker Volume",
        "type": "docker-volume",
        "volume_name": "v",
        "generated_id": bare.id,
    }
    assert VOLUME.agent_entry(with_container) == {
        "name": "Docker Volume",
        "type": "docker-volume",
        "volume_name": "v",
        "container_name": "app",
        "generated_id": with_container.id,
    }


def fields():
    assert field_specs(VOLUME.fields_existing()) == [
        ("volume", "text", None),
        ("container", "text", ""),
    ]
    assert VOLUME.fields_new() == VOLUME.fields_existing()
    assert VOLUME.option_fields() == []


def from_existing():
    spec = VOLUME.from_existing({"volume": "  data  ", "container": "  "})
    assert spec == DatabaseSpec(
        id=spec.id, engine="docker-volume", name="Docker Volume", volume="data"
    )


def compose_service(render_engine):
    rendered = render_engine(
        "docker-volume", answers={"volume": "v", "container": "app"}
    )
    assert rendered.doc["services"] == {"agent": agent_service(SOCKET)}
    assert "volumes" not in rendered.doc
    assert rendered.databases == [VOLUME.agent_entry(rendered.spec)]


def compose_service_inline(render_engine):
    rendered = render_engine("docker-volume", inline=True, answers={"volume": "v"})
    assert rendered.doc["services"] == {"agent": agent_service(SOCKET, inline=True)}
