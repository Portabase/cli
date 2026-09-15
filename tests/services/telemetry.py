import pytest

from services.telemetry import NoopTelemetry, Telemetry


def telemetry_is_abstract():
    with pytest.raises(TypeError):
        Telemetry()


def noop_session_and_span_are_context_managers():
    telemetry = NoopTelemetry()
    with (
        telemetry.session(command="agent create") as session,
        telemetry.span("render", engine="postgresql") as span,
    ):
        assert (session, span) == (None, None)


def noop_span_lets_exceptions_through():
    with pytest.raises(ValueError, match="boom"), NoopTelemetry().span("render"):
        raise ValueError("boom")


def noop_records_nothing():
    telemetry = NoopTelemetry()
    assert telemetry.event("created", engine="redis") is None
    assert telemetry.error(ValueError("x"), unexpected=True) is None
    assert telemetry.flush() is None
