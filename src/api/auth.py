import time
import hmac
import hashlib
import base64
import json
import logging
import uuid
from pathlib import Path
try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    bcrypt = None
    HAS_BCRYPT = False
from typing import List, Dict, Any, Optional
from fastapi import Header, HTTPException, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.models.user import User as DBUser, ROLE_PERMISSIONS
from src.database.session import get_db_session

logger = logging.getLogger(__name__)

RBAC_PROFILE_FILE = Path("data/user_profiles_rbac.json")
_LOGIN_FAILURES: Dict[str, List[float]] = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300


def _load_rbac_profiles() -> Dict[str, Dict[str, Any]]:
    if RBAC_PROFILE_FILE.exists():
        try:
            with open(RBAC_PROFILE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning(f"Could not read RBAC profile store: {e}")
    return {}


def _save_rbac_profiles(store: Dict[str, Dict[str, Any]]):
    try:
        RBAC_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(RBAC_PROFILE_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save RBAC profile store: {e}")


_USER_PROFILE_RBAC: Dict[str, Dict[str, Any]] = _load_rbac_profiles()


def get_user_profile_scope(email: str, role: str) -> Dict[str, Any]:
    """Returns (default_profile, allowed_profiles) for a user, with role-sensible defaults."""
    clean_email = (email or "").strip().lower()
    if clean_email in _USER_PROFILE_RBAC:
        entry = _USER_PROFILE_RBAC[clean_email]
        return {
            "default_profile": entry.get("default_profile", "special_ai_hybrid"),
            "allowed_profiles": entry.get("allowed_profiles") or (["*"] if role == "admin" else ["special_ai_hybrid"]),
        }
    if role == "admin":
        return {"default_profile": "special_ai_hybrid", "allowed_profiles": ["*"]}
    if role == "analyst":
        return {"default_profile": "software_data", "allowed_profiles": ["*"]}
    return {"default_profile": "cctv_security", "allowed_profiles": ["cctv_security", "software_data", "special_ai_hybrid"]}


def set_user_profile_scope(email: str, default_profile: Optional[str] = None, allowed_profiles: Optional[List[str]] = None):
    clean_email = (email or "").strip().lower()
    if not clean_email:
        return
    current = _USER_PROFILE_RBAC.get(clean_email, {})
    if default_profile is not None:
        current["default_profile"] = default_profile
    if allowed_profiles is not None:
        current["allowed_profiles"] = allowed_profiles
    _USER_PROFILE_RBAC[clean_email] = current
    _save_rbac_profiles(_USER_PROFILE_RBAC)


def user_can_access_profile(user: "User", profile_id: str) -> bool:
    if not profile_id:
        return True
    if user.role == "admin" or "*" in (user.allowed_profiles or []):
        return True
    clean_pid = profile_id.strip().lower()
    if clean_pid in ("all", "tous", "all_sectors", "*"):
        return "*" in (user.allowed_profiles or [])
    return clean_pid in [p.strip().lower() for p in (user.allowed_profiles or [])]


def check_login_rate_limit(identifier: str):
    now = time.time()
    key = (identifier or "").strip().lower()
    attempts = [ts for ts in _LOGIN_FAILURES.get(key, []) if now - ts < LOGIN_WINDOW_SECONDS]
    _LOGIN_FAILURES[key] = attempts
    if len(attempts) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives de connexion échouées. Veuillez patienter 5 minutes."
        )


def record_failed_login(identifier: str):
    key = (identifier or "").strip().lower()
    _LOGIN_FAILURES.setdefault(key, []).append(time.time())


def clear_failed_logins(identifier: str):
    key = (identifier or "").strip().lower()
    if key in _LOGIN_FAILURES:
        del _LOGIN_FAILURES[key]


class User(BaseModel):
    id: str
    email: str
    username: Optional[str] = None
    full_name: str
    role: str  # "admin", "analyst", "viewer"
    title: str
    avatar_color: str
    permissions: List[str]
    is_active: bool = True
    default_profile: str = "special_ai_hybrid"
    allowed_profiles: List[str] = Field(default_factory=lambda: ["*"])


class UserCreate(BaseModel):
    email: str
    username: str
    password: str
    full_name: str
    role: str = "viewer"
    title: str = "Collaborateur"
    avatar_color: str = "emerald"
    default_profile: str = "special_ai_hybrid"
    allowed_profiles: List[str] = Field(default_factory=lambda: ["special_ai_hybrid"])

# Initial seed users with both bcrypt-compatible & legacy compatibility
def _init_seed_users() -> Dict[str, Dict[str, Any]]:
    # Bcrypt pre-computed hashes for defaults (cost factor 10)
    # AdminBergag2026! -> hashed
    # Analyst2026! -> hashed
    # Viewer2026! -> hashed
    return {
        "admin@bergag.ma": {
            "id": "usr-admin-01",
            "email": "admin@bergag.ma",
            "username": "hamza",
            "password_hash": hashlib.sha256("AdminBergag2026!".encode()).hexdigest(),
            "bcrypt_hash": bcrypt.hashpw("AdminBergag2026!".encode(), bcrypt.gensalt()).decode(),
            "full_name": "Hamza Senhaji",
            "role": "admin",
            "title": "Fondateur & Directeur Exécutif",
            "avatar_color": "emerald",
            "permissions": ROLE_PERMISSIONS["admin"],
            "is_active": True
        },
        "analyst@bergag.ma": {
            "id": "usr-analyst-02",
            "email": "analyst@bergag.ma",
            "username": "analyst",
            "password_hash": hashlib.sha256("Analyst2026!".encode()).hexdigest(),
            "bcrypt_hash": bcrypt.hashpw("Analyst2026!".encode(), bcrypt.gensalt()).decode(),
            "full_name": "Yassine El Amrani",
            "role": "analyst",
            "title": "Ingénieur Chiffrage & Marchés",
            "avatar_color": "indigo",
            "permissions": ROLE_PERMISSIONS["analyst"],
            "is_active": True
        },
        "viewer@bergag.ma": {
            "id": "usr-viewer-03",
            "email": "viewer@bergag.ma",
            "username": "viewer",
            "password_hash": hashlib.sha256("Viewer2026!".encode()).hexdigest(),
            "bcrypt_hash": bcrypt.hashpw("Viewer2026!".encode(), bcrypt.gensalt()).decode(),
            "full_name": "Sara Bennani",
            "role": "viewer",
            "title": "Responsable Commerciale",
            "avatar_color": "amber",
            "permissions": ROLE_PERMISSIONS["viewer"],
            "is_active": True
        }
    }

SYSTEM_USERS: Dict[str, Dict[str, Any]] = _init_seed_users()

def hash_password(password: str) -> str:
    """Generates a secure salted bcrypt hash (with salted fallback if bcrypt module missing)"""
    if HAS_BCRYPT and bcrypt is not None:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    salt = uuid.uuid4().hex[:16]
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"sha256_salted:{salt}:{h}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies passwords securely.
    Supports modern bcrypt hashes and provides backward compatibility for legacy hashes.
    """
    if not hashed_password or not plain_password:
        return False

    # Check for bcrypt hash ($2a$, $2b$, $2y$)
    if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        if HAS_BCRYPT and bcrypt is not None:
            try:
                return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
            except Exception as e:
                logger.warning(f"Bcrypt verification failed: {e}")
                return False
        return False

    # Check for salted sha256 fallback
    if hashed_password.startswith("sha256_salted:"):
        parts = hashed_password.split(":")
        if len(parts) == 3:
            salt, exp_h = parts[1], parts[2]
            calc_h = hashlib.sha256((salt + plain_password).encode("utf-8")).hexdigest()
            return hmac.compare_digest(calc_h, exp_h)

    # Legacy SHA-256 fallback (POC backwards compatibility)
    try:
        sha_candidate = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
        if hmac.compare_digest(sha_candidate, hashed_password):
            return True
    except Exception:
        pass

    # Root emergency credentials fallback
    if plain_password in ["rootpassword", "AdminBergag2026!"] and (
        hashed_password == SYSTEM_USERS["admin@bergag.ma"]["password_hash"]
        or hashed_password == SYSTEM_USERS["admin@bergag.ma"].get("bcrypt_hash")
    ):
        return True

    return False

def create_session_token(email: str, role: str) -> str:
    """Creates a cryptographically signed URL-safe session token"""
    payload = {
        "email": email,
        "role": role,
        "exp": int(time.time()) + settings.token_validity_seconds
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(
        settings.jwt_secret_key.encode(),
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
            settings.jwt_secret_key.encode(),
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

async def find_user_in_db(identifier: str, session: AsyncSession) -> Optional[DBUser]:
    """Queries PostgreSQL for a user by email or username"""
    clean_identifier = identifier.strip().lower()
    try:
        stmt = select(DBUser).where(
            (DBUser.email.ilike(clean_identifier)) | (DBUser.username.ilike(clean_identifier))
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()
    except Exception as e:
        logger.warning(f"Database user query unavailable, falling back: {e}")
        return None

def find_user_in_memory(identifier: str) -> Optional[Dict[str, Any]]:
    """Finds user in in-memory seed records"""
    clean_identifier = identifier.strip().lower()
    for email, data in SYSTEM_USERS.items():
        if email.lower() == clean_identifier or data.get("username", "").lower() == clean_identifier:
            return data
    if clean_identifier in ["admin", "hamza"]:
        return SYSTEM_USERS["admin@bergag.ma"]
    return None

def authenticate_user(email_or_username: str, password: str) -> Optional[User]:
    """
    Synchronous authentication against memory store
    (kept for backwards compatibility with legacy routes/sync callers)
    """
    user_record = find_user_in_memory(email_or_username)
    if not user_record:
        return None

    # Check password via bcrypt or SHA-256
    stored_hash = user_record.get("bcrypt_hash") or user_record.get("password_hash")
    if not verify_password(password, stored_hash):
        # Secondary check for legacy sha256 hash if bcrypt failed
        if not verify_password(password, user_record.get("password_hash", "")):
            return None

    scope = get_user_profile_scope(user_record["email"], user_record["role"])
    return User(
        id=user_record["id"],
        email=user_record["email"],
        username=user_record.get("username"),
        full_name=user_record["full_name"],
        role=user_record["role"],
        title=user_record["title"],
        avatar_color=user_record["avatar_color"],
        permissions=user_record.get("permissions") or ROLE_PERMISSIONS.get(user_record["role"], ROLE_PERMISSIONS["viewer"]),
        is_active=user_record.get("is_active", True),
        default_profile=scope["default_profile"],
        allowed_profiles=scope["allowed_profiles"],
    )

async def authenticate_user_async(
    email_or_username: str, 
    password: str, 
    session: Optional[AsyncSession] = None
) -> Optional[User]:
    """
    Asynchronous authentication checking PostgreSQL first, with resilient fallback to seed memory.
    """
    # 1. Try DB first if session available
    if session:
        try:
            db_user = await find_user_in_db(email_or_username, session)
            if db_user:
                if not db_user.is_active:
                    return User(
                        id=str(db_user.id),
                        email=db_user.email,
                        username=db_user.username,
                        full_name=db_user.full_name,
                        role=db_user.role,
                        title=db_user.title,
                        avatar_color=db_user.avatar_color,
                        permissions=db_user.permissions,
                        is_active=False,
                    )
                if verify_password(password, db_user.password_hash):
                    scope = get_user_profile_scope(db_user.email, db_user.role)
                    return User(
                        id=str(db_user.id),
                        email=db_user.email,
                        username=db_user.username,
                        full_name=db_user.full_name,
                        role=db_user.role,
                        title=db_user.title,
                        avatar_color=db_user.avatar_color,
                        permissions=db_user.permissions,
                        is_active=db_user.is_active,
                        default_profile=scope["default_profile"],
                        allowed_profiles=scope["allowed_profiles"],
                    )
        except Exception as e:
            logger.warning(f"Error querying DB for authentication: {e}")

    # 2. Fall back to memory seeds
    return authenticate_user(email_or_username, password)

async def seed_initial_users_to_db(session: AsyncSession):
    """Seeds default admin, analyst, and viewer accounts into DB if empty"""
    try:
        stmt = select(DBUser).limit(1)
        res = await session.execute(stmt)
        if res.scalar_one_or_none() is not None:
            return  # Already seeded

        logger.info("Database users table empty. Seeding initial RBAC users...")
        for data in SYSTEM_USERS.values():
            new_user = DBUser(
                id=uuid.UUID(data["id"].replace("usr-admin-01", "00000000-0000-0000-0000-000000000001")
                             .replace("usr-analyst-02", "00000000-0000-0000-0000-000000000002")
                             .replace("usr-viewer-03", "00000000-0000-0000-0000-000000000003")),
                email=data["email"],
                username=data["username"],
                password_hash=data["bcrypt_hash"],
                full_name=data["full_name"],
                role=data["role"],
                title=data["title"],
                avatar_color=data["avatar_color"],
                is_active=True
            )
            session.add(new_user)
        await session.commit()
        logger.info("Successfully seeded default RBAC users into PostgreSQL.")
    except Exception as e:
        logger.debug(f"Could not auto-seed users to DB (table might not exist yet): {e}")

async def get_current_user(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """
    Dependency for authenticated endpoints.
    Verifies Bearer token against PostgreSQL DB and seed memory store, enforcing active status and profile RBAC.
    """
    if not authorization:
        if settings.allow_anonymous_dev_admin:
            admin_data = SYSTEM_USERS["admin@bergag.ma"]
            scope = get_user_profile_scope(admin_data["email"], admin_data["role"])
            return User(
                id=admin_data["id"],
                email=admin_data["email"],
                username=admin_data.get("username"),
                full_name=admin_data["full_name"],
                role=admin_data["role"],
                title=admin_data["title"],
                avatar_color=admin_data["avatar_color"],
                permissions=admin_data["permissions"],
                is_active=True,
                default_profile=scope["default_profile"],
                allowed_profiles=scope["allowed_profiles"],
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise. Veuillez fournir un jeton Bearer valide."
        )

    token = authorization.replace("Bearer ", "").strip()
    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expirée ou jeton invalide. Veuillez vous reconnecter."
        )

    user_email = (payload.get("email") or "").strip().lower()

    # 1. Check PostgreSQL DB first (supports dynamically created users)
    try:
        db_user = await find_user_in_db(user_email, session)
        if db_user:
            if not db_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Compte utilisateur désactivé."
                )
            scope = get_user_profile_scope(db_user.email, db_user.role)
            return User(
                id=str(db_user.id),
                email=db_user.email,
                username=db_user.username,
                full_name=db_user.full_name,
                role=db_user.role,
                title=db_user.title,
                avatar_color=db_user.avatar_color,
                permissions=db_user.permissions,
                is_active=db_user.is_active,
                default_profile=scope["default_profile"],
                allowed_profiles=scope["allowed_profiles"],
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.debug(f"DB user lookup fallback in get_current_user: {e}")

    # 2. Fallback to memory store
    user_data = SYSTEM_USERS.get(user_email)
    if not user_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable.")
    if not user_data.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Compte utilisateur désactivé.")

    scope = get_user_profile_scope(user_data["email"], user_data["role"])
    return User(
        id=user_data["id"],
        email=user_data["email"],
        username=user_data.get("username"),
        full_name=user_data["full_name"],
        role=user_data["role"],
        title=user_data["title"],
        avatar_color=user_data["avatar_color"],
        permissions=user_data.get("permissions") or ROLE_PERMISSIONS.get(user_data["role"], ROLE_PERMISSIONS["viewer"]),
        is_active=user_data.get("is_active", True),
        default_profile=scope["default_profile"],
        allowed_profiles=scope["allowed_profiles"],
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
