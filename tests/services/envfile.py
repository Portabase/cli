import pytest

from services.envfile import EnvFile

SAMPLE = r"""# comment
export A=1
B = "two words"
C='single # kept'
D=plain # trailing comment
E="esc \"q\" back\\slash"
#F=commented

G=
"""


@pytest.fixture
def env(tmp_path):
    path = tmp_path / ".env"
    path.write_text(SAMPLE, encoding="utf-8")
    return EnvFile.load(path)


def missing_file(tmp_path):
    env = EnvFile.load(tmp_path / ".env")
    assert not env.exists
    assert env.as_dict() == {}
    assert env.get("A", "default") == "default"


def parse(env):
    assert env.as_dict() == {
        "A": "1",
        "B": "two words",
        "C": "single # kept",
        "D": "plain",
        "E": 'esc "q" back\\slash',
        "G": "",
    }
    assert env.get("F") is None


def last_duplicate_wins(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=1\nA=2\n", encoding="utf-8")
    assert EnvFile.load(path).get("A") == "2"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "simple",
        "with space",
        'quote"inside',
        "back\\slash",
        "ends\\",
        '\\"',
        "hash # x",
        "a=b",
        "'single'",
    ],
)
def set_save_load_round_trip(tmp_path, value):
    env = EnvFile.load(tmp_path / ".env")
    env.set("KEY", value)
    env.save()
    assert EnvFile.load(tmp_path / ".env").get("KEY") == value


def set_existing_key_keeps_position_and_comments(env):
    env.set("B", "new")
    env.set("Z", "added")
    env.save()
    lines = env.path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# comment"
    assert lines[2] == 'B="new"'
    assert lines[-1] == 'Z="added"'


def merge_overrides_and_adds(env):
    env.merge({"A": "10", "NEW": "x"})
    assert env.get("A") == "10"
    assert env.get("NEW") == "x"


def remove_keeps_index_consistent(env):
    env.remove("B")
    env.remove("missing")
    env.set("D", "changed")
    assert env.get("B") is None
    assert env.get("A") == "1"
    assert env.get("C") == "single # kept"
    assert env.get("D") == "changed"
    env.save()
    assert "B =" not in env.path.read_text(encoding="utf-8")
    assert EnvFile.load(env.path).get("D") == "changed"


def remove_prefix_only_removes_that_prefix(tmp_path):
    env = EnvFile.load(tmp_path / ".env")
    env.merge(
        {
            "AUTH_OIDC_KC": "kept",
            "AUTH_OIDC_KC_ID": "kc",
            "AUTH_OIDC_KC_SECRET": "s",
            "AUTH_OIDC_KCX_ID": "kept",
            "OTHER": "kept",
        }
    )
    env.remove_prefix("AUTH_OIDC_KC")
    assert env.as_dict() == {
        "AUTH_OIDC_KC": "kept",
        "AUTH_OIDC_KCX_ID": "kept",
        "OTHER": "kept",
    }


def save_creates_parent_and_ends_with_newline(tmp_path):
    env = EnvFile.load(tmp_path / "nested" / ".env")
    env.set("A", "1")
    env.save()
    assert env.exists
    assert env.path.read_text(encoding="utf-8") == 'A="1"\n'
    assert not (tmp_path / "nested" / ".env.tmp").exists()
