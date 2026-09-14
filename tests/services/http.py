import pytest
import requests

from core.errors import NetworkError
from services.http import HttpClient


class _Response:
    def __init__(self, *, status=200, text="", json=None, chunks=(), headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}
        self._json = json
        self._chunks = chunks

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")

    def json(self):
        if self._json is None:
            raise ValueError("Expecting value")
        return self._json

    def iter_content(self, chunk_size):
        for chunk in self._chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Session:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def _call(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response

    def get(self, url, **kwargs):
        return self._call("GET", url, kwargs)

    def head(self, url, **kwargs):
        return self._call("HEAD", url, kwargs)


def _client(**session):
    client = HttpClient(timeout=3)
    client.session = _Session(**session)
    return client


def user_agent_header():
    assert HttpClient(user_agent="ua/1").session.headers["User-Agent"] == "ua/1"


def get_json_returns_the_payload():
    client = _client(response=_Response(json={"a": 1}))
    assert client.get_json("https://x") == {"a": 1}
    assert client.session.calls == [("GET", "https://x", {"timeout": 3})]


@pytest.mark.parametrize(
    ("session", "message"),
    [
        ({"response": _Response(status=404)}, "GET https://x failed: 404"),
        ({"error": requests.ConnectionError("down")}, "GET https://x failed: down"),
        ({"response": _Response(json=None)}, "response is not JSON"),
    ],
    ids=["http-error", "connection-error", "not-json"],
)
def get_json_failures(session, message):
    with pytest.raises(NetworkError, match=message):
        _client(**session).get_json("https://x")


def get_text_returns_the_body():
    assert _client(response=_Response(text="hello")).get_text("https://x") == "hello"


def get_text_failure_has_a_hint():
    with pytest.raises(NetworkError) as exc:
        _client(response=_Response(status=500)).get_text("https://x")
    assert "internet connection" in (exc.value.hint or "")


def status_returns_the_code_without_raising():
    client = _client(response=_Response(status=503))
    assert client.status("https://x") == 503
    assert client.session.calls[0][2] == {"timeout": 3, "stream": True}


def status_connection_error():
    with pytest.raises(NetworkError):
        _client(error=requests.Timeout("slow")).status("https://x")


def download_writes_every_chunk(tmp_path):
    client = _client(response=_Response(chunks=[b"ab", b"", b"cde"]))
    dest = tmp_path / "file"
    progress = []
    assert client.download("https://x", dest, progress.append) == 5
    assert dest.read_bytes() == b"abcde"
    assert progress == [2, 3]
    assert client.session.calls[0][2] == {"stream": True, "timeout": 30.0}


def download_failure_removes_the_partial_file(tmp_path):
    chunks = [b"ab", requests.ConnectionError("cut")]
    dest = tmp_path / "file"
    with pytest.raises(NetworkError, match="Download of https://x failed: cut"):
        _client(response=_Response(chunks=chunks)).download("https://x", dest)
    assert not dest.exists()


def download_http_error(tmp_path):
    dest = tmp_path / "file"
    with pytest.raises(NetworkError):
        _client(response=_Response(status=404)).download("https://x", dest, timeout=5)
    assert not dest.exists()


@pytest.mark.parametrize(
    ("session", "expected"),
    [
        ({"response": _Response(headers={"content-length": "42"})}, 42),
        ({"response": _Response()}, None),
        ({"response": _Response(headers={"content-length": "abc"})}, None),
        ({"error": requests.ConnectionError("down")}, None),
    ],
    ids=["header", "no-header", "bad-header", "error"],
)
def content_length_cases(session, expected):
    client = _client(**session)
    assert client.content_length("https://x") == expected
    assert client.session.calls[0][:2] == ("HEAD", "https://x")
    assert client.session.calls[0][2]["allow_redirects"] is True
