import base64
import binascii
import json
import re
import secrets
import string


def generate_password(length: int = 16) -> str:

    if length < 8:
        length = 8

    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#%^&*()-_=+[]{}|;:,.<>?"

    password = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]

    all_chars = lower + upper + digits + symbols
    password += [secrets.choice(all_chars) for _ in range(length - 4)]

    secrets.SystemRandom().shuffle(password)

    return "".join(password)


def slugify_project_name(value: str, fallback: str = "portabase") -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.lower())
    slug = slug.strip("-_")
    slug = re.sub(r"^[^a-z0-9]+", "", slug)

    return slug or fallback


def validate_edge_key(key: str) -> bool:
    try:
        try:
            decoded_bytes = base64.b64decode(key, validate=True)
            decoded_str = decoded_bytes.decode("utf-8")
            data = json.loads(decoded_str)
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
            try:
                data = json.loads(key)
            except json.JSONDecodeError:
                return False

        required_fields = ["serverUrl", "agentId", "masterKeyB64"]
        return all(field in data for field in required_fields)
    except TypeError:
        return False
