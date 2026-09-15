import pytest

from services.compose_facts import (
    CA_BUNDLE_IN_CONTAINER,
    GENERATED_MARKER,
    ComposeFacts,
)


def _facts(tmp_path, text):
    path = tmp_path / "docker-compose.yml"
    path.write_text(text, encoding="utf-8")
    return ComposeFacts(path)


def missing_file(tmp_path):
    facts = ComposeFacts(tmp_path / "docker-compose.yml")
    assert not facts.exists
    assert not facts.is_generated
    assert not facts.host_gateway
    assert facts.ca_bundle is None


def generated_marker(tmp_path):
    header = f"{GENERATED_MARKER} 1.0. Do not edit.\nservices: {{}}\n"
    assert _facts(tmp_path, header).is_generated
    assert not _facts(tmp_path, "services: {}\n").is_generated


@pytest.mark.parametrize(
    "text",
    [
        "services:\n  agent:\n    extra_hosts:\n      - localhost:host-gateway\n",
        "services:\n  agent:\n    extra_hosts:\n      localhost: host-gateway\n",
    ],
    ids=["list", "dict"],
)
def host_gateway_detected(tmp_path, text):
    assert _facts(tmp_path, text).host_gateway


@pytest.mark.parametrize(
    "text",
    [
        "services:\n  agent:\n    image: x\n",
        "services:\n  other:\n    extra_hosts: ['localhost:host-gateway']\n",
        "services: []\n",
        "- not a mapping\n",
        "services: [unclosed\n",
    ],
)
def host_gateway_absent(tmp_path, text):
    assert not _facts(tmp_path, text).host_gateway


def ca_bundle_short_syntax(tmp_path):
    text = (
        "services:\n  agent:\n    volumes:\n"
        "      - ./databases.json:/config/config.json\n"
        f"      - ./ca.crt:{CA_BUNDLE_IN_CONTAINER}:ro\n"
    )
    assert _facts(tmp_path, text).ca_bundle == "./ca.crt"


def ca_bundle_long_syntax(tmp_path):
    text = (
        "services:\n  agent:\n    volumes:\n"
        "      - type: bind\n        source: /etc/ca.crt\n"
        f"        target: {CA_BUNDLE_IN_CONTAINER}\n"
    )
    assert _facts(tmp_path, text).ca_bundle == "/etc/ca.crt"


def ca_bundle_absent(tmp_path):
    text = "services:\n  agent:\n    volumes:\n      - ./db.json:/config/config.json\n"
    assert _facts(tmp_path, text).ca_bundle is None
