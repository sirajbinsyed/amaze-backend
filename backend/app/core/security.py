from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

import jwt
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from ..core.config import settings
from ..db.pool import fetch_one

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

ALLOWED_ROLES = [
    "admin",
    "sales",
    "project",
    "project_manager",
    "designer",
    "printing",
    "logistics",
    "accounts",
    "hr",
    "staff",
    "crm"
]

def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])  # Truncate to 72 bytes for bcrypt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password[:72], hashed_password)  # Truncate for verification

def create_access_token(subject: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = subject.copy()
    now = datetime.now(tz=timezone.utc)
    expire = now + (expires_delta or settings.access_token_expires)
    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = await fetch_one(
        """
        select id, username, role, status
        from staff_credentials
        where id = %s
        """,
        (int(user_id),),
    )
    if not user or user["status"] != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")
    return user

def require_roles(roles: List[str]):
    invalid = [r for r in roles if r not in ALLOWED_ROLES]
    if invalid:
        raise ValueError(f"Invalid roles: {invalid}")

    async def _dep(user = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return _dep