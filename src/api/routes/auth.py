import logging
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db_session
from src.models.user import User as DBUser, ROLE_PERMISSIONS
from src.api.auth import (
    User,
    UserCreate,
    authenticate_user_async,
    create_session_token,
    get_current_user,
    require_role,
    hash_password,
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

class UpdateUserRoleRequest(BaseModel):
    role: str
    is_active: Optional[bool] = None

@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(get_db_session)):
    """Authenticates user against DB or memory store and returns signed session token with RBAC permissions"""
    user = await authenticate_user_async(req.username_or_email, req.password, session=session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants incorrects. Vérifiez votre email et mot de passe."
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ce compte utilisateur est désactivé. Veuillez contacter un administrateur."
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
        username=user_data.get("username"),
        full_name=user_data["full_name"],
        role=user_data["role"],
        title=user_data["title"],
        avatar_color=user_data["avatar_color"],
        permissions=user_data.get("permissions") or ROLE_PERMISSIONS.get(user_data["role"], ROLE_PERMISSIONS["viewer"]),
        is_active=user_data.get("is_active", True)
    )
    token = create_session_token(user.email, user.role)
    return LoginResponse(token=token, user=user)

@router.get("/users", response_model=List[User])
async def list_team_users(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_role(["admin"]))
):
    """Lists all configured team users from PostgreSQL database (falls back to memory store)"""
    try:
        stmt = select(DBUser).order_by(DBUser.created_at.desc())
        res = await session.execute(stmt)
        db_users = res.scalars().all()
        if db_users:
            return [
                User(
                    id=str(u.id),
                    email=u.email,
                    username=u.username,
                    full_name=u.full_name,
                    role=u.role,
                    title=u.title,
                    avatar_color=u.avatar_color,
                    permissions=u.permissions,
                    is_active=u.is_active
                )
                for u in db_users
            ]
    except Exception as e:
        logger.debug(f"DB user query fallback: {e}")

    # Fallback to seed accounts
    return [
        User(
            id=d["id"],
            email=d["email"],
            username=d.get("username"),
            full_name=d["full_name"],
            role=d["role"],
            title=d["title"],
            avatar_color=d["avatar_color"],
            permissions=d.get("permissions") or ROLE_PERMISSIONS.get(d["role"], ROLE_PERMISSIONS["viewer"]),
            is_active=d.get("is_active", True)
        )
        for d in SYSTEM_USERS.values()
    ]

@router.post("/users", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user(
    req: UserCreate,
    session: AsyncSession = Depends(get_db_session),
    admin: User = Depends(require_role(["admin"]))
):
    """Creates a new team user with bcrypt password and assigned role (Admin only)"""
    clean_email = req.email.strip().lower()
    clean_username = req.username.strip().lower()

    if req.role not in ROLE_PERMISSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Rôle invalide '{req.role}'. Choix autorisés: {list(ROLE_PERMISSIONS.keys())}"
        )

    # 1. Attempt PostgreSQL user creation
    try:
        # Check uniqueness
        stmt = select(DBUser).where((DBUser.email == clean_email) | (DBUser.username == clean_username))
        res = await session.execute(stmt)
        if res.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Cet email ou nom d'utilisateur existe déjà.")

        new_db_user = DBUser(
            id=uuid.uuid4(),
            email=clean_email,
            username=clean_username,
            password_hash=hash_password(req.password),
            full_name=req.full_name.strip(),
            role=req.role,
            title=req.title.strip(),
            avatar_color=req.avatar_color,
            is_active=True
        )
        session.add(new_db_user)
        await session.commit()
        await session.refresh(new_db_user)

        logger.info(f"Admin {admin.email} created user {new_db_user.email} in DB with role {new_db_user.role}")
        return User(
            id=str(new_db_user.id),
            email=new_db_user.email,
            username=new_db_user.username,
            full_name=new_db_user.full_name,
            role=new_db_user.role,
            title=new_db_user.title,
            avatar_color=new_db_user.avatar_color,
            permissions=new_db_user.permissions,
            is_active=new_db_user.is_active
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"DB write unavailable, falling back to memory: {e}")

    # 2. In-memory store fallback
    if clean_email in SYSTEM_USERS:
        raise HTTPException(status_code=409, detail="Cet email existe déjà.")

    user_id = f"usr-{uuid.uuid4().hex[:8]}"
    hashed = hash_password(req.password)
    user_dict = {
        "id": user_id,
        "email": clean_email,
        "username": clean_username,
        "password_hash": hashed,
        "bcrypt_hash": hashed,
        "full_name": req.full_name.strip(),
        "role": req.role,
        "title": req.title.strip(),
        "avatar_color": req.avatar_color,
        "permissions": ROLE_PERMISSIONS[req.role],
        "is_active": True
    }
    SYSTEM_USERS[clean_email] = user_dict

    return User(
        id=user_id,
        email=clean_email,
        username=clean_username,
        full_name=req.full_name.strip(),
        role=req.role,
        title=req.title.strip(),
        avatar_color=req.avatar_color,
        permissions=ROLE_PERMISSIONS[req.role],
        is_active=True
    )
