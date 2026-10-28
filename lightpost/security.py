import json
import os
import re
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class Vault:
    """Encrypt account credentials with AES-256-GCM."""

    def __init__(self, key="", directory="data"):
        if not key:
            path = Path(directory) / "credentials.key"
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                key = path.read_text().strip()
            else:
                key = os.urandom(32).hex()
                with os.fdopen(fd, "w") as file:
                    file.write(key)
        if not re.fullmatch(r"[a-fA-F0-9]{64}", key):
            raise ValueError("ENCRYPTION_KEY must be exactly 64 hexadecimal characters.")
        self.cipher = AESGCM(bytes.fromhex(key))

    def encrypt(self, value):
        nonce = os.urandom(12)
        encrypted = self.cipher.encrypt(nonce, json.dumps(value).encode(), None)
        return ":".join((nonce.hex(), encrypted[-16:].hex(), encrypted[:-16].hex()))

    def decrypt(self, value):
        try:
            nonce, tag, data = (bytes.fromhex(part) for part in value.split(":"))
            return json.loads(self.cipher.decrypt(nonce, data + tag, None))
        except Exception:
            raise ValueError(
                "Cannot unlock this account. Restore its original encryption key or reconnect it."
            ) from None
