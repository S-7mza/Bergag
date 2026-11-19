import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from src.api.auth import (
    User, 
    authenticate_user, 
    create_session_token, 
    get_current_user, 
    require_role, 
    SYSTEM_USERS
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Authentication & RBAC"])

class LoginRequest(BaseModel):
    username_or_email: str
    password: str

class LoginResponse(BaseModel):
    token: str
    user: User

class SwitchRoleRequest(BaseModel):
    role: str

@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticates user and returns signed session token with role permissions"""
    user = authenticate_user(req.username_or_email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects. Vérifiez votre email et mot de passe."
        )
    token = create_session_token(user.email, user.role)
    logger.info(f"User '{user.email}' logged in successfully with role '{user.role}'")
    return LoginResponse(token=token, user=user)

@router.get("/me", response_model=User)
async def get_me(user: User = Depends(get_current_user)):
    """Returns currently authenticated user profile and permissions"""
    return user

@router.post("/switch-demo-role", response_model=LoginResponse)
async def switch_demo_role(req: SwitchRoleRequest):
    """Allows instant previewing of role-based views (Admin, Analyst, Viewer)"""
    role_map = {
        "admin": "admin@bergag.ma",
        "analyst": "analyst@bergag.ma",
        "viewer": "viewer@bergag.ma"
    }
    email = role_map.get(req.role.lower())
    if not email or email not in SYSTEM_USERS:
        raise HTTPException(status_code=400, detail=f"Rôle '{req.role}' invalide")

    user_data = SYSTEM_USERS[email]
    user = User(
        id=user_data["id"],
        email=user_data["email"],
        full_name=user_data["full_name"],
        role=user_data["role"],
        title=user_data["title"],
        avatar_color=user_data["avatar_color"],
        permissions=user_data["permissions"]
    )
    token = create_session_token(user.email, user.role)
    return LoginResponse(token=token, user=user)

@router.get("/users", response_model=List[User])
async def list_team_users(user: User = Depends(require_role(["admin"]))):
    """Lists all configured team users (Admin only)"""
    return [
        User(
            id=d["id"],
            email=d["email"],
            full_name=d["full_name"],
            role=d["role"],
            title=d["title"],
            avatar_color=d["avatar_color"],
            permissions=d["permissions"]
        )
        for d in SYSTEM_USERS.values()
    ]

