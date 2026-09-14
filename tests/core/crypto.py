import base64
import json
import os
import struct

import pytest

from core.crypto import (
    DecryptionError,
    decrypt_enc_file,
    default_output_for,
    load_master_key,
)
from tests.support import encrypt

KEY = bytes(range(32))
HEADER = {"cipher": "AES-256-GCM", "base_nonce": list(range(8)), "chunk_size": 4}


def _header(**overrides) -> bytes:
    return json.dumps({**HEADER, **overrides}).encode() + b"\n"


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "backup.sql.enc", tmp_path / "out" / "backup.sql"


def load_master_key_raw(tmp_path):
    path = tmp_path / "master_key.bin"
    path.write_bytes(KEY)
    assert load_master_key(path) == KEY


def load_master_key_base64(tmp_path):
    path = tmp_path / "master_key.bin"
    path.write_bytes(base64.b64encode(KEY) + b"\n")
    assert load_master_key(path) == KEY


def load_master_key_defaults_to_cwd(tmp_path, monkeypatch):
    (tmp_path / "master_key.bin").write_bytes(KEY)
    monkeypatch.chdir(tmp_path)
    assert load_master_key(None) == KEY


@pytest.mark.parametrize(
    "content", [b"short", b"not base64 !!", base64.b64encode(b"x" * 16)]
)
def load_master_key_rejects_wrong_length(tmp_path, content):
    path = tmp_path / "master_key.bin"
    path.write_bytes(content)
    with pytest.raises(DecryptionError, match="32-byte"):
        load_master_key(path)


def load_master_key_missing(tmp_path):
    with pytest.raises(DecryptionError, match="not found"):
        load_master_key(tmp_path / "nope.bin")


def load_master_key_directory(tmp_path):
    with pytest.raises(DecryptionError, match="not a file"):
        load_master_key(tmp_path)


@pytest.mark.parametrize("plain", [b"", b"abc", b"exactly8", os.urandom(1000)])
def decrypt_round_trip(paths, plain):
    enc, out = paths
    enc.write_bytes(encrypt(plain, KEY, chunk_size=4))
    decrypt_enc_file(enc, out, KEY)
    assert out.read_bytes() == plain
    assert not out.with_name(out.name + ".part").exists()


def decrypt_wrong_key_keeps_previous_output(paths):
    enc, out = paths
    enc.write_bytes(encrypt(b"secret data", KEY))
    out.parent.mkdir()
    out.write_bytes(b"previous")
    with pytest.raises(DecryptionError, match="Authentication failed on chunk 0"):
        decrypt_enc_file(enc, out, bytes(32))
    assert out.read_bytes() == b"previous"
    assert not out.with_name(out.name + ".part").exists()


def decrypt_detects_reordered_chunks(paths):
    enc, out = paths
    head, body = encrypt(b"aaaabbbb", KEY, chunk_size=4).split(b"\n", 1)
    size = 4 + 4 + 16
    enc.write_bytes(head + b"\n" + body[size : 2 * size] + body[:size])
    with pytest.raises(DecryptionError, match="Authentication failed"):
        decrypt_enc_file(enc, out, KEY)
    assert not out.exists()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "missing header"),
        (b"nope\n", "Invalid or missing JSON header"),
        (_header(cipher="AES-128-CBC"), "Unsupported cipher"),
        (_header(base_nonce=[1, 2]), "Invalid base_nonce length"),
        (_header() + b"\x00\x00", "Truncated chunk length prefix"),
        (_header() + struct.pack(">I", 4) + b"1234", "smaller than the 16-byte tag"),
        (_header() + struct.pack(">I", 1000), "exceeds the maximum 20 bytes"),
        (_header() + struct.pack(">I", 20) + b"short", "Truncated chunk 0"),
    ],
)
def decrypt_rejects_corrupt_files(paths, content, message):
    enc, out = paths
    enc.write_bytes(content)
    with pytest.raises(DecryptionError, match=message):
        decrypt_enc_file(enc, out, KEY)
    assert not out.exists()
    assert not out.with_name(out.name + ".part").exists()


def decrypt_truncated_last_chunk(paths):
    enc, out = paths
    enc.write_bytes(encrypt(b"abcdefgh", KEY)[:-1])
    with pytest.raises(DecryptionError, match="Truncated chunk 1"):
        decrypt_enc_file(enc, out, KEY)


@pytest.mark.parametrize(
    ("name", "expected"),
    [("dump.sql.enc", "dump.sql"), ("dump.enc", "dump"), ("dump.sql", "dump.sql.dec")],
)
def default_output_name(tmp_path, name, expected):
    assert default_output_for(tmp_path / name) == expected


def decryption_error_exit_code():
    assert (DecryptionError.code, DecryptionError.exit_code) == ("E_CRYPTO", 8)
