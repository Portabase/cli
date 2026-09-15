from __future__ import annotations


class PortabaseError(Exception):
    code: str = "E_GENERIC"
    exit_code: int = 1

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause

    def __str__(self) -> str:
        return self.message


class UserAbort(PortabaseError):
    code = "E_ABORT"
    exit_code = 130

    def __init__(self, message: str = "Canceled.", **kwargs) -> None:
        super().__init__(message, **kwargs)


class ValidationError(PortabaseError):
    code = "E_VALIDATION"
    exit_code = 2


class ConfigError(PortabaseError):
    code = "E_CONFIG"
    exit_code = 3


class DockerError(PortabaseError):
    code = "E_DOCKER"
    exit_code = 4


class TemplateError(PortabaseError):
    code = "E_TEMPLATE"
    exit_code = 5


class NetworkError(PortabaseError):
    code = "E_NETWORK"
    exit_code = 6


class UpdateError(PortabaseError):
    code = "E_UPDATE"
    exit_code = 7
