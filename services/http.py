from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from core.errors import NetworkError

_HINT = "Check your internet connection or proxy settings."


class HttpClient:
    def __init__(
        self, timeout: float = 10.0, user_agent: str = "portabase-cli"
    ) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent

    def get_json(self, url: str) -> Any:
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            raise NetworkError(
                f"GET {url} failed: {error}", hint=_HINT, cause=error
            ) from error
        except ValueError as error:
            raise NetworkError(
                f"GET {url}: response is not JSON", cause=error
            ) from error

    def get_text(self, url: str) -> str:
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as error:
            raise NetworkError(
                f"GET {url} failed: {error}", hint=_HINT, cause=error
            ) from error

    def status(self, url: str) -> int:
        try:
            return self.session.get(url, timeout=self.timeout, stream=True).status_code
        except requests.RequestException as error:
            raise NetworkError(
                f"GET {url} failed: {error}", hint=_HINT, cause=error
            ) from error

    def download(
        self,
        url: str,
        dest: Path,
        on_progress: Callable[[int], None] | None = None,
        *,
        timeout: float = 30.0,
    ) -> int:
        written = 0
        try:
            with self.session.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                with open(dest, "wb") as file:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        file.write(chunk)
                        written += len(chunk)
                        if on_progress:
                            on_progress(len(chunk))
        except requests.RequestException as error:
            dest.unlink(missing_ok=True)
            raise NetworkError(
                f"Download of {url} failed: {error}", hint=_HINT, cause=error
            ) from error
        return written

    def content_length(self, url: str) -> int | None:
        try:
            response = self.session.head(
                url, timeout=self.timeout, allow_redirects=True
            )
            value = response.headers.get("content-length")
            return int(value) if value else None
        except (requests.RequestException, ValueError):
            return None
