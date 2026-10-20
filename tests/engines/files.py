import pytest

from core.errors import ValidationError
from core.specs import DatabaseSpec
from engines import registry
from engines.files import FilesEngine
from tests.support import agent_service, field_specs

FILES = registry.get("files")
MOUNT = "/srv/uploads:/data/srv/uploads"


def attributes():
    assert type(FILES) is FilesEngine
    assert (FILES.key, FILES.display, FILES.default_port) == ("files", "Files", None)
    assert FILES.template is None
    assert (FILES.auth_variants, FILES.has_modes) == (False, False)
    assert "restore" in (FILES.warning or "")


def generate(ports):
    answers = {"path": "/srv/uploads", "label": "Uploads"}
    spec = FILES.generate(auth=False, ports=ports, answers=answers)
    assert spec == DatabaseSpec(
        id=spec.id, engine="files", name="Uploads", path="/data/srv/uploads"
    )
    assert FILES.describe(spec) == "dir: /srv/uploads"


def env_vars():
    assert FILES.env_vars(FILES.from_existing({"path": "/srv"})) == {}


def agent_entry():
    bare = FILES.from_existing({"path": "/srv/uploads"})
    assert FILES.agent_entry(bare) == {
        "name": "Files",
        "type": "files",
        "path": "/data/srv/uploads",
        "generated_id": bare.id,
    }
    tuned = bare.with_options(
        {"method": "snapshot", "exclude": ["*.tmp"], "one_file_system": False}
    )
    assert FILES.agent_entry(tuned)["options"] == {
        "method": "snapshot",
        "exclude": ["*.tmp"],
    }


def fields():
    assert field_specs(FILES.fields_existing()) == [("path", "text", None)]
    assert FILES.fields_new() == FILES.fields_existing()
    assert field_specs(FILES.option_fields()) == [
        ("method", "choice", "archive"),
        ("exclude", "list", []),
        ("one_file_system", "bool", False),
    ]
    assert FILES.option_fields()[0].choices == ("archive", "snapshot", "sync")


def from_existing():
    spec = FILES.from_existing({"path": "/srv/uploads"})
    assert spec == DatabaseSpec(
        id=spec.id, engine="files", name="Files", path="/data/srv/uploads"
    )


def compose_service(render_engine):
    rendered = render_engine("files", answers={"path": "/srv/uploads"})
    assert rendered.doc["services"] == {"agent": agent_service(MOUNT)}
    assert "volumes" not in rendered.doc
    assert rendered.databases == [FILES.agent_entry(rendered.spec)]


def compose_service_inline(render_engine):
    rendered = render_engine("files", inline=True, answers={"path": "/srv/uploads"})
    assert rendered.doc["services"] == {"agent": agent_service(MOUNT, inline=True)}


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [("/srv/uploads", "/srv/uploads"), (" /srv/uploads/ ", "/srv/uploads")],
)
def path_is_normalized(raw, normalized):
    assert FILES.fields_existing()[0].validator(raw) == normalized


@pytest.mark.parametrize(
    "raw", ["uploads", "./uploads", "/", "//", "C:\\data", "/srv/a:b", "/srv/#1"]
)
def path_rejects_unmountable_values(raw):
    with pytest.raises(ValidationError):
        FILES.fields_existing()[0].validator(raw)


def exclude_rejects_brace_alternation():
    validator = FILES.option_fields()[1].validator
    assert validator(["node_modules", "/cache"]) == ["node_modules", "/cache"]
    with pytest.raises(ValidationError, match="Brace"):
        validator(["*.{log,tmp}"])


@pytest.mark.parametrize(
    ("path", "mount"),
    [
        ("/data/srv/uploads", ("/srv/uploads", "/data/srv/uploads")),
        ("/mnt/nas", None),
        (None, None),
    ],
)
def mount_for(path, mount):
    spec = DatabaseSpec(id="1", engine="files", name="n", path=path)
    assert FilesEngine.mount_for(spec) == mount
