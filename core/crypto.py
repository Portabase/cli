import base64
import contextlib
import json
import os
import struct
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.errors import PortabaseError

ENC_SUFFIX = ".enc"
DEFAULT_KEY_FILENAME = "master_key.bin"
CIPHER_NAME = "AES-256-GCM"
_BASE_NONCE_LEN = 8
_LEN_PREFIX_LEN = 4
_AES_256_KEY_LEN = 32
_TAG_LEN = 16
_MAX_CHUNK_PLAINTEXT = 256 * 1024 * 1024
_WRITE_SLICE = 4 * 1024 * 1024


class DecryptionError(PortabaseError):
    code = "E_CRYPTO"
    exit_code = 8


def load_master_key(key_path: Path | None) -> bytes:
    if key_path is None:
        key_path = Path.cwd() / DEFAULT_KEY_FILENAME

    if not key_path.exists():
        raise DecryptionError(f"Master key file not found: {key_path}")
    if not key_path.is_file():
        raise DecryptionError(f"Master key path is not a file: {key_path}")

    raw = key_path.read_bytes()

    if len(raw) == _AES_256_KEY_LEN:
        return raw

    try:
        decoded = base64.standard_b64decode(raw.strip())
    except ValueError:
        decoded = b""
    if len(decoded) == _AES_256_KEY_LEN:
        return decoded

    raise DecryptionError(
        f"Invalid master key in {key_path}: expected a 32-byte AES-256 key "
        f"(raw or base64), got {len(raw)} bytes."
    )


def _read_header(handle) -> tuple[bytes, int]:
    header_line = handle.readline()
    if not header_line:
        raise DecryptionError("File is empty: missing header.")
    try:
        header = json.loads(header_line)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DecryptionError(f"Invalid or missing JSON header: {exc}") from exc

    cipher = header.get("cipher")
    if cipher != CIPHER_NAME:
        raise DecryptionError(
            f"Unsupported cipher: {cipher!r} (expected {CIPHER_NAME})."
        )

    base_nonce = bytes(header.get("base_nonce", []))
    if len(base_nonce) != _BASE_NONCE_LEN:
        raise DecryptionError(
            f"Invalid base_nonce length: {len(base_nonce)} (expected {_BASE_NONCE_LEN})."
        )

    chunk_size = header.get("chunk_size")
    if not isinstance(chunk_size, int) or not 0 < chunk_size <= _MAX_CHUNK_PLAINTEXT:
        chunk_size = _MAX_CHUNK_PLAINTEXT
    return base_nonce, chunk_size


def decrypt_enc_file(enc_path: Path, out_path: Path, key: bytes) -> None:
    aesgcm = AESGCM(key)
    tmp_path = out_path.with_name(out_path.name + ".part")

    try:
        with open(enc_path, "rb") as src:
            base_nonce, chunk_size = _read_header(src)
            max_ciphertext = chunk_size + _TAG_LEN

            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "wb") as dst:
                chunk_index = 0
                while True:
                    len_buf = src.read(_LEN_PREFIX_LEN)
                    if not len_buf:
                        break
                    if len(len_buf) != _LEN_PREFIX_LEN:
                        raise DecryptionError("Truncated chunk length prefix.")

                    chunk_len = struct.unpack(">I", len_buf)[0]
                    if chunk_len < _TAG_LEN:
                        raise DecryptionError(
                            f"Chunk {chunk_index} length {chunk_len} is smaller than "
                            f"the {_TAG_LEN}-byte tag (corrupt file)."
                        )
                    if chunk_len > max_ciphertext:
                        raise DecryptionError(
                            f"Chunk {chunk_index} length {chunk_len} exceeds the maximum "
                            f"{max_ciphertext} bytes (corrupt file or wrong format)."
                        )

                    ciphertext = src.read(chunk_len)
                    if len(ciphertext) != chunk_len:
                        raise DecryptionError(
                            f"Truncated chunk {chunk_index}: expected {chunk_len} bytes, "
                            f"got {len(ciphertext)}."
                        )

                    nonce = base_nonce + struct.pack(">I", chunk_index)
                    try:
                        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
                    except InvalidTag as exc:
                        raise DecryptionError(
                            f"Authentication failed on chunk {chunk_index} "
                            "(wrong key or corrupt data)."
                        ) from exc

                    del ciphertext
                    for start in range(0, len(plaintext), _WRITE_SLICE):
                        dst.write(plaintext[start : start + _WRITE_SLICE])
                    chunk_index += 1

        os.replace(tmp_path, out_path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)
        raise


def default_output_for(enc_path: Path) -> str:
    name = enc_path.name
    if name.endswith(ENC_SUFFIX):
        return name[: -len(ENC_SUFFIX)]
    return name + ".dec"
