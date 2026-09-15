import pytest

from core.errors import DockerError
from services import docker
from services.docker import DockerRunner


def project_name_is_the_slugified_folder(tmp_path):
    folder = tmp_path / "My Agent"
    folder.mkdir()
    assert DockerRunner.project_name(folder) == "my-agent"


def binary_missing(monkeypatch):
    monkeypatch.setattr(docker.shutil, "which", lambda _: None)
    runner = DockerRunner()
    assert not runner.available()
    with pytest.raises(DockerError, match="Docker not found"):
        _ = runner.binary


def binary_explicit():
    assert DockerRunner("/opt/docker").binary == "/opt/docker"
