import pytest

from core.errors import TemplateError
from services.renderer import ComposeRenderer
from services.templates import TemplateRepository
from tests.support import ROOT


def names_are_sorted_and_complete(templates):
    names = templates.names()
    assert "agent.yml.j2" in names
    assert "dashboard.yml.j2" in names
    assert "engines/postgresql.yml.j2" in names
    assert names == sorted(names)


def bundled_defaults_to_repo_templates(monkeypatch):
    monkeypatch.delenv("PORTABASE_TEMPLATES_DIR", raising=False)
    assert TemplateRepository.bundled().root == ROOT / "templates"


def bundled_honours_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PORTABASE_TEMPLATES_DIR", str(tmp_path))
    assert TemplateRepository.bundled().root == tmp_path


def empty_folder(tmp_path):
    with pytest.raises(TemplateError, match="No templates found"):
        TemplateRepository(tmp_path).get("agent.yml.j2")


def missing_template(templates):
    with pytest.raises(TemplateError, match="'engines/nope.yml.j2' is missing"):
        templates.get("engines/nope.yml.j2")


def broken_template(tmp_path):
    (tmp_path / "agent.yml.j2").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "bad.j2").write_text("{% if %}", encoding="utf-8")
    with pytest.raises(TemplateError, match="failed to load"):
        TemplateRepository(tmp_path).get("bad.j2")


def undefined_variable_is_an_error(templates):
    with pytest.raises(TemplateError, match="rendering failed"):
        ComposeRenderer._render_template(templates.get("agent.yml.j2"), {})
