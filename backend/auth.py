from __future__ import annotations

import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

from backend.database import get_db

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TOKEN_TTL_DAYS = 7


def _collections():
    db = get_db()
    users = db["user_accounts"]
    sessions = db["user_sessions"]
    users.create_index("email", unique=True)
    sessions.create_index("token_hash", unique=True)
    sessions.create_index("expires_at", expireAfterSeconds=0)
    sessions.create_index("user_id")
    return users, sessions


def _public_user(user: dict) -> dict:
    admin_emails = {
        item.strip().lower()
        for item in os.getenv("ADMIN_EMAILS", "").split(",")
        if item.strip()
    }
    return {
        "id": str(user["_id"]),
        "name": user["name"],
        "email": user["email"],
        "created_at": user["created_at"].isoformat(),
        "is_admin": user["email"] in admin_emails,
    }


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_session(user: dict) -> dict:
    _, sessions = _collections()
    token = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=TOKEN_TTL_DAYS)
    sessions.insert_one({
        "token_hash": _token_hash(token),
        "user_id": user["_id"],
        "created_at": now,
        "expires_at": expires_at,
    })
    return {"token": token, "user": _public_user(user)}


def register_user(name: str, email: str, password: str) -> dict:
    if not isinstance(name, str) or not isinstance(email, str) or not isinstance(password, str):
        raise ValueError("Name, email, and password are required.")
    name = name.strip()
    email = email.strip().lower()
    if not 1 <= len(name) <= 80:
        raise ValueError("Name must contain 1 to 80 characters.")
    if len(email) > 254 or not EMAIL_RE.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    if len(password) < 12 or len(password) > 128:
        raise ValueError("Password must contain 12 to 128 characters.")

    users, _ = _collections()
    user = {
        "name": name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = users.insert_one(user)
    except DuplicateKeyError as exc:
        raise ValueError("An account with this email already exists.") from exc
    user["_id"] = result.inserted_id
    return _create_session(user)


def login_user(email: str, password: str) -> dict:
    if not isinstance(email, str) or not isinstance(password, str):
        raise ValueError("Email and password are required.")
    users, _ = _collections()
    user = users.find_one({"email": email.strip().lower()})
    # Keep the error generic so the endpoint does not reveal account existence.
    if not user or not check_password_hash(user["password_hash"], password):
        raise ValueError("Invalid email or password.")
    return _create_session(user)


def get_user_for_token(token: str | None) -> dict | None:
    if not token or not isinstance(token, str) or len(token) > 256:
        return None
    users, sessions = _collections()
    now = datetime.now(timezone.utc)
    session = sessions.find_one({
        "token_hash": _token_hash(token),
        "expires_at": {"$gt": now},
    })
    if not session:
        return None
    user = users.find_one({"_id": session["user_id"]})
    return user


def get_request_user(request) -> dict | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return get_user_for_token(token.strip())


def logout_token(token: str | None) -> None:
    if not token or not isinstance(token, str) or len(token) > 256:
        return
    _, sessions = _collections()
    sessions.delete_one({"token_hash": _token_hash(token)})
