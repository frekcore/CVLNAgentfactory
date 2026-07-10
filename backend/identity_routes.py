import uuid
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Response
from pydantic import BaseModel, EmailStr
from database import db
from auth_utils import (hash_password, verify_password, create_access_token,
                        hash_service_token, get_current_actor, require_admin, log_authz)
from event_bus import publish

router = APIRouter(tags=["identity"])

VALID_ROLES = ["admin", "operator", "reader"]


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "reader"


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    password: str | None = None


class ServiceIdentityCreate(BaseModel):
    agent_id: str
    name: str
    scopes: list[str] = []


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@router.post("/auth/login")
async def login(payload: LoginPayload, response: Response):
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        await log_authz({"type": "anonymous", "id": email}, "login", "identity", False, "invalid credentials")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"], user["role"])
    response.set_cookie(key="access_token", value=token, httponly=True, secure=True,
                        samesite="none", max_age=28800, path="/")
    await log_authz({"type": "human", "id": user["id"], "name": user.get("name", ""), "role": user["role"]},
                    "login", "identity", True, "login success")
    return {"access_token": token, "user": {"id": user["id"], "email": user["email"],
            "name": user.get("name", ""), "role": user["role"]}}


@router.post("/auth/logout")
async def logout(response: Response, actor: dict = Depends(get_current_actor)):
    response.delete_cookie("access_token", path="/")
    return {"result": "ok"}


@router.get("/auth/me")
async def me(actor: dict = Depends(get_current_actor)):
    return actor


@router.get("/users")
async def list_users(actor: dict = Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
    return users


@router.post("/users")
async def create_user(payload: UserCreate, actor: dict = Depends(require_admin)):
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of {VALID_ROLES}")
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email already exists")
    user = {"id": str(uuid.uuid4()), "email": email, "name": payload.name,
            "role": payload.role, "created_at": now_iso()}
    await db.users.insert_one({**user, "password_hash": hash_password(payload.password)})
    await log_authz(actor, "user_create", f"user:{email}", True, f"role={payload.role}")
    await publish("identity.user_created", actor["id"], {"email": email, "role": payload.role})
    return user


@router.patch("/users/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, actor: dict = Depends(require_admin)):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    update = {}
    if payload.name:
        update["name"] = payload.name
    if payload.role:
        if payload.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Role must be one of {VALID_ROLES}")
        update["role"] = payload.role
    if payload.password:
        update["password_hash"] = hash_password(payload.password)
    if update:
        await db.users.update_one({"id": user_id}, {"$set": update})
        await log_authz(actor, "user_update", f"user:{user['email']}", True, str(list(update.keys())))
    return {"result": "ok"}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, actor: dict = Depends(require_admin)):
    if user_id == actor["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await log_authz(actor, "user_delete", f"user:{user_id}", True, "")
    return {"result": "ok"}


@router.get("/identity/service-identities")
async def list_service_identities(actor: dict = Depends(require_admin)):
    identities = await db.identities.find({}, {"_id": 0, "token_hash": 0}).to_list(500)
    return identities


@router.post("/identity/service-identities")
async def create_service_identity(payload: ServiceIdentityCreate, actor: dict = Depends(require_admin)):
    if await db.identities.find_one({"agent_id": payload.agent_id}):
        raise HTTPException(status_code=409, detail="Service identity already exists for this agent")
    token = "svc_" + secrets.token_urlsafe(32)
    await db.identities.insert_one({
        "id": str(uuid.uuid4()), "agent_id": payload.agent_id, "name": payload.name,
        "token_hash": hash_service_token(token), "scopes": payload.scopes,
        "active": True, "created_at": now_iso()})
    await log_authz(actor, "service_identity_create", f"agent:{payload.agent_id}", True, "")
    await publish("identity.service_created", actor["id"], {"agent_id": payload.agent_id})
    return {"agent_id": payload.agent_id, "token": token,
            "warning": "Store this token now — it will not be shown again."}
