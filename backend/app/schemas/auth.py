from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal

Role = Literal[
    "admin",
    "sales",
    "project_manager",
    "designer",
    "printing",
    "logistics",
    "accounts",
    "hr",
]

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: Optional[str] = None
    role: Optional[Role] = None  # optional; first user becomes admin automatically

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserPublic(BaseModel):
    id: int
    username: str
    role: str
    full_name: str | None = None
    is_active: bool