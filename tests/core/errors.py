import pytest

from core import errors
from core.crypto import DecryptionError

CODES = [
    (errors.PortabaseError, "E_GENERIC", 1),
    (errors.ValidationError, "E_VALIDATION", 2),
    (errors.ConfigError, "E_CONFIG", 3),
    (errors.DockerError, "E_DOCKER", 4),
    (errors.TemplateError, "E_TEMPLATE", 5),
    (errors.NetworkError, "E_NETWORK", 6),
    (errors.UpdateError, "E_UPDATE", 7),
    (DecryptionError, "E_CRYPTO", 8),
    (errors.UserAbort, "E_ABORT", 130),
]


@pytest.mark.parametrize(
    ("cls", "code", "exit_code"), CODES, ids=[case[0].__name__ for case in CODES]
)
def codes_and_exit_codes(cls, code, exit_code):
    assert issubclass(cls, errors.PortabaseError)
    assert (cls.code, cls.exit_code) == (code, exit_code)


def exit_codes_are_unique():
    exit_codes = [exit_code for _, _, exit_code in CODES]
    assert len(exit_codes) == len(set(exit_codes))


def message_hint_and_cause():
    cause = ValueError("boom")
    error = errors.ValidationError("Bad input.", hint="Try again.", cause=cause)
    assert str(error) == "Bad input."
    assert (error.message, error.hint, error.cause) == (
        "Bad input.",
        "Try again.",
        cause,
    )
    assert error.__cause__ is cause


def no_hint_and_no_cause_by_default():
    error = errors.ConfigError("Broken.")
    assert error.hint is None
    assert error.cause is None
    assert error.__cause__ is None


def user_abort_default_message():
    assert str(errors.UserAbort()) == "Canceled."
    assert errors.UserAbort(hint="Run it again.").hint == "Run it again."
