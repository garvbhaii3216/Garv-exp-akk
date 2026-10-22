import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
from dotenv import load_dotenv
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

# Load environment
load_dotenv()

try:
    from backend.database import get_db
    from backend.models import User
except (ImportError, ModuleNotFoundError):
    from database import get_db
    from models import User

# Configuration & Secrets Management
APP_ENV = os.getenv("APP_ENV", "development").lower()
RAW_SECRET = os.getenv("JWT_SECRET_KEY")

def get_or_create_jwt_secret() -> str:
    """Retrieve or generate a stable persistent JWT secret to prevent session loss on restart."""
    if RAW_SECRET and len(RAW_SECRET) >= 32:
        return RAW_SECRET
    secret_file = os.path.join(os.path.dirname(__file__), ".jwt_secret_key")
    if os.path.exists(secret_file):
        try:
            with open(secret_file, "r", encoding="utf-8") as f:
                saved = f.read().strip()
                if saved and len(saved) >= 32:
                    return saved
        except Exception:
            pass
    new_secret = "expense_tracker_persistent_vault_secret_" + secrets.token_hex(32)
    try:
        with open(secret_file, "w", encoding="utf-8") as f:
            f.write(new_secret)
    except Exception:
        pass
    return new_secret

SECRET_KEY = RAW_SECRET if (RAW_SECRET and len(RAW_SECRET) >= 32) else get_or_create_jwt_secret()

ALGORITHM = "HS256"
# Default token expiration is 365 days so users are not repeatedly asked to log in
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 365)))
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash password using bcrypt with configurable work factor (default 12 rounds).
    Prevents silent truncation beyond 72 bytes.
    """
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > 72:
        raise ValueError("Password cannot exceed 72 bytes for bcrypt security.")
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(pw_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash in constant time."""
    try:
        pw_bytes = plain_password.encode("utf-8")
        if len(pw_bytes) > 72:
            return False
        return bcrypt.checkpw(pw_bytes, hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token with iat, exp, and sub claims."""
    to_encode = data.copy()
    now_utc = datetime.now(timezone.utc)
    if expires_delta:
        expire = now_utc + expires_delta
    else:
        expire = now_utc + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({
        "exp": expire,
        "iat": now_utc,
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Authenticate request bearer token and retrieve active user."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    user = None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is not None:
            user_id = int(user_id_str)
            user = db.query(User).filter(User.id == user_id).first()
    except Exception:
        # Support Firebase Authentication ID Token fallback
        try:
            fb_payload = jwt.decode(token, options={"verify_signature": False})
            iss = str(fb_payload.get("iss", ""))
            aud = str(fb_payload.get("aud", ""))
            if (iss.startswith("https://securetoken.google.com/") or aud == "expense-tracker-3216") and fb_payload.get("email"):
                fb_email = str(fb_payload["email"]).strip().lower()
                user = db.query(User).filter(User.email == fb_email).first()
                if not user:
                    user = User(
                        email=fb_email,
                        full_name=fb_email.split("@")[0].replace(".", " ").title(),
                        hashed_password=hash_password(secrets.token_hex(24)),
                        currency_symbol="₹",
                        currency_code="INR",
                        is_active=True
                    )
                    db.add(user)
                    db.commit()
                    db.refresh(user)
        except Exception:
            pass
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not getattr(user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    return user


def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Authorize administrator privileges. Raises 403 Forbidden for non-admins."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Administrator access required to perform this action.",
        )
    return current_user

