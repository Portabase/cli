import dataclasses

import pytest

from core.fields import Field


def defaults():
    field = Field("name", "Prompt")
    assert (field.kind, field.default, field.choices, field.help, field.validator) == (
        "text",
        None,
        (),
        None,
        None,
    )


@pytest.mark.parametrize(
    ("name", "flag"),
    [("key", "--key"), ("retry_attempts", "--retry-attempts"), ("a_b_c", "--a-b-c")],
)
def flag_uses_dashes(name, flag):
    assert Field(name, "Prompt").flag == flag


def is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Field("a", "A").name = "b"
