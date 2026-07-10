import os
import hashlib
import bcrypt
import jwt
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import Request, HTTPException, Depends
from database import db

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {"sub": user_id, "email": email, "role": role,
               "exp": datetime.now(timezone.utc) + timedelta(hours=8), "type": "access"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def hash_service_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def log_authz(actor: dict, action: str, resource: str, allowed: bool, reason: str = ""):
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "actor_type": actor.get("type", "anonymous"),
        "actor_id": actor.get("id", ""),
        "actor_name": actor.get("name", ""),
        "role": actor.get("role", ""),
        "action": action,
        "resource": resource,
        "allowed": allowed,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def get_current_actor(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if token.startswith("svc_"):
        identity = await db.identities.find_one({"token_hash": hash_service_token(token), "active": True}, {"_id": 0})
        if not identity:
            raise HTTPException(status_code=401, detail="Invalid service token")
        return {"type": "service", "id": identity["agent_id"], "name": identity["name"],
                "role": "service", "scopes": identity.get("scopes", [])}

    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return {"type": "human", "id": user["id"], "email": user["email"],
                "name": user.get("name", ""), "role": user.get("role", "reader")}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_admin(actor: dict = Depends(get_current_actor)) -> dict:
    if actor["role"] != "admin":
        await log_authz(actor, "admin_access", "admin", False, "role is not admin")
        raise HTTPException(status_code=403, detail="Admin role required")
    return actor


async def require_registry_writer(actor: dict = Depends(get_current_actor)) -> dict:
    """Rule: only Agent 000 (service identity) or an admin acting on its behalf writes to the Registry."""
    is_agent000 = actor["type"] == "service" and actor["id"] == "AGT-000"
    is_admin = actor["type"] == "human" and actor["role"] == "admin"
    if not (is_agent000 or is_admin):
        await log_authz(actor, "registry_write", "registry", False,
                        "only AGT-000 service identity or admin may write to the Registry")
        raise HTTPException(status_code=403, detail="Registry write restricted to Agent 000 or admin")
    return actor
