import pytest
from datetime import datetime, timezone
import jwt
from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import SECRET_KEY, ALGORITHM
from backend.tests.conftest import TestingSessionLocal
from backend.models import User, AllowanceCycle
from backend.rate_limiter import rate_limiter

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_test_env():
    rate_limiter.requests.clear()
    yield


def test_login_remember_me_extended_session():
    # Create or ensure user
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "student.remember@example.com").first()
        if not user:
            client.post(
                "/api/auth/register",
                json={
                    "full_name": "Remember Student",
                    "email": "student.remember@example.com",
                    "password": "Password123!",
                    "currency_symbol": "₹",
                    "currency_code": "INR"
                }
            )

        # Standard login without remember_me
        res_normal = client.post(
            "/api/auth/login",
            json={"username": "student.remember@example.com", "password": "Password123!", "remember_me": False}
        )
        assert res_normal.status_code == 200
        token_normal = res_normal.json()["access_token"]
        payload_normal = jwt.decode(token_normal, SECRET_KEY, algorithms=[ALGORITHM])
        exp_normal = payload_normal["exp"]

        # Extended login with remember_me
        res_remember = client.post(
            "/api/auth/login",
            json={"username": "student.remember@example.com", "password": "Password123!", "remember_me": True}
        )
        assert res_remember.status_code == 200
        token_remember = res_remember.json()["access_token"]
        payload_remember = jwt.decode(token_remember, SECRET_KEY, algorithms=[ALGORITHM])
        exp_remember = payload_remember["exp"]

        # Extended expiration must be significantly longer (> 60 days in seconds)
        assert exp_remember - exp_normal > 60 * 24 * 3600
    finally:
        db.close()


def test_google_login_new_user_and_zero_allowance():
    test_google_email = "alex.google.user@example.com"
    res = client.post(
        "/api/auth/google",
        json={
            "email": test_google_email,
            "full_name": "Alex Google",
            "remember_me": True
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == test_google_email
    assert data["user"]["full_name"] == "Alex Google"

    # Verify user exists in database
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == test_google_email).first()
        assert user is not None
        assert user.currency_symbol == "₹"

        # Verify starter cycle was initialized with strictly 0.00 initial allowance
        cycles = db.query(AllowanceCycle).filter(AllowanceCycle.user_id == user.id).all()
        assert len(cycles) >= 1
        assert cycles[0].initial_allowance == 0.0
    finally:
        db.close()


def test_google_login_existing_user():
    test_email = "alex.google.user@example.com"
    res = client.post(
        "/api/auth/google",
        json={
            "email": test_email,
            "full_name": "Alex Google Updated",
            "remember_me": True
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == test_email
