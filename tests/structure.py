import ast

from engines import registry
from tests.support import ROOT

TESTS = ROOT / "tests"
PACKAGES = ("core", "services", "engines")
# Modules whose tests live under another name.
ALIASES = {"engines/__init__.py": "engines/registry.py"}
SHARED = {"conftest.py", "support.py", "structure.py"}
ENGINE_SKELETON = [
    "attributes",
    "generate",
    "env_vars",
    "agent_entry",
    "fields",
    "from_existing",
    "compose_service",
    "compose_service_inline",
]


def _functions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]


def every_module_has_a_test_file():
    missing = []
    for package in PACKAGES:
        for module in sorted((ROOT / package).glob("*.py")):
            rel = f"{package}/{module.name}"
            if module.name == "__init__.py" and rel not in ALIASES:
                continue
            if not (TESTS / ALIASES.get(rel, rel)).exists():
                missing.append(rel)
    assert not missing, f"modules without tests: {missing}"


def every_engine_has_a_test_file():
    missing = [
        engine.key
        for engine in registry
        if not (TESTS / "engines" / f"{engine.key.replace('-', '_')}.py").exists()
    ]
    assert not missing, f"engines without tests/engines/<key>.py: {missing}"


def engine_files_follow_the_same_skeleton():
    wrong = {}
    for engine in registry:
        path = TESTS / "engines" / f"{engine.key.replace('-', '_')}.py"
        if not path.exists():
            continue
        head = _functions(path)[: len(ENGINE_SKELETON)]
        if head != ENGINE_SKELETON:
            wrong[path.name] = head
    assert not wrong, f"expected {ENGINE_SKELETON} first, got {wrong}"


def every_test_file_mirrors_a_module_or_an_engine():
    engines = {engine.key.replace("-", "_") for engine in registry}
    stray = []
    for path in sorted(TESTS.rglob("*.py")):
        rel = path.relative_to(TESTS).as_posix()
        if path.name == "__init__.py" or rel in SHARED:
            continue
        if (ROOT / rel).exists() or rel in ALIASES.values():
            continue
        if path.parent.name == "engines" and path.stem in engines:
            continue
        stray.append(rel)
    assert not stray, f"test files matching no module: {stray}"


def tests_have_no_prefix_and_no_classes():
    offenders = []
    for path in sorted(TESTS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                offenders.append(f"{path.name}::{node.name}")
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                offenders.append(f"{path.name}::{node.name}")
    assert not offenders, f"use plain names, no test_/Test prefix: {offenders}"
