import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from backend.main import app, OTP_STORE
from backend.database import SessionLocal
from backend.models import User

client = TestClient(app)


def test_otp_generation_and_verification():
    test_email = "newstudent_otp@example.com"
    # Clean any leftover
    OTP_STORE.pop(test_email, None)

    # 1. Send OTP
    res = client.post("/api/auth/send-registration-otp", json={"email": test_email})
    assert res.status_code == 200
    data = res.json()
    assert "dev_otp" in data
    dev_otp = data["dev_otp"]
    assert len(dev_otp) == 6
    assert dev_otp.isdigit()

    # 2. Registration with WRONG OTP must fail
    fail_res = client.post(
        "/api/auth/register",
        json={
            "full_name": "Test Student",
            "email": test_email,
            "password": "ValidPassword123!",
            "otp": "000000"
        }
    )
    assert fail_res.status_code == 400
    assert "Invalid OTP code" in fail_res.json()["detail"]

    # 3. Registration with CORRECT OTP must succeed
    success_res = client.post(
        "/api/auth/register",
        json={
            "full_name": "Test Student",
            "email": test_email,
            "password": "ValidPassword123!",
            "otp": dev_otp
        }
    )
    assert success_res.status_code == 201
    reg_data = success_res.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["email"] == test_email

    # 4. OTP should now be consumed (replay prevention)
    replay_res = client.post(
        "/api/auth/register",
        json={
            "full_name": "Test Student 2",
            "email": test_email,
            "password": "ValidPassword123!",
            "otp": dev_otp
        }
    )
    assert replay_res.status_code == 400

    # 5. Requesting OTP for already existing account must fail
    dup_res = client.post("/api/auth/send-registration-otp", json={"email": test_email})
    assert dup_res.status_code == 400
    assert "already exists" in dup_res.json()["detail"]


def test_account_immutability_triggers():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "newstudent_otp@example.com").first()
        if not user:
            user = db.query(User).first()
        assert user is not None

        # Attempt DELETE directly via SQL
        with pytest.raises(Exception) as exc_delete:
            db.execute(text(f"DELETE FROM users WHERE id = {user.id}"))
            db.commit()
        assert "ACCOUNT IMMUTABILITY: User accounts cannot be deleted once created." in str(exc_delete.value)
        db.rollback()

        # Attempt UPDATE of immutable email
        with pytest.raises(Exception) as exc_update:
            db.execute(text(f"UPDATE users SET email = 'tampered@example.com' WHERE id = {user.id}"))
            db.commit()
        assert "ACCOUNT IMMUTABILITY: Immutable user identity fields" in str(exc_update.value)
        db.rollback()
    finally:
        db.close()
