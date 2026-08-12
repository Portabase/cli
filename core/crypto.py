"""AES-256-GCM decryption for Portabase ``.enc`` backup files.

The ``.enc`` format is produced by the Rust encryption pipeline. Layout::

    {"version":1,"cipher":"AES-256-GCM","chunk_size":16777216,"base_nonce":[...8 bytes...]}\n
    [u32 big-endian ciphertext length][ciphertext + 16-byte GCM tag]   # chunk 0
    [u32 big-endian ciphertext length][ciphertext + 16-byte GCM tag]   # chunk 1
    ...

* First line is a compact JSON header terminated by ``\n``.
* Each subsequent chunk is a 4-byte big-endian length prefix followed by the
  AES-256-GCM ciphertext with the authentication tag appended (as emitted by
  the Rust ``aes-gcm`` crate).
* The 12-byte nonce for chunk ``i`` is ``base_nonce (8 bytes) || i (u32 BE)``.
* The master key is the raw 32-byte AES-256 key. No key derivation is applied;
  the Rust side base64-decodes ``masterKeyB64`` to obtain these same 32 bytes.
"""

import base64
import json
import os
import struct
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENC_SUFFIX = ".enc"
DEFAULT_KEY_FILENAME = "master_key.bin"
CIPHER_NAME = "AES-256-GCM"
_BASE_NONCE_LEN = 8
_LEN_PREFIX_LEN = 4
_AES_256_KEY_LEN = 32
_TAG_LEN = 16
# Hard ceiling on a single chunk's plaintext, used when the header's declared
# chunk_size is missing or implausible. Bounds per-chunk allocation so a corrupt
# length prefix can never force an arbitrarily large read on a multi-GB file.
_MAX_CHUNK_PLAINTEXT = 256 * 1024 * 1024
# Copy plaintext to disk in bounded slices so a large chunk is never handed to
# the OS write path as one giant buffer.
_WRITE_SLICE = 4 * 1024 * 1024


class DecryptionError(Exception):
    """Raised when a ``.enc`` file cannot be decrypted."""


def load_master_key(key_path: Path | None) -> bytes:
    """Load the raw 32-byte AES-256 key from ``key_path``.

    When ``key_path`` is ``None`` the key file is looked up as
    ``master_key.bin`` in the current working directory. The file may hold
    either the raw 32 key bytes or the STANDARD base64 encoding of them.
    """
    if key_path is None:
        key_path = Path.cwd() / DEFAULT_KEY_FILENAME

    if not key_path.exists():
        raise DecryptionError(f"Master key file not found: {key_path}")
    if not key_path.is_file():
        raise DecryptionError(f"Master key path is not a file: {key_path}")

    raw = key_path.read_bytes()

    # Raw 32-byte key (as produced by the test/backup tooling).
    if len(raw) == _AES_256_KEY_LEN:
        return raw

    # Otherwise try to interpret the file as base64 text (masterKeyB64).
    try:
        decoded = base64.standard_b64decode(raw.strip())
    except Exception:  # binascii.Error / ValueError on malformed base64
        decoded = b""
    if len(decoded) == _AES_256_KEY_LEN:
        return decoded

    raise DecryptionError(
        f"Invalid master key in {key_path}: expected a 32-byte AES-256 key "
        f"(raw or base64), got {len(raw)} bytes."
    )


def _read_header(handle) -> tuple[bytes, int]:
    """Read and validate the JSON header line.

    Returns ``(base_nonce, chunk_size)`` where ``chunk_size`` is the declared
    plaintext chunk size, clamped to a safe ceiling. It bounds how many bytes a
    single chunk read may allocate regardless of total file size.
    """
    header_line = handle.readline()
    if not header_line:
        raise DecryptionError("File is empty: missing header.")
    try:
        header = json.loads(header_line)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DecryptionError(f"Invalid or missing JSON header: {exc}") from exc

    cipher = header.get("cipher")
    if cipher != CIPHER_NAME:
        raise DecryptionError(f"Unsupported cipher: {cipher!r} (expected {CIPHER_NAME}).")

    base_nonce = bytes(header.get("base_nonce", []))
    if len(base_nonce) != _BASE_NONCE_LEN:
        raise DecryptionError(
            f"Invalid base_nonce length: {len(base_nonce)} (expected {_BASE_NONCE_LEN})."
        )

    chunk_size = header.get("chunk_size")
    if not isinstance(chunk_size, int) or not 0 < chunk_size <= _MAX_CHUNK_PLAINTEXT:
        # Unknown or implausible declared size: fall back to the hard ceiling as
        # the per-chunk allocation limit rather than trusting the file.
        chunk_size = _MAX_CHUNK_PLAINTEXT
    return base_nonce, chunk_size


def decrypt_enc_file(enc_path: Path, out_path: Path, key: bytes) -> None:
    """Decrypt a single ``.enc`` file to ``out_path``.

    The plaintext is written to a temporary sibling file first and atomically
    renamed on success, so a failure never leaves a partial output behind.
    Raises :class:`DecryptionError` on any format or authentication failure.
    """
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
                        break  # clean end of stream
                    if len(len_buf) != _LEN_PREFIX_LEN:
                        raise DecryptionError("Truncated chunk length prefix.")

                    chunk_len = struct.unpack(">I", len_buf)[0]
                    # Bound the allocation before reading: a corrupt prefix must
                    # not be able to trigger a multi-GB read on a large file.
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

                    # Release the ciphertext buffer before writing the plaintext,
                    # then write in bounded slices to keep the footprint flat.
                    del ciphertext
                    for start in range(0, len(plaintext), _WRITE_SLICE):
                        dst.write(plaintext[start : start + _WRITE_SLICE])
                    chunk_index += 1

        os.replace(tmp_path, out_path)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def default_output_for(enc_path: Path) -> str:
    """Return the plaintext filename for ``enc_path`` (strips a trailing ``.enc``)."""
    name = enc_path.name
    if name.endswith(ENC_SUFFIX):
        return name[: -len(ENC_SUFFIX)]
    return name + ".dec"
