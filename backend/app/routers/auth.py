from fastapi import APIRouter, HTTPException, Depends, status, Body
from datetime import datetime
from pydantic import EmailStr

from ..schemas.auth import TokenResponse, UserPublic
from ..core.security import (
    hash_password,
    verify_password,
    create_access_token,
    require_roles,
    get_current_user
)
from ..db.pool import fetch_one, execute

router = APIRouter(prefix="/auth", tags=["auth"])

# ==============================
# SIGNUP
# ==============================
@router.post("/signup", response_model=UserPublic)
async def signup(payload: dict = Body(...)):
    username = payload.get("username")
    password = payload.get("password")
    staff_id = payload.get("staff_id")
    role_input = payload.get("role")

    if not username or not password or not staff_id:
        raise HTTPException(status_code=400, detail="username, password, and staff_id are required")

    # bcrypt limit = 72 bytes
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password cannot exceed 72 bytes")

    # Check if username already exists
    existing_user = await fetch_one(
        "SELECT id FROM staff_credentials WHERE username = %s",
        (username,)
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")

    # Determine role (first user becomes admin)
    row = await fetch_one("SELECT COUNT(1) AS c FROM staff_credentials", None)
    is_first_user = (row["c"] == 0)
    role = role_input or ("admin" if is_first_user else "sales")

    # Hash password
    hashed_password = hash_password(password[:72])

    created_at = datetime.utcnow()
    status_value = "active"

    await execute(
        """
        INSERT INTO staff_credentials (staff_id, username, password_hash, role, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (staff_id, username, hashed_password, role, status_value, created_at),
    )

    created_user = await fetch_one(
        "SELECT id, staff_id, username, role, status, created_at FROM staff_credentials WHERE username = %s",
        (username,)
    )

    return UserPublic(
    id=created_user["id"],
    username=created_user["username"],
    role=created_user["role"],
    full_name=None,
    is_active=(created_user["status"] == "active")
    )


# ==============================
# LOGIN
# ==============================
@router.post("/login", response_model=TokenResponse)
async def login(payload: dict = Body(...)):
    username = payload.get("username")
    password = payload.get("password")

    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password are required")

    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password cannot exceed 72 bytes")

    user = await fetch_one(
        "SELECT id, username, password_hash, role, status FROM staff_credentials WHERE username = %s",
        (username,),
    )

    if not user or not verify_password(password[:72], user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    if user["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    token = create_access_token({"sub": str(user["id"]), "role": user["role"]})

    return TokenResponse(access_token=token)
