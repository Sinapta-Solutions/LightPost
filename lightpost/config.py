"""Small, explicit configuration. No secrets are printed."""

import os
from dataclasses import dataclass
from pathlib import Path


def load_env(path=Path(".env")):
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.split("=", 1)
                os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


@dataclass
class Config:
    database: str = "data/lightpost.sqlite"
    host: str = "127.0.0.1"
    port: int = 3000
    password: str = ""
    key: str = ""
    secure_cookie: bool = False
    interval: float = 3
    scheduler: bool = True
    web_root: str = "web"

    @classmethod
    def from_env(cls):
        load_env()
        config = cls(
            database=os.getenv("DATABASE_PATH", "data/lightpost.sqlite"),
            host=os.getenv("HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", "3000")),
            password=os.getenv("ADMIN_PASSWORD", ""),
            key=os.getenv("ENCRYPTION_KEY", ""),
            web_root=os.getenv("WEB_ROOT", "web"),
            secure_cookie=os.getenv("COOKIE_SECURE") == "true",
        )
        if config.host not in ("127.0.0.1", "localhost", "::1") and len(config.password) < 8:
            raise ValueError("Set ADMIN_PASSWORD (8+ characters) before binding beyond loopback.")
        return config
