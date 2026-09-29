import hashlib
import hmac
import os
import time
import uuid

import jwt
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_SECONDS = 30 * 60  # 30 min — keeps the revocation window small

# Revocation store (jti -> token expiry epoch).
# ponytail: in-memory, single process only. On serverless or multiple workers a
# logout is only honoured by the process that received it; move to Redis with
# per-jti TTL if that matters.
_revoked: dict[str, float] = {}

_SCRYPT = dict(n=2**14, r=8, p=1)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return hmac.compare_digest(candidate.hex(), digest)  # constant-time


# Checked against when the username doesn't exist, so response time doesn't
# reveal which usernames are valid.
DUMMY_HASH = hash_password(uuid.uuid4().hex)


def _purge_expired():
    now = time.time()
    for jti, exp in list(_revoked.items()):
        if exp < now:
            _revoked.pop(jti, None)


def create_access_token(username: str, role: str) -> dict:
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT secret not configured")
    now = int(time.time())
    payload = {
        "sub": username,
        "role": role,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL_SECONDS,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"access_token": token, "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_TTL_SECONDS, "username": username, "role": role}


async def verify_token(authorization: str | None = Header(None)) -> dict:
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT secret not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token, JWT_SECRET,
            algorithms=[JWT_ALGORITHM],                  # explicit -> blocks alg=none attack
            options={"require": ["exp", "iat", "jti", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token") from None

    _purge_expired()
    if payload["jti"] in _revoked:
        raise HTTPException(status_code=401, detail="Token revoked")
    return payload


async def require_admin(staff: dict = Depends(verify_token)) -> dict:
    if staff.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return staff


def revoke_token(payload: dict):
    _revoked[payload["jti"]] = payload.get("exp", time.time())
