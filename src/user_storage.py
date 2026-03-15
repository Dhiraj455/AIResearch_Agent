"""User storage: register and lookup users by email/id."""

import json
import uuid
from pathlib import Path

import bcrypt

from src.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _users_path() -> Path:
    Path(settings.USERS_DIR).mkdir(parents=True, exist_ok=True)
    return Path(settings.USERS_DIR) / "users.json"


def _load_users() -> dict:
    p = _users_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_users(users: dict) -> None:
    _users_path().write_text(json.dumps(users, indent=2), encoding="utf-8")


def _email_key(email: str) -> str:
    return email.strip().lower()


def register_user(email: str, password: str) -> dict:
    """
    Register a new user. Returns user dict with id, email, created_at.
    Raises ValueError if email already exists.
    """
    users = _load_users()
    key = _email_key(email)
    if key in users:
        raise ValueError("Email already registered")
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "email": email.strip(),
        "password_hash": hash_password(password),
        "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
    users[key] = user
    _save_users(users)
    return {"id": user_id, "email": user["email"], "created_at": user["created_at"]}


def get_user_by_email(email: str) -> dict | None:
    """Get user by email (case-insensitive)."""
    users = _load_users()
    return users.get(_email_key(email))


def get_user_by_id(user_id: str) -> dict | None:
    """Get user by id. Returns user dict without password_hash for safety."""
    users = _load_users()
    for u in users.values():
        if u["id"] == user_id:
            return {"id": u["id"], "email": u["email"], "created_at": u["created_at"]}
    return None
