from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import JWT_SECRET, JWT_TTL_MIN
from .db import get_db
from .models import AuditLog, User

bearer = HTTPBearer(auto_error=False)

OFFICER_ROLES = ("refund_auditor", "special_sectors", "risk_analyst", "admin")
DECISION_ROLES = ("refund_auditor", "special_sectors", "admin")


def create_token(user: User) -> str:
    payload = {"sub": user.username, "role": user.role,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_TTL_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), request: Request = None,
                 db: Session = Depends(get_db)) -> User:
    token = creds.credentials if creds else (request.query_params.get("token") if request else None)
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, data["sub"])
    if not user:
        raise HTTPException(401, "Unknown user")
    return user


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"Role '{user.role}' is not allowed to do this")
        return user
    return dep


def mask_tin(tin: str | None, user: User, assigned: str | None = None) -> str | None:
    """TINs are masked except for admins, the assigned officer, or the taxpayer themself."""
    if not tin:
        return tin
    if tin.startswith("FX-"):
        return tin
    if user.role == "admin" or (assigned and user.username == assigned) or (user.role == "taxpayer" and user.tin == tin):
        return tin
    return tin[:3] + "•••" + tin[-2:]


def audit(db: Session, user: User | None, action: str, entity: str, detail: str | None = None, commit: bool = True):
    db.add(AuditLog(username=user.username if user else "anonymous", role=user.role if user else "-",
                    action=action, entity=entity, detail=detail, ts=datetime.utcnow()))
    if commit:
        db.commit()
