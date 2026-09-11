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
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            raise NetworkError(f"GET {url} failed: {e}", hint=_HINT, cause=e) from e
        except ValueError as e:
            raise NetworkError(f"GET {url}: response is not JSON", cause=e) from e

    def get_text(self, url: str) -> str:
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            raise NetworkError(f"GET {url} failed: {e}", hint=_HINT, cause=e) from e

    def status(self, url: str) -> int:
        try:
            return self.session.get(url, timeout=self.timeout, stream=True).status_code
        except requests.RequestException as e:
            raise NetworkError(f"GET {url} failed: {e}", hint=_HINT, cause=e) from e

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
            with self.session.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        written += len(chunk)
                        if on_progress:
                            on_progress(len(chunk))
        except requests.RequestException as e:
            dest.unlink(missing_ok=True)
            raise NetworkError(
                f"Download of {url} failed: {e}", hint=_HINT, cause=e
            ) from e
        return written

    def content_length(self, url: str) -> int | None:
        try:
            r = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            value = r.headers.get("content-length")
            return int(value) if value else None
        except (requests.RequestException, ValueError):
            return None
