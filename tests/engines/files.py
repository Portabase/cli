from typing import cast

import pytest

from core.errors import ValidationError
from core.specs import DatabaseSpec
from engines import registry
from engines.files import FilesEngine
from tests.support import agent_service, field_specs
from ui.components.prompt import Prompt
from ui.form import Form

FILES = registry.get("files")
MOUNT = "/srv/uploads:/data/srv/uploads"
FORM = Form(cast(Prompt, None), non_interactive=True)


def attributes():
    assert type(FILES) is FilesEngine
    assert (FILES.key, FILES.display, FILES.default_port) == ("files", "Files", None)
    assert FILES.template is None
    assert (FILES.auth_variants, FILES.has_modes) == (False, False)
    assert "restore" in (FILES.warning or "")
    assert "1.25.0" in (FILES.warning or "")


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
    limited = bare.with_options(
        {"method": "sync", "max_delete": 100, "max_delete_size": "10G"}
    )
    assert FILES.agent_entry(limited)["options"] == {
        "method": "sync",
        "max_delete": 100,
        "max_delete_size": "10G",
    }


def fields():
    assert field_specs(FILES.fields_existing()) == [("path", "text", None)]
    assert FILES.fields_new() == FILES.fields_existing()
    assert field_specs(FILES.option_fields()) == [
        ("method", "choice", "archive"),
        ("exclude", "list", []),
        ("one_file_system", "bool", False),
        ("max_delete", "text", ""),
        ("max_delete_size", "text", ""),
    ]
    assert FILES.option_fields()[0].choices == ("archive", "snapshot", "sync", "copy")


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


def delete_limits_are_written_only_when_set():
    options = FORM.collect(
        FILES.option_fields(),
        {"method": "sync", "max_delete": " 0 ", "max_delete_size": "1.5g"},
    )
    assert (options["max_delete"], options["max_delete_size"]) == (0, "1.5g")

    unset = FORM.collect(FILES.option_fields(), {"method": "sync"})
    spec = FILES.from_existing({"path": "/srv"}).with_options(unset)
    assert FILES.agent_entry(spec)["options"] == {"method": "sync"}


@pytest.mark.parametrize("method", ["archive", "snapshot", "copy"])
def delete_limits_only_apply_to_sync(method):
    options = FORM.collect(FILES.option_fields(), {"method": method})
    assert "max_delete" not in options
    assert "max_delete_size" not in options
    with pytest.raises(ValidationError, match="--max-delete does not apply"):
        FORM.collect(FILES.option_fields(), {"method": method, "max_delete": "5"})


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("max_delete", "-1"),
        ("max_delete", "1.5"),
        ("max_delete", "ten"),
        ("max_delete_size", "10GB"),
        ("max_delete_size", "G"),
        ("max_delete_size", "1,5G"),
    ],
)
def delete_limits_reject_invalid_values(option, value):
    with pytest.raises(ValidationError):
        FORM.collect(FILES.option_fields(), {"method": "sync", option: value})
