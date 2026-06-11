"""User store – simple JSON-file-backed user database.

Each user record stores a SHA-256 hash of the password for verification.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class UserInfo:
    username: str
    password_hash: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class UserStore:
    def __init__(self, path: Path):
        self._path = path
        self._users: dict[str, UserInfo] = {}
        self._load()

    # -- public API --

    def register(self, username: str, password: str) -> tuple[bool, str]:
        """Register a new user. Returns (success, message)."""
        if not username.strip():
            return False, "Username cannot be empty."
        if len(password) < 4:
            return False, "Password must be at least 4 characters."
        if username in self._users:
            return False, "Username already exists."
        self._users[username] = UserInfo(
            username=username,
            password_hash=_hash_password(password),
        )
        self._save()
        return True, "Registration successful."

    def authenticate(self, username: str, password: str) -> tuple[bool, str]:
        """Verify credentials. Returns (success, message)."""
        user = self._users.get(username)
        if not user:
            return False, "Invalid username or password."
        if user.password_hash != _hash_password(password):
            return False, "Invalid username or password."
        return True, "Login successful."

    def user_exists(self, username: str) -> bool:
        return username in self._users

    def list_users(self) -> list[dict]:
        return [
            {"username": u.username, "created_at": u.created_at}
            for u in self._users.values()
        ]

    # -- persistence --

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for record in data.get("users", []):
                self._users[record["username"]] = UserInfo(
                    username=record["username"],
                    password_hash=record["password_hash"],
                    created_at=record.get("created_at", ""),
                )
        except Exception:
            pass

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "users": [
                    {"username": u.username, "password_hash": u.password_hash, "created_at": u.created_at}
                    for u in self._users.values()
                ]
            }
            self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()