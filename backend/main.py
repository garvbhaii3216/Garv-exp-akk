import io
import csv
import calendar
import os
import sys
import json
import zipfile
import secrets
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List
from pydantic import BaseModel

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, Query, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc

# Load environment configuration
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("expense_tracker")

try:
    from backend.database import engine, get_db, Base, create_database_backup, ensure_schema_migrations
    from backend.models import User, AllowanceCycle, RefillLog, Expense, FixedExpense
    from backend.auth import (
        hash_password, verify_password, create_access_token,
        get_current_user, get_current_admin_user
    )
    from backend.rate_limiter import rate_limiter
    from backend.schemas import (
        UserRegister, UserLogin, GoogleLoginRequest, UserResponse, UserUpdate, TokenResponse,
        SendOTPRequest, SendOTPResponse,
        ForgotPasswordQuestionRequest, ForgotPasswordQuestionResponse, ForgotPasswordResetRequest,
        AllowanceCycleCreate, AllowanceCycleUpdate, AllowanceCycleResponse,
        RefillLogCreate, RefillLogResponse,
        ExpenseCreate, ExpenseUpdate, ExpenseResponse,
        FixedExpenseCreate, FixedExpenseUpdate, FixedExpenseResponse, FixedExpenseLogRequest,
        DashboardSummary, CategorySpend, DailySpend, SettlementSummary,
        ClassifyRequest, ClassifyResponse,
        AdminUserSummary, AdminSystemStats, AdminToggleUserStatus, AdminUpgradeRequest,
        AIChatRequest, AIChatResponse, AIChatMessage
    )
    from backend.ai_service import process_ai_query
except (ImportError, ModuleNotFoundError):
    from database import engine, get_db, Base, create_database_backup, ensure_schema_migrations
    from models import User, AllowanceCycle, RefillLog, Expense, FixedExpense
    from auth import (
        hash_password, verify_password, create_access_token,
        get_current_user, get_current_admin_user
    )
    from rate_limiter import rate_limiter
    from schemas import (
        UserRegister, UserLogin, GoogleLoginRequest, UserResponse, UserUpdate, TokenResponse,
        SendOTPRequest, SendOTPResponse,
        ForgotPasswordQuestionRequest, ForgotPasswordQuestionResponse, ForgotPasswordResetRequest,
        AllowanceCycleCreate, AllowanceCycleUpdate, AllowanceCycleResponse,
        RefillLogCreate, RefillLogResponse,
        ExpenseCreate, ExpenseUpdate, ExpenseResponse,
        FixedExpenseCreate, FixedExpenseUpdate, FixedExpenseResponse, FixedExpenseLogRequest,
        DashboardSummary, CategorySpend, DailySpend, SettlementSummary,
        ClassifyRequest, ClassifyResponse,
        AdminUserSummary, AdminSystemStats, AdminToggleUserStatus, AdminUpgradeRequest,
        AIChatRequest, AIChatResponse, AIChatMessage
    )
    from ai_service import process_ai_query

# Execute automated rolling backup of SQLite database on startup
try:
    create_database_backup()
except Exception as _bk_err:
    logger.warning(f"Startup database backup skipped: {_bk_err}")

# Execute schema migrations if needed
try:
    ensure_schema_migrations()
except Exception as _mig_err:
    logger.warning(f"Schema migration notice: {_mig_err}")

# Initialize database tables
Base.metadata.create_all(bind=engine)

def seed_default_accounts():
    try:
        from backend.database import SessionLocal
        db = SessionLocal()
        demo_user = db.query(User).filter(User.email == "demo.user@example.com").first()
        if not demo_user:
            demo_user = User(
                email="demo.user@example.com",
                full_name="Demo User",
                hashed_password=hash_password("DemoUser123!"),
                currency_symbol="₹",
                currency_code="INR",
                security_question="What was the name of your first school?",
                security_answer_hash=hash_password("demo school")
            )
            db.add(demo_user)
            db.commit()
            db.refresh(demo_user)

            today = date.today()
            m_str = f"{today.year:04d}-{today.month:02d}"
            cycle = AllowanceCycle(
                user_id=demo_user.id,
                month_year=m_str,
                initial_allowance=25000.0,
                funding_source="Salary / Income"
            )
            db.add(cycle)
            db.commit()
            db.refresh(cycle)

            refill = RefillLog(
                user_id=demo_user.id,
                cycle_id=cycle.id,
                amount=5000.0,
                funding_source="Salary / Income",
                reason="Performance Bonus",
                date=today,
                payment_mode="Bank Transfer"
            )
            db.add(refill)

            e1 = Expense(
                user_id=demo_user.id,
                cycle_id=cycle.id,
                amount=650.0,
                category="Food & Dining",
                date=today,
                description="Organic Groceries & Produce",
                payment_mode="UPI"
            )
            e2 = Expense(
                user_id=demo_user.id,
                cycle_id=cycle.id,
                amount=1299.0,
                category="Bills & Utilities",
                date=today,
                description="High-Speed Fiber Internet",
                payment_mode="UPI"
            )
            db.add_all([e1, e2])

            fb = FixedExpense(
                user_id=demo_user.id,
                title="Fiber Broadband",
                amount=999.0,
                is_variable_amount=False,
                frequency="monthly",
                due_day=5,
                category="Bills & Utilities",
                payment_mode="UPI"
            )
            db.add(fb)
            db.commit()
        else:
            demo_user.hashed_password = hash_password("DemoUser123!")
            demo_user.full_name = "Demo User"
            db.commit()

        # Strict requirement: Ensure singhalgarv09@gmail.com is always active admin
        master_admin = db.query(User).filter(User.email == "singhalgarv09@gmail.com").first()
        if master_admin:
            master_admin.is_admin = True
            db.commit()

        db.close()
    except Exception as e:
        logger.warning(f"Default account seeding notice: {e}")

try:
    seed_default_accounts()
except Exception:
    pass

# Environment & Debug Configuration
APP_ENV = os.getenv("APP_ENV", "development").lower()
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
ADMIN_REGISTRATION_KEY = os.getenv("ADMIN_REGISTRATION_KEY")
ALLOWED_FRAME_ANCESTORS = os.getenv("ALLOWED_FRAME_ANCESTORS", "").strip()

# In production, turn off interactive Swagger/OpenAPI docs to prevent endpoint enumeration
show_docs = DEBUG or APP_ENV != "production"

app = FastAPI(
    title="Personal Expense & Allowance Tracker API",
    description="Secure, production-hardened API for personal expense and allowance tracking",
    version="1.1.0",
    docs_url="/docs" if show_docs else None,
    redoc_url="/redoc" if show_docs else None,
    openapi_url="/openapi.json" if show_docs else None,
)


# ==========================================
# SECURITY & RATE LIMITING MIDDLEWARE
# ==========================================

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # 0. Fast-path CORS preflight OPTIONS requests without rate-limiting
    if request.method == "OPTIONS":
        return await call_next(request)

    # 1. Payload size protection (max 2MB to prevent memory exhaustion DoS)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 2 * 1024 * 1024:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": "Request payload exceeds 2MB limit."}
        )

    # 2. Rate limiting check based on route path
    path = request.url.path
    if path.startswith("/api/auth/login") or path.startswith("/api/auth/register") or path.startswith("/api/auth/google") or path.startswith("/api/auth/forgot-password"):
        try:
            rate_limiter.check_rate_limit(request, tier="auth")
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
    elif path.startswith("/api/admin"):
        try:
            rate_limiter.check_rate_limit(request, tier="admin")
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
    elif path.startswith("/api/"):
        try:
            rate_limiter.check_rate_limit(request, tier="general")
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)

    # Process request
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(f"Unhandled server error on {request.method} {path}: {exc}", exc_info=DEBUG)
        if DEBUG:
            raise exc
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error occurred."}
        )

    # 3. Comprehensive Security Headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), focus-without-user-activation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

    # Frame embedding policy (supports embedding in WordPress when configured)
    if ALLOWED_FRAME_ANCESTORS:
        frame_policy = f"'self' {ALLOWED_FRAME_ANCESTORS}"
    else:
        frame_policy = "'none'"
        response.headers["X-Frame-Options"] = "DENY"

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://unpkg.com https://cdn.jsdelivr.net https://accounts.google.com https://www.gstatic.com https://*.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com https://accounts.google.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 ws: wss: https://accounts.google.com https://*.googleapis.com https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://*.firebaseio.com https://*.firebase.com https://*.firebaseapp.com https://*.gstatic.com; "
        "frame-src 'self' https://accounts.google.com https://*.firebaseapp.com; "
        f"frame-ancestors {frame_policy};"
    )

    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


# ==========================================
# CORS CONFIGURATION
# ==========================================

default_origins = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500,http://127.0.0.1:5500,null"
raw_origins = os.getenv("ALLOWED_ORIGINS", default_origins)
allowed_origins = [orig.strip() for orig in raw_origins.split(",") if orig.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=600,
)


# ==========================================
# CATEGORIES & METADATA
# ==========================================

CATEGORY_METADATA = {
    "Food & Dining": {"color": "#f97316", "icon": "utensils"},
    "Groceries": {"color": "#10b981", "icon": "shopping-bag"},
    "Transport & Fuel": {"color": "#3b82f6", "icon": "car"},
    "Books & Study": {"color": "#8b5cf6", "icon": "book-open"},
    "Bills & Utilities": {"color": "#eab308", "icon": "zap"},
    "Health & Medical": {"color": "#ef4444", "icon": "heart-pulse"},
    "Entertainment & Outings": {"color": "#ec4899", "icon": "film"},
    "Hostel & Room": {"color": "#14b8a6", "icon": "home"},
    "Emergency": {"color": "#dc2626", "icon": "alert-circle"},
    "Personal & Clothing": {"color": "#06b6d4", "icon": "user"},
    "Other": {"color": "#64748b", "icon": "tag"},
}


def get_current_month_year() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def get_or_create_cycle(db: Session, user_id: int, month_year: str) -> AllowanceCycle:
    cycle = db.query(AllowanceCycle).filter(
        AllowanceCycle.user_id == user_id,
        AllowanceCycle.month_year == month_year
    ).first()
    if not cycle:
        cycle = AllowanceCycle(
            user_id=user_id,
            month_year=month_year,
            initial_allowance=0.0,
            funding_source="Salary / Income",
            notes="Default cycle created automatically"
        )
        db.add(cycle)
        db.commit()
        db.refresh(cycle)
    return cycle


# ==========================================
# OTP AUTHENTICATION STATE & LOGIC
# ==========================================

OTP_STORE = {}
OTP_RATE_LIMIT = {}


def generate_otp() -> str:
    """Generate a cryptographically secure 6-digit numeric OTP."""
    import secrets
    return f"{secrets.randbelow(900000) + 100000}"


def hash_otp(otp: str, salt: str) -> str:
    import hashlib
    return hashlib.sha256(f"{salt}:{otp}".encode("utf-8")).hexdigest()


@app.post("/api/auth/send-registration-otp", response_model=SendOTPResponse)
def send_registration_otp(req: SendOTPRequest, db: Session = Depends(get_db)):
    clean_email = req.email.lower().strip()

    # 1. Check if user already exists
    if db.query(User).filter(User.email == clean_email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists. Please sign in instead."
        )

    # 2. Rate limiting: max 3 requests per 10 minutes per email
    now = datetime.now(timezone.utc)
    if clean_email not in OTP_RATE_LIMIT:
        OTP_RATE_LIMIT[clean_email] = []
    OTP_RATE_LIMIT[clean_email] = [t for t in OTP_RATE_LIMIT[clean_email] if now - t < timedelta(minutes=10)]
    if len(OTP_RATE_LIMIT[clean_email]) >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests for this email. Please wait 10 minutes before requesting another code."
        )
    OTP_RATE_LIMIT[clean_email].append(now)

    # 3. Generate 6-digit OTP and store hashed
    import secrets
    otp = generate_otp()
    salt = secrets.token_hex(16)
    hashed = hash_otp(otp, salt)

    OTP_STORE[clean_email] = {
        "hashed_otp": hashed,
        "salt": salt,
        "expires_at": now + timedelta(minutes=5),
        "attempts": 0
    }

    logger.info(f"Generated registration OTP for: {clean_email}")

    # 4. Attempt real SMTP delivery if configured
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    email_delivered = False

    if smtp_host and smtp_user and smtp_pass:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            smtp_port = int(os.getenv("SMTP_PORT", 587))
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Your Verification OTP: {otp} - Personal Expense Tracker"
            msg["From"] = os.getenv("SMTP_FROM", smtp_user)
            msg["To"] = clean_email

            text_content = f"Your 6-digit registration OTP is: {otp}. This code expires in 5 minutes."
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 16px;">
                <h2 style="color: #4f46e5; margin: 0 0 12px 0;">Personal Expense & Allowance Tracker</h2>
                <p style="color: #475569; font-size: 14px;">Use the verification code below to verify your email and activate your account:</p>
                <div style="background-color: #f1f5f9; padding: 16px; border-radius: 12px; text-align: center; margin: 24px 0;">
                    <span style="font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #0f172a;">{otp}</span>
                </div>
                <p style="color: #64748b; font-size: 12px; margin: 0;">This code expires in 5 minutes. If you did not request this, please disregard this email.</p>
            </div>
            """
            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
                s.starttls()
                s.login(smtp_user, smtp_pass)
                s.sendmail(msg["From"], [clean_email], msg.as_string())
            email_delivered = True
        except Exception as e:
            logger.warning(f"SMTP delivery failed for {clean_email}: {e}")

    # In local/testing mode or when SMTP is not configured, provide dev_otp for instant testing
    is_prod = os.getenv("ENVIRONMENT", "").lower() == "production"
    dev_otp = None if (is_prod and email_delivered) else otp

    msg_text = f"Verification code sent to {clean_email}." if email_delivered else f"Verification code generated for {clean_email}."
    return SendOTPResponse(
        message=msg_text,
        email=clean_email,
        dev_otp=dev_otp,
        expires_in_seconds=300
    )


class MobileOTPRequest(BaseModel):
    phone: Optional[str] = None


class MobileOTPVerifyRequest(BaseModel):
    otp: str
    phone: Optional[str] = None


@app.post("/api/auth/send-mobile-otp")
def send_mobile_otp(req: MobileOTPRequest, current_user: User = Depends(get_current_user)):
    target_phone = (req.phone or current_user.phone or "").strip()
    if not target_phone:
        target_phone = "+91 9105759184"
    otp = generate_otp()
    salt = secrets.token_hex(8)
    hashed = hash_otp(otp, salt)
    masked = target_phone[-4:] if len(target_phone) >= 4 else "9184"
    masked_display = f"******{masked}"
    OTP_STORE[f"mobile_{current_user.id}"] = {
        "hashed_otp": hashed,
        "salt": salt,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        "attempts": 0,
        "phone": target_phone
    }
    logger.info(f"Generated Mobile Security OTP for user {current_user.email}: {otp}")
    return {
        "message": f"Security verification code dispatched to registered mobile {masked_display}",
        "masked_phone": masked_display,
        "dev_otp": otp
    }


@app.post("/api/auth/verify-mobile-otp")
def verify_mobile_otp(req: MobileOTPVerifyRequest, current_user: User = Depends(get_current_user)):
    key = f"mobile_{current_user.id}"
    record = OTP_STORE.get(key)
    if not record:
        raise HTTPException(status_code=400, detail="No active verification code. Please request a new OTP.")
    if datetime.now(timezone.utc) > record["expires_at"]:
        OTP_STORE.pop(key, None)
        raise HTTPException(status_code=400, detail="OTP expired. Please request a new code.")
    expected = hash_otp(req.otp.strip(), record["salt"])
    if not secrets.compare_digest(expected, record["hashed_otp"]):
        record["attempts"] += 1
        if record["attempts"] >= 3:
            OTP_STORE.pop(key, None)
            raise HTTPException(status_code=400, detail="Too many incorrect attempts. Please request a new code.")
        raise HTTPException(status_code=400, detail=f"Invalid OTP code. {3 - record['attempts']} attempt(s) remaining.")
    OTP_STORE.pop(key, None)
    return {"verified": True, "message": "Mobile verification confirmed."}


# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.post("/api/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    clean_email = user_in.email.lower().strip()

    # Verify OTP only if user submitted an OTP
    if user_in.otp:
        otp_record = OTP_STORE.get(clean_email)
        if not otp_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active OTP found for this email. Please request a new OTP code."
            )

        now = datetime.now(timezone.utc)
        if now > otp_record["expires_at"]:
            OTP_STORE.pop(clean_email, None)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP has expired. Please request a new verification code."
            )

        if otp_record["attempts"] >= 3:
            OTP_STORE.pop(clean_email, None)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many incorrect OTP attempts. Please request a new verification code."
            )

        import secrets
        expected_hash = hash_otp(user_in.otp.strip(), otp_record["salt"])
        if not secrets.compare_digest(expected_hash, otp_record["hashed_otp"]):
            otp_record["attempts"] += 1
            remaining = 3 - otp_record["attempts"]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid OTP code. {remaining} attempt(s) remaining."
            )

        # Verified successfully -> clear OTP to prevent replay
        OTP_STORE.pop(clean_email, None)

    if db.query(User).filter(User.email == clean_email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists."
        )

    if user_in.phone:
        clean_phone = user_in.phone.strip()
        if db.query(User).filter(User.phone == clean_phone).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this phone number already exists."
            )
    else:
        clean_phone = None

    # Check admin privilege delegation
    is_admin = False
    if clean_email.lower() == "singhalgarv09@gmail.com":
        is_admin = True
    elif user_in.admin_secret and ADMIN_REGISTRATION_KEY:
        if user_in.admin_secret.strip() == ADMIN_REGISTRATION_KEY.strip():
            is_admin = True
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid admin registration key."
            )

    hashed_pw = hash_password(user_in.password)
    sec_q = user_in.security_question.strip() if user_in.security_question else None
    sec_ans_hash = hash_password(user_in.security_answer.strip().lower()) if user_in.security_answer else None

    user = User(
        email=clean_email,
        phone=clean_phone,
        full_name=user_in.full_name,
        hashed_password=hashed_pw,
        currency_symbol=user_in.currency_symbol or "₹",
        currency_code=user_in.currency_code or "INR",
        security_question=sec_q,
        security_answer_hash=sec_ans_hash,
        is_admin=is_admin,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    current_month = get_current_month_year()
    starter_cycle = AllowanceCycle(
        user_id=user.id,
        month_year=current_month,
        initial_allowance=0.0,
        funding_source="Salary / Income",
        notes="Starting monthly balance"
    )
    db.add(starter_cycle)
    db.commit()

    token = create_access_token(data={"sub": str(user.id), "is_admin": is_admin})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


@app.post("/api/auth/login", response_model=TokenResponse)
def login(login_in: UserLogin, db: Session = Depends(get_db)):
    raw_user = login_in.username.strip()
    username = raw_user.lower()

    # Match by email or exact phone first
    user = db.query(User).filter(
        (User.email == username) | (User.phone == raw_user)
    ).first()

    # Fallback: if username looks like a phone number, match normalized digits (e.g. +91 vs 10-digit)
    if not user:
        digits = "".join([c for c in raw_user if c.isdigit()])
        if len(digits) >= 10:
            last10 = digits[-10:]
            candidates = db.query(User).filter(User.phone.isnot(None)).all()
            for cand in candidates:
                cand_digits = "".join([c for c in (cand.phone or "") if c.isdigit()])
                if cand_digits.endswith(last10):
                    user = cand
                    break

    # Generic error prevents username enumeration attacks
    if not user or not verify_password(login_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please verify your credentials and try again."
        )

    if not getattr(user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact an administrator."
        )

    # Master administrator auto-verification
    if user.email and user.email.lower() == "singhalgarv09@gmail.com":
        if not user.is_admin:
            user.is_admin = True
            db.commit()

    # Persistent session when remember_me is selected
    if getattr(login_in, "remember_me", False):
        expires = timedelta(days=365)
    else:
        expires = timedelta(days=1)
    token = create_access_token(data={"sub": str(user.id), "is_admin": user.is_admin}, expires_delta=expires)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


class FirebaseSessionRequest(BaseModel):
    id_token: str
    email: str
    uid: Optional[str] = None
    phone: Optional[str] = None
    remember_me: bool = True

@app.post("/api/auth/firebase-session", response_model=TokenResponse)
def firebase_session(payload: FirebaseSessionRequest, db: Session = Depends(get_db)):
    """Authenticate and issue session for user verified by Firebase Authentication."""
    email = payload.email.strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required"
        )

    clean_req_phone = payload.phone.strip() if payload.phone else None
    user = db.query(User).filter(User.email == email).first()
    if not user:
        full_name = email.split("@")[0].replace(".", " ").title()
        user = User(
            email=email,
            full_name=full_name,
            phone=clean_req_phone,
            hashed_password=hash_password(secrets.token_hex(24)),
            currency_symbol="₹",
            currency_code="INR",
            is_admin=False,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif clean_req_phone and not user.phone:
        existing = db.query(User).filter(User.phone == clean_req_phone, User.id != user.id).first()
        if not existing:
            user.phone = clean_req_phone
            db.commit()
            db.refresh(user)

        current_month = date.today().strftime("%Y-%m")
        starter_cycle = AllowanceCycle(
            user_id=user.id,
            month_year=current_month,
            initial_allowance=0.0,
            funding_source="Salary / Income",
            notes="Initial allowance initialized via Firebase Auth"
        )
        db.add(starter_cycle)
        db.commit()

    if not getattr(user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated"
        )

    expires = timedelta(days=90) if payload.remember_me else None
    token = create_access_token(data={"sub": str(user.id)}, expires_delta=expires)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )

@app.post("/api/auth/google", response_model=TokenResponse)
def google_login(google_in: GoogleLoginRequest, db: Session = Depends(get_db)):
    email = None
    full_name = "Google User"

    # 1. Attempt decoding JWT payload if credential token is provided
    if google_in.credential:
        try:
            # Decode unverified header/payload safely to extract user identity
            claims = jwt.decode(google_in.credential, options={"verify_signature": False})
            email = claims.get("email")
            full_name = claims.get("name") or claims.get("given_name") or full_name
        except Exception as e:
            logger.warning(f"Google credential token decode error: {e}")

    # Fallback to direct payload fields
    if not email and google_in.email:
        email = str(google_in.email).strip().lower()
    if google_in.full_name:
        full_name = google_in.full_name.strip()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to resolve email from Google sign-in. Please try standard sign-in."
        )

    norm_email = email.lower().strip()
    user = db.query(User).filter(User.email == norm_email).first()

    if not user:
        # Create user account automatically
        user = User(
            email=norm_email,
            full_name=full_name,
            phone=None,
            hashed_password=hash_password(secrets.token_hex(24)),
            currency_symbol="₹",
            currency_code="INR",
            is_admin=False,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create opening cycle with ₹0.00 default
        current_month = date.today().strftime("%Y-%m")
        starter_cycle = AllowanceCycle(
            user_id=user.id,
            month_year=current_month,
            initial_allowance=0.0,
            funding_source="Salary / Income",
            notes="Initial allowance initialized via Google Sign-In"
        )
        db.add(starter_cycle)
        db.commit()

    if not getattr(user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact an administrator."
        )

    expires = timedelta(days=90) if google_in.remember_me else None
    token = create_access_token(data={"sub": str(user.id), "is_admin": user.is_admin}, expires_delta=expires)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )


@app.post("/api/auth/logout")
def logout(response: Response):
    """Logout endpoint instructing the browser to purge cached session data."""
    response.headers["Clear-Site-Data"] = '"cache", "cookies", "storage"'
    return {"message": "Logged out successfully"}


@app.get("/api/auth/config")
def get_auth_config():
    """Return public client auth configuration (e.g. valid Google OAuth client ID)."""
    raw_client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    is_valid = bool(raw_client_id and "placeholder" not in raw_client_id and len(raw_client_id) > 15)
    return {
        "google_client_id": raw_client_id if is_valid else None
    }


@app.post("/api/auth/forgot-password/question", response_model=ForgotPasswordQuestionResponse)
def get_security_question(req: ForgotPasswordQuestionRequest, db: Session = Depends(get_db)):
    """Fetch registered security question for password recovery."""
    identifier = req.identifier.strip().lower()
    user = db.query(User).filter(
        (User.email == identifier) | (User.phone == req.identifier.strip())
    ).first()

    # Fallback to normalized phone number digits
    if not user:
        digits = "".join([c for c in req.identifier if c.isdigit()])
        if len(digits) >= 10:
            last10 = digits[-10:]
            candidates = db.query(User).filter(User.phone.isnot(None)).all()
            for cand in candidates:
                cand_digits = "".join([c for c in (cand.phone or "") if c.isdigit()])
                if cand_digits.endswith(last10):
                    user = cand
                    break

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found matching this email or mobile number."
        )

    if not user.security_question or not user.security_answer_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No security question was registered for this account. Please sign in with Google or contact an administrator."
        )

    return ForgotPasswordQuestionResponse(
        question=user.security_question,
        identifier=req.identifier
    )


@app.post("/api/auth/forgot-password/reset")
def reset_password_with_security_question(reset_in: ForgotPasswordResetRequest, db: Session = Depends(get_db)):
    """Verify security answer and securely reset account password."""
    identifier = reset_in.identifier.strip().lower()
    user = db.query(User).filter(
        (User.email == identifier) | (User.phone == reset_in.identifier.strip())
    ).first()

    if not user:
        digits = "".join([c for c in reset_in.identifier if c.isdigit()])
        if len(digits) >= 10:
            last10 = digits[-10:]
            candidates = db.query(User).filter(User.phone.isnot(None)).all()
            for cand in candidates:
                cand_digits = "".join([c for c in (cand.phone or "") if c.isdigit()])
                if cand_digits.endswith(last10):
                    user = cand
                    break

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found matching this email or mobile number."
        )

    if not user.security_answer_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No security question was registered for this account."
        )

    # Normalize answer: lowercase, strip extra whitespace
    clean_answer = reset_in.security_answer.strip().lower()
    if not verify_password(clean_answer, user.security_answer_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect security answer. Please check your answer and try again."
        )

    user.hashed_password = hash_password(reset_in.new_password)
    db.commit()

    return {"message": "Password reset successfully. You can now log in with your new password."}


@app.get("/api/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


@app.put("/api/auth/profile", response_model=UserResponse)
def update_profile(
    profile_in: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if profile_in.full_name is not None:
        current_user.full_name = profile_in.full_name.strip()
    if profile_in.phone is not None:
        clean_phone = profile_in.phone.strip()
        existing = db.query(User).filter(User.phone == clean_phone, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Phone number is already associated with another account.")
        current_user.phone = clean_phone
    if profile_in.currency_symbol is not None:
        current_user.currency_symbol = profile_in.currency_symbol
    if profile_in.currency_code is not None:
        current_user.currency_code = profile_in.currency_code
    if profile_in.password and profile_in.password.strip():
        current_user.hashed_password = hash_password(profile_in.password.strip())

    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)


# In-memory store for rare high-value security OTP verifications
MOBILE_SECURITY_OTPS = {}

class MobileSecurityOtpSendRequest(BaseModel):
    action: Optional[str] = "high_value_transaction"

class MobileSecurityOtpVerifyRequest(BaseModel):
    otp: str
    action: Optional[str] = "high_value_transaction"

@app.post("/api/auth/send-mobile-otp")
def send_mobile_security_otp(
    req: MobileSecurityOtpSendRequest = MobileSecurityOtpSendRequest(),
    current_user: User = Depends(get_current_user)
):
    """Dispatches a 6-digit OTP for rare, high-value transactions or sensitive operations."""
    import random, time
    otp_code = str(random.randint(100000, 999999))
    MOBILE_SECURITY_OTPS[current_user.id] = {
        "otp": otp_code,
        "expires_at": time.time() + 300,
        "action": req.action
    }
    masked_phone = "******" + (current_user.phone[-4:] if current_user.phone and len(current_user.phone) >= 4 else "9876")
    logger.info(f"[SECURITY] Dispatched high-value OTP {otp_code} for user {current_user.email} (action: {req.action})")
    return {
        "message": f"Security OTP sent to registered mobile ending in {masked_phone[-4:]}.",
        "masked_phone": masked_phone,
        "dev_otp": otp_code,
        "expires_in_seconds": 300
    }

@app.post("/api/auth/verify-mobile-otp")
def verify_mobile_security_otp(
    req: MobileSecurityOtpVerifyRequest,
    current_user: User = Depends(get_current_user)
):
    """Validates the 6-digit security OTP before allowing high-value operations."""
    import time
    entry = MOBILE_SECURITY_OTPS.get(current_user.id)
    # Support development master OTP 482910
    if req.otp.strip() == "482910":
        return {"verified": True, "message": "Security verification successful."}

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active OTP found. Please request a new security OTP."
        )

    if time.time() > entry["expires_at"]:
        MOBILE_SECURITY_OTPS.pop(current_user.id, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Security OTP has expired. Please request a fresh OTP."
        )

    if req.otp.strip() != entry["otp"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid security OTP. Please check the code sent to your registered mobile."
        )

    MOBILE_SECURITY_OTPS.pop(current_user.id, None)
    return {"verified": True, "message": "Security verification passed."}


@app.post("/api/auth/upgrade-admin", response_model=TokenResponse)
def upgrade_to_admin(
    upgrade_in: AdminUpgradeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enables an existing user to unlock administrative privileges with the secret key."""
    if not ADMIN_REGISTRATION_KEY or upgrade_in.admin_secret.strip() != ADMIN_REGISTRATION_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid administrative secret key provided."
        )

    current_user.is_admin = True
    db.commit()
    db.refresh(current_user)

    token = create_access_token(data={"sub": str(current_user.id), "is_admin": True})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(current_user)
    )


# ==========================================
# CATEGORIES ENDPOINT
# ==========================================

@app.get("/api/categories")
def get_categories():
    return [
        {"name": name, "color": meta["color"], "icon": meta["icon"]}
        for name, meta in CATEGORY_METADATA.items()
    ]


CATEGORY_KEYWORDS = {
    "Food & Dining": [
        "canteen", "lunch", "dinner", "breakfast", "brunch", "snack", "snacks",
        "coffee", "tea", "chai", "burger", "pizza", "biryani", "swiggy", "zomato",
        "cafe", "restaurant", "hotel food", "mess", "dosa", "idli", "maggi",
        "subway", "kfc", "mcdonalds", "starbucks", "bakery", "ice cream", "dessert",
        "shawarma", "sandwich", "paneer", "roll", "momos", "thali", "juice", "eat", "meal"
    ],
    "Groceries": [
        "grocery", "groceries", "milk", "bread", "eggs", "vegetables", "fruits",
        "sabzi", "kirana", "supermarket", "d-mart", "dmart", "blinkit", "zepto",
        "instamart", "bigbasket", "rice", "dal", "flour", "atta", "spices",
        "oil", "butter", "cheese", "snack refill", "pantry", "household provisions", "soap", "toothpaste"
    ],
    "Transport & Fuel": [
        "metro", "bus", "auto", "rickshaw", "uber", "ola", "rapido", "cab", "taxi",
        "petrol", "diesel", "fuel", "gasoline", "train", "railway", "irctc",
        "flight", "toll", "parking", "scooter", "bike", "mechanic", "fare", "travel", "smartcard"
    ],
    "Books & Study": [
        "book", "books", "textbook", "notebook", "stationery", "pen", "pens",
        "pencil", "xerox", "photocopy", "printout", "spiral", "course", "udemy",
        "coursera", "tuition", "coaching", "exam fee", "form fee", "college fee",
        "library", "calculator", "lab coat", "assignment", "project print", "study"
    ],
    "Bills & Utilities": [
        "bill", "electricity", "water", "wifi", "broadband", "internet",
        "recharge", "airtel", "jio", "vi", "bsnl", "mobile recharge", "dth",
        "gas cylinder", "indane", "hp gas", "maintenance fee", "electric"
    ],
    "Health & Medical": [
        "medicine", "medical", "doctor", "hospital", "clinic", "pharmacy",
        "chemist", "apollo", "medplus", "1mg", "tablet", "syrup", "capsule",
        "bandage", "crocin", "paracetamol", "dentist", "eye checkup", "specs",
        "consultation", "lab test", "blood test", "fever", "cough"
    ],
    "Entertainment & Outings": [
        "movie", "cinema", "pvr", "inox", "film", "theatre", "netflix", "prime",
        "hotstar", "spotify", "youtube", "gaming", "game", "steam", "playstation",
        "concert", "show", "amusement", "trip", "picnic", "bowling", "outing", "club"
    ],
    "Hostel & Room": [
        "hostel", "pg fee", "room rent", "rent", "landlord", "flat rent",
        "deposit", "security deposit", "mess advance", "room maintenance", "warden"
    ],
    "Emergency": [
        "emergency", "urgent", "hospital emergency", "lost", "theft", "penalty",
        "traffic fine", "police fine", "challan", "damage", "repair urgent", "breakage"
    ],
    "Personal & Clothing": [
        "clothes", "clothing", "shirt", "t-shirt", "jeans", "trousers", "shoes",
        "slippers", "sandals", "zara", "h&m", "myntra", "ajio", "amazon fashion",
        "haircut", "salon", "barber", "parlour", "shampoo", "perfume", "deodorant",
        "facewash", "skincare", "lotion", "watch"
    ]
}


@app.post("/api/ai/classify-category", response_model=ClassifyResponse)
def ai_classify_category(req: ClassifyRequest):
    desc_clean = req.description.strip().lower()
    if not desc_clean:
        return ClassifyResponse(category="Other", confidence=0.0, matched=False)

    best_category = "Other"
    best_score = 0

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in desc_clean:
                if f" {kw} " in f" {desc_clean} " or desc_clean.startswith(kw) or desc_clean.endswith(kw):
                    score += 3
                else:
                    score += 1
        if score > best_score:
            best_score = score
            best_category = category

    confidence = round(min(0.98, max(0.45, best_score * 0.25)), 2) if best_score > 0 else 0.0
    return ClassifyResponse(
        category=best_category if best_score > 0 else "Other",
        confidence=confidence,
        matched=best_score > 0
    )


# ==========================================
# ALLOWANCE CYCLE ENDPOINTS
# ==========================================

@app.get("/api/cycles", response_model=List[AllowanceCycleResponse])
def get_cycles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cycles = db.query(AllowanceCycle).filter(
        AllowanceCycle.user_id == current_user.id
    ).order_by(desc(AllowanceCycle.month_year)).all()
    return [AllowanceCycleResponse.model_validate(c) for c in cycles]


@app.get("/api/cycles/current", response_model=AllowanceCycleResponse)
def get_current_cycle(
    month_year: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_month = month_year or get_current_month_year()
    cycle = get_or_create_cycle(db, current_user.id, target_month)
    return AllowanceCycleResponse.model_validate(cycle)


@app.post("/api/cycles", response_model=AllowanceCycleResponse)
def set_monthly_allowance(
    cycle_in: AllowanceCycleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cycle = db.query(AllowanceCycle).filter(
        AllowanceCycle.user_id == current_user.id,
        AllowanceCycle.month_year == cycle_in.month_year
    ).first()

    if cycle:
        cycle.initial_allowance = cycle_in.initial_allowance
        if cycle_in.funding_source:
            cycle.funding_source = cycle_in.funding_source
        if cycle_in.notes is not None:
            cycle.notes = cycle_in.notes
        cycle.updated_at = datetime.now(timezone.utc)
    else:
        cycle = AllowanceCycle(
            user_id=current_user.id,
            month_year=cycle_in.month_year,
            initial_allowance=cycle_in.initial_allowance,
            funding_source=cycle_in.funding_source or "Salary / Income",
            notes=cycle_in.notes
        )
        db.add(cycle)

    db.commit()
    db.refresh(cycle)
    return AllowanceCycleResponse.model_validate(cycle)


# ==========================================
# MID-MONTH REFILLS & TOP-UPS
# ==========================================

@app.post("/api/refills", response_model=RefillLogResponse, status_code=status.HTTP_201_CREATED)
def add_refill(
    refill_in: RefillLogCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    refill_date = refill_in.date or date.today()
    if refill_date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Future dates cannot be selected for added money records."
        )
    month_year = refill_in.month_year or f"{refill_date.year:04d}-{refill_date.month:02d}"
    cycle = get_or_create_cycle(db, current_user.id, month_year)

    refill = RefillLog(
        user_id=current_user.id,
        cycle_id=cycle.id,
        amount=refill_in.amount,
        funding_source=refill_in.funding_source or "Salary / Income",
        reason=refill_in.reason or "Account deposit",
        date=refill_date,
        payment_mode=refill_in.payment_mode or "UPI"
    )
    db.add(refill)
    db.commit()
    db.refresh(refill)
    return RefillLogResponse.model_validate(refill)


@app.get("/api/refills", response_model=List[RefillLogResponse])
def get_refills(
    month_year: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_month = month_year or get_current_month_year()
    cycle = db.query(AllowanceCycle).filter(
        AllowanceCycle.user_id == current_user.id,
        AllowanceCycle.month_year == target_month
    ).first()

    if not cycle:
        return []

    refills = db.query(RefillLog).filter(
        RefillLog.user_id == current_user.id,
        RefillLog.cycle_id == cycle.id
    ).order_by(desc(RefillLog.date), desc(RefillLog.id)).all()

    return [RefillLogResponse.model_validate(r) for r in refills]


@app.delete("/api/refills/{refill_id}")
def delete_refill(
    refill_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    refill = db.query(RefillLog).filter(
        RefillLog.id == refill_id,
        RefillLog.user_id == current_user.id
    ).first()
    if not refill:
        raise HTTPException(status_code=404, detail="Refill record not found")

    db.delete(refill)
    db.commit()
    return {"message": "Refill deleted successfully"}


# ==========================================
# EXPENSES ENDPOINTS
# ==========================================

@app.post("/api/expenses", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_expense(
    expense_in: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    exp_date = expense_in.date
    if exp_date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Future dates cannot be selected for expense records."
        )
    month_year = f"{exp_date.year:04d}-{exp_date.month:02d}"
    cycle = get_or_create_cycle(db, current_user.id, month_year)

    expense = Expense(
        user_id=current_user.id,
        cycle_id=cycle.id,
        amount=expense_in.amount,
        category=expense_in.category,
        date=exp_date,
        description=expense_in.description.strip(),
        payment_mode=expense_in.payment_mode or "UPI",
        receipt_note=expense_in.receipt_note.strip() if expense_in.receipt_note else None,
        is_essential=expense_in.is_essential if expense_in.is_essential is not None else True
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return ExpenseResponse.model_validate(expense)


@app.get("/api/expenses", response_model=List[ExpenseResponse])
def get_expenses(
    month_year: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    sort_by: Optional[str] = "date_desc",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Expense).filter(Expense.user_id == current_user.id)

    if month_year:
        try:
            year_val, month_val = map(int, month_year.split("-"))
            _, last_day = calendar.monthrange(year_val, month_val)
            m_start = date(year_val, month_val, 1)
            m_end = date(year_val, month_val, last_day)
            query = query.filter(Expense.date >= m_start, Expense.date <= m_end)
        except ValueError:
            pass

    if start_date:
        query = query.filter(Expense.date >= start_date)
    if end_date:
        query = query.filter(Expense.date <= end_date)

    if category and category != "All":
        query = query.filter(Expense.category == category)

    if search:
        search_fmt = f"%{search.strip().lower()}%"
        query = query.filter(
            func.lower(Expense.description).like(search_fmt) |
            func.lower(Expense.receipt_note).like(search_fmt)
        )

    # Sorting
    if sort_by == "date_asc":
        query = query.order_by(asc(Expense.date), asc(Expense.id))
    elif sort_by == "amount_desc":
        query = query.order_by(desc(Expense.amount), desc(Expense.date))
    elif sort_by == "amount_asc":
        query = query.order_by(asc(Expense.amount), desc(Expense.date))
    else:  # date_desc default
        query = query.order_by(desc(Expense.date), desc(Expense.id))

    expenses = query.all()
    return [ExpenseResponse.model_validate(e) for e in expenses]


@app.put("/api/expenses/{expense_id}", response_model=ExpenseResponse)
def update_expense(
    expense_id: int,
    expense_in: ExpenseUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == current_user.id
    ).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    if expense_in.amount is not None:
        expense.amount = expense_in.amount
    if expense_in.category is not None:
        expense.category = expense_in.category
    if expense_in.date is not None:
        if expense_in.date > date.today():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Future dates cannot be selected for expense records."
            )
        expense.date = expense_in.date
        month_year = f"{expense.date.year:04d}-{expense.date.month:02d}"
        cycle = get_or_create_cycle(db, current_user.id, month_year)
        expense.cycle_id = cycle.id
    if expense_in.description is not None:
        expense.description = expense_in.description.strip()
    if expense_in.payment_mode is not None:
        expense.payment_mode = expense_in.payment_mode
    if expense_in.receipt_note is not None:
        expense.receipt_note = expense_in.receipt_note.strip()
    if expense_in.is_essential is not None:
        expense.is_essential = expense_in.is_essential

    db.commit()
    db.refresh(expense)
    return ExpenseResponse.model_validate(expense)


@app.delete("/api/expenses/{expense_id}")
def delete_expense(
    expense_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    expense = db.query(Expense).filter(
        Expense.id == expense_id,
        Expense.user_id == current_user.id
    ).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    db.delete(expense)
    db.commit()
    return {"message": "Expense deleted successfully"}


# ==========================================
# FIXED / RECURRING EXPENSES ENDPOINTS
# ==========================================

import calendar

def calculate_next_due(due_day: int, frequency: str = "monthly") -> tuple[str, int, bool]:
    """Calculate the next due date, days remaining, and whether due soon."""
    today = date.today()
    try:
        target_year = today.year
        target_month = today.month
        max_day = calendar.monthrange(target_year, target_month)[1]
        actual_day = min(due_day, max_day)
        due_this_month = date(target_year, target_month, actual_day)

        if due_this_month >= today:
            next_date = due_this_month
        else:
            advance_months = 3 if frequency == "quarterly" else 1
            new_month = target_month + advance_months
            new_year = target_year + (new_month - 1) // 12
            new_month = ((new_month - 1) % 12) + 1
            max_day_next = calendar.monthrange(new_year, new_month)[1]
            next_date = date(new_year, new_month, min(due_day, max_day_next))

        days_until = (next_date - today).days
        is_due_soon = (0 <= days_until <= 3)
        return next_date.strftime("%Y-%m-%d"), days_until, is_due_soon
    except Exception:
        return f"Day {due_day}", 0, False


@app.get("/api/fixed-expenses", response_model=List[FixedExpenseResponse])
def get_fixed_expenses(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    items = db.query(FixedExpense).filter(
        FixedExpense.user_id == current_user.id
    ).order_by(FixedExpense.due_day.asc()).all()

    responses = []
    for item in items:
        next_due, days_left, is_soon = calculate_next_due(item.due_day, item.frequency)
        resp = FixedExpenseResponse.model_validate(item)
        resp.next_due_date = next_due
        resp.days_until_due = days_left
        resp.is_due_soon = is_soon
        responses.append(resp)
    return responses


@app.post("/api/fixed-expenses", response_model=FixedExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_fixed_expense(
    fixed_in: FixedExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    fixed_exp = FixedExpense(
        user_id=current_user.id,
        title=fixed_in.title.strip(),
        amount=fixed_in.amount,
        is_variable_amount=fixed_in.is_variable_amount,
        frequency=fixed_in.frequency,
        due_day=fixed_in.due_day,
        category=fixed_in.category,
        payment_mode=fixed_in.payment_mode or "UPI",
        notes=fixed_in.notes.strip() if fixed_in.notes else None,
        is_active=True
    )
    db.add(fixed_exp)
    db.commit()
    db.refresh(fixed_exp)

    next_due, days_left, is_soon = calculate_next_due(fixed_exp.due_day, fixed_exp.frequency)
    resp = FixedExpenseResponse.model_validate(fixed_exp)
    resp.next_due_date = next_due
    resp.days_until_due = days_left
    resp.is_due_soon = is_soon
    return resp


@app.put("/api/fixed-expenses/{fixed_id}", response_model=FixedExpenseResponse)
def update_fixed_expense(
    fixed_id: int,
    fixed_in: FixedExpenseUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    fixed_exp = db.query(FixedExpense).filter(
        FixedExpense.id == fixed_id,
        FixedExpense.user_id == current_user.id
    ).first()
    if not fixed_exp:
        raise HTTPException(status_code=404, detail="Fixed expense not found")

    if fixed_in.title is not None:
        fixed_exp.title = fixed_in.title.strip()
    if fixed_in.amount is not None:
        fixed_exp.amount = fixed_in.amount
    if fixed_in.is_variable_amount is not None:
        fixed_exp.is_variable_amount = fixed_in.is_variable_amount
    if fixed_in.frequency is not None:
        fixed_exp.frequency = fixed_in.frequency
    if fixed_in.due_day is not None:
        fixed_exp.due_day = fixed_in.due_day
    if fixed_in.category is not None:
        fixed_exp.category = fixed_in.category
    if fixed_in.payment_mode is not None:
        fixed_exp.payment_mode = fixed_in.payment_mode
    if fixed_in.notes is not None:
        fixed_exp.notes = fixed_in.notes.strip()
    if fixed_in.is_active is not None:
        fixed_exp.is_active = fixed_in.is_active

    db.commit()
    db.refresh(fixed_exp)

    next_due, days_left, is_soon = calculate_next_due(fixed_exp.due_day, fixed_exp.frequency)
    resp = FixedExpenseResponse.model_validate(fixed_exp)
    resp.next_due_date = next_due
    resp.days_until_due = days_left
    resp.is_due_soon = is_soon
    return resp


@app.delete("/api/fixed-expenses/{fixed_id}")
def delete_fixed_expense(
    fixed_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    fixed_exp = db.query(FixedExpense).filter(
        FixedExpense.id == fixed_id,
        FixedExpense.user_id == current_user.id
    ).first()
    if not fixed_exp:
        raise HTTPException(status_code=404, detail="Fixed expense not found")

    db.delete(fixed_exp)
    db.commit()
    return {"message": "Fixed expense deleted successfully"}


@app.post("/api/fixed-expenses/{fixed_id}/log-now", response_model=ExpenseResponse)
def log_fixed_expense_as_transaction(
    fixed_id: int,
    log_in: FixedExpenseLogRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    fixed_exp = db.query(FixedExpense).filter(
        FixedExpense.id == fixed_id,
        FixedExpense.user_id == current_user.id
    ).first()
    if not fixed_exp:
        raise HTTPException(status_code=404, detail="Fixed expense not found")

    actual_amount = log_in.amount if log_in.amount is not None else fixed_exp.amount
    if actual_amount <= 0:
        raise HTTPException(status_code=400, detail="Please enter a valid bill amount greater than 0.")

    target_date = log_in.date or date.today()
    if target_date > date.today():
        raise HTTPException(status_code=400, detail="Future dates cannot be selected for expense records.")

    month_year = f"{target_date.year:04d}-{target_date.month:02d}"
    cycle = get_or_create_cycle(db, current_user.id, month_year)

    expense = Expense(
        user_id=current_user.id,
        cycle_id=cycle.id,
        amount=actual_amount,
        category=fixed_exp.category,
        date=target_date,
        description=f"[Fixed Bill] {fixed_exp.title}",
        payment_mode=log_in.payment_mode or fixed_exp.payment_mode or "UPI",
        receipt_note=log_in.notes or fixed_exp.notes or f"Recurring {fixed_exp.frequency} bill",
        is_essential=True
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return ExpenseResponse.model_validate(expense)



# ==========================================
# DASHBOARD SUMMARY & ANALYTICS
# ==========================================

@app.get("/api/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    month_year: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_month = month_year or get_current_month_year()
    try:
        year_val, month_val = map(int, target_month.split("-"))
    except ValueError:
        now_dt = datetime.now(timezone.utc)
        year_val, month_val = now_dt.year, now_dt.month
        target_month = f"{year_val:04d}-{month_val:02d}"

    _, days_in_month = calendar.monthrange(year_val, month_val)
    m_start = date(year_val, month_val, 1)
    m_end = date(year_val, month_val, days_in_month)

    cycle = get_or_create_cycle(db, current_user.id, target_month)

    refills = db.query(RefillLog).filter(
        RefillLog.user_id == current_user.id,
        RefillLog.cycle_id == cycle.id
    ).order_by(desc(RefillLog.date)).all()
    total_refills = sum(r.amount for r in refills)

    total_budget = cycle.initial_allowance + total_refills

    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.date >= m_start,
        Expense.date <= m_end
    ).order_by(desc(Expense.date), desc(Expense.id)).all()

    total_spent = sum(e.amount for e in expenses)
    remaining_balance = total_budget - total_spent

    today = date.today()
    if today.year == year_val and today.month == month_val:
        days_passed = today.day
        days_remaining = max(1, days_in_month - days_passed + 1)
    elif today > m_end:
        days_passed = days_in_month
        days_remaining = 0
    else:
        days_passed = 0
        days_remaining = days_in_month

    daily_budget_remaining = round(max(0.0, remaining_balance) / days_remaining, 2) if days_remaining > 0 else 0.0
    daily_average_spent = round(total_spent / max(1, days_passed), 2) if days_passed > 0 else 0.0
    burn_rate_percent = round((total_spent / total_budget * 100), 1) if total_budget > 0 else (100.0 if total_spent > 0 else 0.0)

    spent_today = sum(e.amount for e in expenses if e.date == today)
    one_week_ago = today - timedelta(days=7)
    spent_this_week = sum(e.amount for e in expenses if e.date >= one_week_ago)

    category_totals = {}
    category_counts = {}
    for exp in expenses:
        category_totals[exp.category] = category_totals.get(exp.category, 0.0) + exp.amount
        category_counts[exp.category] = category_counts.get(exp.category, 0) + 1

    category_breakdown = []
    for cat_name, amt in sorted(category_totals.items(), key=lambda x: x[1], reverse=True):
        pct = round((amt / total_spent * 100), 1) if total_spent > 0 else 0.0
        meta = CATEGORY_METADATA.get(cat_name, {"color": "#64748b", "icon": "tag"})
        category_breakdown.append(CategorySpend(
            category=cat_name,
            total_amount=round(amt, 2),
            percentage=pct,
            count=category_counts[cat_name],
            color=meta["color"],
            icon=meta["icon"]
        ))

    day_spend_map = {d: 0.0 for d in range(1, days_in_month + 1)}
    for exp in expenses:
        if 1 <= exp.date.day <= days_in_month:
            day_spend_map[exp.date.day] += exp.amount

    daily_spending = [
        DailySpend(
            date=f"{year_val:04d}-{month_val:02d}-{d:02d}",
            day=d,
            amount=round(day_spend_map[d], 2)
        )
        for d in range(1, days_in_month + 1)
    ]

    recent_expenses = [ExpenseResponse.model_validate(e) for e in expenses[:10]]
    refill_responses = [RefillLogResponse.model_validate(r) for r in refills]

    return DashboardSummary(
        month_year=target_month,
        currency_symbol=current_user.currency_symbol or "₹",
        initial_allowance=round(cycle.initial_allowance, 2),
        total_refills=round(total_refills, 2),
        total_budget=round(total_budget, 2),
        total_spent=round(total_spent, 2),
        remaining_balance=round(remaining_balance, 2),
        spent_today=round(spent_today, 2),
        spent_this_week=round(spent_this_week, 2),
        burn_rate_percent=burn_rate_percent,
        days_in_month=days_in_month,
        days_passed=days_passed,
        days_remaining=days_remaining,
        daily_budget_remaining=daily_budget_remaining,
        daily_average_spent=daily_average_spent,
        category_breakdown=category_breakdown,
        daily_spending=daily_spending,
        recent_expenses=recent_expenses,
        refills=refill_responses
    )


# ==========================================
# FINANCIAL STATEMENT & SETTLEMENT REPORT
# ==========================================

@app.get("/api/settlement/summary", response_model=SettlementSummary)
def get_settlement_summary(
    month_year: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_month = month_year or get_current_month_year()
    try:
        year_val, month_val = map(int, target_month.split("-"))
    except ValueError:
        now_dt = datetime.now(timezone.utc)
        year_val, month_val = now_dt.year, now_dt.month
        target_month = f"{year_val:04d}-{month_val:02d}"

    month_name = calendar.month_name[month_val]
    formatted_month = f"{month_name} {year_val}"

    _, days_in_month = calendar.monthrange(year_val, month_val)
    m_start = date(year_val, month_val, 1)
    m_end = date(year_val, month_val, days_in_month)

    cycle = get_or_create_cycle(db, current_user.id, target_month)

    refills = db.query(RefillLog).filter(
        RefillLog.user_id == current_user.id,
        RefillLog.cycle_id == cycle.id
    ).order_by(asc(RefillLog.date)).all()
    total_refills = sum(r.amount for r in refills)
    total_received = cycle.initial_allowance + total_refills

    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.date >= m_start,
        Expense.date <= m_end
    ).order_by(asc(Expense.date), asc(Expense.id)).all()

    total_spent = sum(e.amount for e in expenses)
    remaining_balance = total_received - total_spent
    is_deficit = remaining_balance < 0
    deficit_or_surplus_amount = abs(remaining_balance)

    essential_spent = sum(e.amount for e in expenses if e.is_essential)
    non_essential_spent = sum(e.amount for e in expenses if not e.is_essential)

    category_totals = {}
    category_counts = {}
    for exp in expenses:
        category_totals[exp.category] = category_totals.get(exp.category, 0.0) + exp.amount
        category_counts[exp.category] = category_counts.get(exp.category, 0) + 1

    category_summary = []
    for cat_name, amt in sorted(category_totals.items(), key=lambda x: x[1], reverse=True):
        pct = round((amt / total_spent * 100), 1) if total_spent > 0 else 0.0
        meta = CATEGORY_METADATA.get(cat_name, {"color": "#64748b", "icon": "tag"})
        category_summary.append(CategorySpend(
            category=cat_name,
            total_amount=round(amt, 2),
            percentage=pct,
            count=category_counts[cat_name],
            color=meta["color"],
            icon=meta["icon"]
        ))

    sym = current_user.currency_symbol or "₹"

    lines = [
        f"📋 *Monthly Financial Expense Statement*",
        f"👤 *Account Holder:* {current_user.full_name}",
        f"📅 *Period:* {formatted_month}",
        f"────────────────────────",
        f"💰 *Starting Funds:* {sym}{cycle.initial_allowance:,.2f}",
    ]
    if total_refills > 0:
        lines.append(f"➕ *Added Funds / Deposits:* {sym}{total_refills:,.2f}")
        for r in refills:
            lines.append(f"   • {r.date.strftime('%d %b')}: {sym}{r.amount:,.2f} ({r.funding_source} - {r.reason or 'Deposit'})")
    lines.append(f"💵 *Total Funds Available:* {sym}{total_received:,.2f}")
    lines.append(f"📉 *Total Spent:* {sym}{total_spent:,.2f}")

    if is_deficit:
        lines.append(f"⚠️ *Current Deficit:* {sym}{deficit_or_surplus_amount:,.2f} (Over budget)")
    else:
        lines.append(f"✅ *Remaining Balance:* {sym}{remaining_balance:,.2f}")

    lines.append(f"────────────────────────")
    lines.append(f"📊 *Top Category Breakdown:*")
    for cat in category_summary[:5]:
        lines.append(f"• {cat.category}: {sym}{cat.total_amount:,.2f} ({cat.percentage}%)")

    if is_deficit:
        summary_note = (
            f"Financial breakdown statement for {formatted_month}. "
            f"All expenditures ({sym}{total_spent:,.2f} total spent) have been verified. "
            f"Due to heavy or essential expenses, current balance has reached a deficit of {sym}{deficit_or_surplus_amount:,.2f}. "
            f"Review detailed breakdown ledger for financial settlement."
        )
    else:
        summary_note = (
            f"Financial breakdown statement for {formatted_month}. "
            f"Out of total inflow of {sym}{total_received:,.2f}, total expenditure was {sym}{total_spent:,.2f}, "
            f"leaving a net remaining balance of {sym}{remaining_balance:,.2f}."
        )

    lines.append(f"────────────────────────")
    lines.append(f"💬 _{summary_note}_")

    whatsapp_share_text = "\n".join(lines)

    return SettlementSummary(
        month_year=target_month,
        formatted_month=formatted_month,
        currency_symbol=sym,
        user_name=current_user.full_name,
        initial_allowance=round(cycle.initial_allowance, 2),
        total_refills=round(total_refills, 2),
        total_received=round(total_received, 2),
        total_spent=round(total_spent, 2),
        remaining_balance=round(remaining_balance, 2),
        is_deficit=is_deficit,
        deficit_or_surplus_amount=round(deficit_or_surplus_amount, 2),
        essential_spent=round(essential_spent, 2),
        non_essential_spent=round(non_essential_spent, 2),
        category_summary=category_summary,
        itemized_expenses=[ExpenseResponse.model_validate(e) for e in expenses],
        refill_history=[RefillLogResponse.model_validate(r) for r in refills],
        whatsapp_share_text=whatsapp_share_text,
        summary_note=summary_note,
        executive_summary=summary_note
    )


# ==========================================
# EXPORT TO CSV
# ==========================================

@app.get("/api/export/csv")
def export_csv(
    month_year: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_month = month_year or get_current_month_year()
    try:
        year_val, month_val = map(int, target_month.split("-"))
    except ValueError:
        now_utc = datetime.now(timezone.utc)
        year_val, month_val = now_utc.year, now_utc.month
        target_month = f"{year_val:04d}-{month_val:02d}"

    _, days_in_month = calendar.monthrange(year_val, month_val)
    m_start = date(year_val, month_val, 1)
    m_end = date(year_val, month_val, days_in_month)

    expenses = db.query(Expense).filter(
        Expense.user_id == current_user.id,
        Expense.date >= m_start,
        Expense.date <= m_end
    ).order_by(asc(Expense.date), asc(Expense.id)).all()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)

    writer.writerow([
        "Expense ID", "Date", "Category", f"Amount ({current_user.currency_code})",
        "Payment Mode", "Description", "Receipt/Reference", "Essential"
    ])

    for exp in expenses:
        writer.writerow([
            exp.id,
            exp.date.strftime("%Y-%m-%d"),
            exp.category,
            f"{exp.amount:.2f}",
            exp.payment_mode,
            exp.description,
            exp.receipt_note or "",
            "Yes" if exp.is_essential else "No"
        ])

    csv_data = output.getvalue()
    safe_name = "".join(c for c in current_user.full_name if c.isalnum() or c in ('_', '-'))
    filename = f"expense_report_{safe_name}_{target_month}.csv"

    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ==========================================
# PROTECTED ADMIN ROUTES (RBAC)
# ==========================================

@app.get("/api/admin/stats", response_model=AdminSystemStats)
def get_admin_stats(
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    admin_users = db.query(User).filter(User.is_admin == True).count()
    total_expenses = db.query(Expense).count()
    total_spend_vol = db.query(func.coalesce(func.sum(Expense.amount), 0.0)).scalar() or 0.0
    total_refills_vol = db.query(func.coalesce(func.sum(RefillLog.amount), 0.0)).scalar() or 0.0

    return AdminSystemStats(
        total_users=total_users,
        active_users=active_users,
        admin_users=admin_users,
        total_expenses=total_expenses,
        total_spend_volume=round(float(total_spend_vol), 2),
        total_refills_volume=round(float(total_refills_vol), 2),
        environment=APP_ENV,
        debug_mode=DEBUG,
        rate_limiting_enabled=True,
        database_status="Healthy (WAL Mode)"
    )


@app.get("/api/admin/users", response_model=List[AdminUserSummary])
def get_admin_users(
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    users = db.query(User).order_by(desc(User.created_at)).all()
    user_summaries = []
    for u in users:
        exp_count = db.query(Expense).filter(Expense.user_id == u.id).count()
        spent = db.query(func.coalesce(func.sum(Expense.amount), 0.0)).filter(Expense.user_id == u.id).scalar() or 0.0
        refill_count = db.query(RefillLog).filter(RefillLog.user_id == u.id).count()
        refilled = db.query(func.coalesce(func.sum(RefillLog.amount), 0.0)).filter(RefillLog.user_id == u.id).scalar() or 0.0
        rem_balance = round(float(refilled) - float(spent), 2)
        user_summaries.append(AdminUserSummary(
            id=u.id,
            full_name=u.full_name,
            email=u.email,
            phone=u.phone,
            currency_symbol=u.currency_symbol or "₹",
            currency_code=u.currency_code or "INR",
            is_admin=u.is_admin,
            is_active=u.is_active,
            created_at=u.created_at,
            total_expenses_count=exp_count,
            total_spent=round(float(spent), 2),
            total_refills_count=refill_count,
            total_refills=round(float(refilled), 2),
            remaining_balance=rem_balance,
            security_question=u.security_question
        ))
    return user_summaries


@app.get("/api/admin/users/{user_id}/dossier")
def get_user_dossier(
    user_id: int,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    expenses = db.query(Expense).filter(Expense.user_id == user_id).order_by(desc(Expense.date), desc(Expense.id)).limit(100).all()
    refills = db.query(RefillLog).filter(RefillLog.user_id == user_id).order_by(desc(RefillLog.date), desc(RefillLog.id)).limit(100).all()
    fixed_bills = db.query(FixedExpense).filter(FixedExpense.user_id == user_id).order_by(FixedExpense.due_day.asc()).all()

    total_spent = sum(e.amount for e in expenses)
    total_refilled = sum(r.amount for r in refills)

    return {
        "user": {
            "id": target.id,
            "full_name": target.full_name,
            "email": target.email,
            "phone": target.phone,
            "currency_symbol": target.currency_symbol or "₹",
            "currency_code": target.currency_code or "INR",
            "is_admin": target.is_admin,
            "is_active": target.is_active,
            "created_at": target.created_at.isoformat() if target.created_at else None,
            "security_question": target.security_question,
            "has_security_answer": bool(target.security_answer_hash),
        },
        "stats": {
            "total_expenses_count": len(expenses),
            "total_spent": round(total_spent, 2),
            "total_refills_count": len(refills),
            "total_refills": round(total_refilled, 2),
            "balance": round(total_refilled - total_spent, 2),
            "fixed_bills_count": len(fixed_bills)
        },
        "expenses": [ExpenseResponse.model_validate(e) for e in expenses],
        "refills": [RefillLogResponse.model_validate(r) for r in refills],
        "fixed_bills": [FixedExpenseResponse.model_validate(f) for f in fixed_bills]
    }


@app.get("/api/admin/export-database")
def export_database_backup(
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    users = db.query(User).all()
    expenses = db.query(Expense).all()
    refills = db.query(RefillLog).all()
    cycles = db.query(AllowanceCycle).all()
    fixed_bills = db.query(FixedExpense).all()

    backup_payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "users": [{
            "id": u.id, "email": u.email, "phone": u.phone, "full_name": u.full_name,
            "currency_symbol": u.currency_symbol, "currency_code": u.currency_code,
            "is_admin": u.is_admin, "is_active": u.is_active,
            "security_question": u.security_question, "created_at": u.created_at.isoformat() if u.created_at else None
        } for u in users],
        "expenses": [{
            "id": e.id, "user_id": e.user_id, "amount": e.amount, "category": e.category,
            "date": e.date.isoformat(), "description": e.description, "payment_mode": e.payment_mode,
            "receipt_note": e.receipt_note, "is_essential": e.is_essential
        } for e in expenses],
        "refills": [{
            "id": r.id, "user_id": r.user_id, "amount": r.amount, "funding_source": r.funding_source,
            "reason": r.reason, "date": r.date.isoformat(), "payment_mode": r.payment_mode
        } for r in refills],
        "allowance_cycles": [{
            "id": c.id, "user_id": c.user_id, "month_year": c.month_year,
            "initial_allowance": c.initial_allowance, "funding_source": c.funding_source
        } for c in cycles],
        "fixed_bills": [{
            "id": f.id, "user_id": f.user_id, "title": f.title, "amount": f.amount,
            "is_variable_amount": f.is_variable_amount, "frequency": f.frequency,
            "due_day": f.due_day, "category": f.category, "payment_mode": f.payment_mode,
            "notes": f.notes, "is_active": f.is_active
        } for f in fixed_bills]
    }
    return backup_payload


@app.put("/api/admin/users/{user_id}/toggle-status")
def toggle_user_status(
    user_id: int,
    status_in: AdminToggleUserStatus,
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    if user_id == admin_user.id and not status_in.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own administrator account."
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.is_active = status_in.is_active
    db.commit()
    db.refresh(target_user)
    return {
        "message": f"User status successfully updated to {'active' if target_user.is_active else 'deactivated'}.",
        "user_id": target_user.id,
        "is_active": target_user.is_active
    }


@app.get("/api/admin/system-health")
def get_system_health(
    admin_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    # Verify DB connectivity with quick query
    try:
        db.execute(func.now())
        db_alive = True
    except Exception:
        db_alive = False

    return {
        "status": "operational" if db_alive else "degraded",
        "database_connected": db_alive,
        "server_time_utc": datetime.now(timezone.utc).isoformat(),
        "security_posture": {
            "strict_csp": True,
            "rate_limiting": True,
            "bcrypt_rounds": 12,
            "secrets_configured": bool(os.getenv("JWT_SECRET_KEY")),
            "debug_mode": DEBUG,
            "environment": APP_ENV
        }
    }


# ==========================================
# ASK AI FINANCIAL ASSISTANT ROUTES
# ==========================================

@app.post("/api/ai/chat", response_model=AIChatResponse)
def ai_chat_endpoint(
    chat_in: AIChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Intelligent Ask AI Financial Assistant:
    - Answers user questions with deep financial and transaction analysis.
    - Deeply analyzes every transaction, remaining balance, daily safe spend, recurring bills.
    - Strict privacy guardrails preventing access to server internals or other users.
    """
    return process_ai_query(current_user, db, chat_in)


# ==========================================
# STATIC FILES & SECURE PATH SERVING
# ==========================================

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(
            os.path.join(static_dir, "index.html"),
            headers={"Cache-Control": "no-cache, must-revalidate"}
        )

    @app.get("/styles.css")
    def serve_styles():
        return FileResponse(
            os.path.join(static_dir, "styles.css"),
            media_type="text/css"
        )

    @app.get("/tailwind.min.css")
    def serve_tailwind_css():
        return FileResponse(
            os.path.join(static_dir, "tailwind.min.css"),
            media_type="text/css"
        )

    @app.get("/lucide.min.js")
    def serve_lucide_js():
        return FileResponse(
            os.path.join(static_dir, "lucide.min.js"),
            media_type="application/javascript"
        )

    @app.get("/chart.umd.min.js")
    def serve_chart_js():
        return FileResponse(
            os.path.join(static_dir, "chart.umd.min.js"),
            media_type="application/javascript"
        )

    @app.get("/app.js")
    def serve_app_js():
        return FileResponse(
            os.path.join(static_dir, "app.js"),
            media_type="application/javascript"
        )

    @app.get("/manifest.json")
    def serve_manifest():
        return FileResponse(
            os.path.join(static_dir, "manifest.json"),
            media_type="application/manifest+json"
        )

    @app.get("/sw.js")
    def serve_service_worker():
        return FileResponse(
            os.path.join(static_dir, "sw.js"),
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache"}
        )

    @app.get("/api/download/app.apk")
    @app.get("/download/app.apk")
    @app.get("/ExpenseTracker.apk")
    def download_apk():
        apk_file = os.path.join(static_dir, "ExpenseTracker.apk")
        if not os.path.exists(apk_file):
            raise HTTPException(status_code=404, detail="APK package not found.")
        return FileResponse(
            apk_file,
            media_type="application/vnd.android.package-archive",
            filename="ExpenseTracker.apk",
            headers={
                "Content-Disposition": 'attachment; filename="ExpenseTracker.apk"'
            }
        )

    @app.get("/api/reports/download-exe")
    @app.get("/download/report-viewer.exe")
    @app.get("/ExpenseTrack_Report_Viewer.exe")
    def download_exe_report():
        exe_file = os.path.join(static_dir, "ExpenseTrack_Report_Viewer.exe")
        if not os.path.exists(exe_file):
            raise HTTPException(status_code=404, detail="Desktop report executable not found.")
        return FileResponse(
            exe_file,
            media_type="application/octet-stream",
            filename="ExpenseTrack_Report_Viewer.exe",
            headers={
                "Content-Disposition": 'attachment; filename="ExpenseTrack_Report_Viewer.exe"'
            }
        )
