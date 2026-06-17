import os, time, uuid, hmac
import jwt
from fastapi import Header, HTTPException
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "")
STAFF_PASSWORD = os.getenv("STAFF_PASSWORD", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_SECONDS = 30 * 60  # 30 min — keeps the revocation window small

# Demo-grade revocation store (jti -> token expiry epoch).
# In production use Redis with per-jti TTL so it self-cleans AND works
# across multiple server instances. An in-memory dict only works single-process.
_revoked: dict[str, float] = {}


def _purge_expired():
    now = time.time()
    for jti, exp in list(_revoked.items()):
        if exp < now:
            _revoked.pop(jti, None)


def verify_staff_password(password: str) -> bool:
    if not STAFF_PASSWORD:
        raise HTTPException(status_code=500, detail="Staff password not configured")
    return hmac.compare_digest(password, STAFF_PASSWORD)  # constant-time, anti-timing


def create_access_token() -> dict:
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT secret not configured")
    now = int(time.time())
    payload = {
        "sub": "staff",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL_SECONDS,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {"access_token": token, "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_TTL_SECONDS}


async def verify_token(authorization: str = Header(...)) -> dict:
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT secret not configured")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token, JWT_SECRET,
            algorithms=[JWT_ALGORITHM],                  # explicit -> blocks alg=none attack
            options={"require": ["exp", "iat", "jti"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    _purge_expired()
    if payload["jti"] in _revoked:
        raise HTTPException(status_code=401, detail="Token revoked")
    return payload


def revoke_token(payload: dict):
    _revoked[payload["jti"]] = payload.get("exp", time.time())