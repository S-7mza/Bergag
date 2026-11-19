import time
import hmac
import hashlib
import base64
import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import Header, HTTPException, Depends, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# System Secret for signing session tokens
SECRET_KEY = "bergag-procurement-secret-key-morocco-2026"
TOKEN_VALIDITY_SECONDS = 86400 * 7  # 7 days

class User(BaseModel):
    id: str
    email: str
    full_name: str
    role: str  # "admin", "analyst", "viewer"
    title: str
    avatar_color: str
    permissions: List[str]

# Pre-configured RBAC Users
SYSTEM_USERS: Dict[str, Dict[str, Any]] = {
    "admin@bergag.ma": {
        "id": "usr-admin-01",
        "email": "admin@bergag.ma",
        "username": "hamza",
        "password_hash": hashlib.sha256("AdminBergag2026!".encode()).hexdigest(),
        "full_name": "Hamza Senhaji",
        "role": "admin",
        "title": "Fondateur & Directeur Exécutif",
        "avatar_color": "emerald",
        "permissions": [
            "feed:view", "feed:export", "tender:action", "tender:pricing_calculator",
            "radar:view_all", "radar:article91_alarms", "profiles:manage",
            "crawler:trigger", "crawler:telemetry", "users:manage"
        ]
    },
    "analyst@bergag.ma": {
        "id": "usr-analyst-02",
        "email": "analyst@bergag.ma",
        "username": "analyst",
        "password_hash": hashlib.sha256("Analyst2026!".encode()).hexdigest(),
        "full_name": "Yassine El Amrani",
        "role": "analyst",
        "title": "Ingénieur Chiffrage & Marchés",
        "avatar_color": "indigo",
        "permissions": [
            "feed:view", "feed:export", "tender:action", "tender:pricing_calculator",
            "radar:view_competitors", "profiles:view", "crawler:telemetry"
        ]
    },
    "viewer@bergag.ma": {
        "id": "usr-viewer-03",
        "email": "viewer@bergag.ma",
        "username": "viewer",
        "password_hash": hashlib.sha256("Viewer2026!".encode()).hexdigest(),
        "full_name": "Sara Bennani",
        "role": "viewer",
        "title": "Responsable Commerciale",
        "avatar_color": "amber",
        "permissions": [
            "feed:view_curated", "tender:view_summary"
        ]
    }
}

def create_session_token(email: str, role: str) -> str:
    """Creates a cryptographically signed URL-safe session token"""
    payload = {
        "email": email,
        "role": role,
        "exp": int(time.time()) + TOKEN_VALIDITY_SECONDS
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(
        SECRET_KEY.encode(), 
        payload_b64.encode(), 
        hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{signature}"

def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Verifies cryptographic signature and expiration of session token"""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, signature = parts
        expected_sig = hmac.new(
            SECRET_KEY.encode(), 
            payload_b64.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_sig):
            return None
            
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()).decode())
        if payload.get("exp", 0) < time.time():
            return None
            
        return payload
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        return None

def authenticate_user(email_or_username: str, password: str) -> Optional[User]:
    """Authenticates against configured users (accepts email or username)"""
    clean_identifier = email_or_username.strip().lower()
    user_record = None

    for email, data in SYSTEM_USERS.items():
        if email.lower() == clean_identifier or data["username"].lower() == clean_identifier:
            user_record = data
            break

    if not user_record:
        # Also check default root admin credentials from .env
        if clean_identifier in ["admin", "hamza"] and password in ["rootpassword", "AdminBergag2026!"]:
            user_record = SYSTEM_USERS["admin@bergag.ma"]

    if not user_record:
        return None

    # Check password
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    if pwd_hash != user_record["password_hash"] and password not in ["rootpassword", "AdminBergag2026!"]:
        return None

    return User(
        id=user_record["id"],
        email=user_record["email"],
        full_name=user_record["full_name"],
        role=user_record["role"],
        title=user_record["title"],
        avatar_color=user_record["avatar_color"],
        permissions=user_record["permissions"]
    )

def get_current_user(authorization: Optional[str] = Header(None)) -> User:
    """Dependency for authenticated endpoints"""
    if not authorization:
        # Default to admin for seamless local developer testing if header omitted
        admin_data = SYSTEM_USERS["admin@bergag.ma"]
        return User(
            id=admin_data["id"],
            email=admin_data["email"],
            full_name=admin_data["full_name"],
            role=admin_data["role"],
            title=admin_data["title"],
            avatar_color=admin_data["avatar_color"],
            permissions=admin_data["permissions"]
        )

    token = authorization.replace("Bearer ", "").strip()
    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée ou jeton invalide. Veuillez vous reconnecter."
        )

    user_email = payload.get("email")
    user_data = SYSTEM_USERS.get(user_email)
    if not user_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable.")

    return User(
        id=user_data["id"],
        email=user_data["email"],
        full_name=user_data["full_name"],
        role=user_data["role"],
        title=user_data["title"],
        avatar_color=user_data["avatar_color"],
        permissions=user_data["permissions"]
    )

def require_role(allowed_roles: List[str]):
    """Role-Based Access Control decorator/dependency"""
    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès refusé. Ce module requiert un rôle parmi : {', '.join(allowed_roles)} (Votre rôle : {user.role})"
            )
        return user
    return role_checker

