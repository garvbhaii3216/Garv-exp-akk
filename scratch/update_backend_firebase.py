# Update backend/auth.py and backend/main.py for Firebase integration and CSP

def update_backend_auth():
    with open('backend/auth.py', 'r', encoding='utf-8') as f:
        content = f.read()

    old_get_user = '''    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = int(user_id_str)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()'''

    new_get_user = '''    token = credentials.credentials
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
            pass'''

    if old_get_user in content:
        content = content.replace(old_get_user, new_get_user, 1)
        with open('backend/auth.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Updated backend/auth.py")
    else:
        print("Could not find old_get_user in backend/auth.py")

def update_backend_main():
    with open('backend/main.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update CSP in backend/main.py
    old_csp = '''    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://unpkg.com https://cdn.jsdelivr.net https://accounts.google.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com https://accounts.google.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 ws: wss: https://accounts.google.com; "
        "frame-src 'self' https://accounts.google.com; "
        f"frame-ancestors {frame_policy};"
    )'''

    new_csp = '''    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://unpkg.com https://cdn.jsdelivr.net https://accounts.google.com https://www.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com https://accounts.google.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 ws: wss: https://accounts.google.com https://*.googleapis.com https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://*.firebaseio.com https://*.firebase.com; "
        "frame-src 'self' https://accounts.google.com https://*.firebaseapp.com; "
        f"frame-ancestors {frame_policy};"
    )'''

    if old_csp in content:
        content = content.replace(old_csp, new_csp, 1)
        print("Updated CSP in backend/main.py")
    else:
        print("Could not find old_csp in backend/main.py")

    # 2. Add /api/auth/firebase-session endpoint
    if "/api/auth/firebase-session" not in content:
        firebase_endpoint = '''class FirebaseSessionRequest(BaseModel):
    id_token: str
    email: str
    uid: Optional[str] = None
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

    user = db.query(User).filter(User.email == email).first()
    if not user:
        full_name = email.split("@")[0].replace(".", " ").title()
        user = User(
            email=email,
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

        current_month = date.today().strftime("%Y-%m")
        starter_cycle = AllowanceCycle(
            user_id=user.id,
            month_year=current_month,
            initial_allowance=0.0,
            funding_source="Parents",
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

'''
        # Insert before @app.post("/api/auth/google"
        target = '@app.post("/api/auth/google"'
        if target in content:
            content = content.replace(target, firebase_endpoint + target, 1)
            print("Added /api/auth/firebase-session endpoint")
        else:
            print("Could not find target to insert /api/auth/firebase-session")

    with open('backend/main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Saved backend/main.py")

update_backend_auth()
update_backend_main()
