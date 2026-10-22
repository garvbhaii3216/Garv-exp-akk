import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_profile_update_mobile_without_otp():
    # Register user via firebase-session without phone
    sess_res = client.post(
        "/api/auth/firebase-session",
        json={"id_token": "test_token", "email": "mobile_test_user@example.com"}
    )
    assert sess_res.status_code == 200
    token = sess_res.json()["access_token"]
    user = sess_res.json()["user"]
    assert user["phone"] is None
    headers = {"Authorization": f"Bearer {token}"}

    # Flash pop / direct profile update: Add mobile number without any OTP
    new_phone = "+919105759184"
    update_res = client.put(
        "/api/auth/profile",
        headers=headers,
        json={"phone": new_phone}
    )
    assert update_res.status_code == 200
    assert update_res.json()["phone"] == new_phone

    # Verify get profile returns new phone
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["phone"] == new_phone

def test_signout_endpoint():
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200
    assert "Clear-Site-Data" in logout_res.headers

def test_high_value_refill_and_expense_without_otp():
    sess_res = client.post(
        "/api/auth/firebase-session",
        json={"id_token": "test_token", "email": "high_value_user@example.com"}
    )
    assert sess_res.status_code == 200
    token = sess_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Add high-value refill (e.g. 50,000) directly without OTP
    refill_res = client.post(
        "/api/refills",
        headers=headers,
        json={
            "amount": 50000.0,
            "funding_source": "Salary / Income",
            "reason": "High-value monthly deposit",
            "payment_mode": "Net Banking"
        }
    )
    assert refill_res.status_code == 201
    assert refill_res.json()["amount"] == 50000.0

    # Add high-value expense (e.g. 25,000) directly without OTP
    expense_res = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "amount": 25000.0,
            "description": "Laptop purchase",
            "category": "Personal & Clothing",
            "date": "2026-10-15",
            "payment_mode": "Credit Card"
        }
    )
    assert expense_res.status_code == 201
    assert expense_res.json()["amount"] == 25000.0


def test_saved_mobile_numbers_for_specific_accounts():
    from backend.database import SessionLocal
    from backend.models import User
    db = SessionLocal()
    try:
        user1 = db.query(User).filter(User.email == "singhalgarv09@gmail.com").first()
        assert user1 is not None, "singhalgarv09@gmail.com should exist in db"
        assert user1.phone == "9105759184", f"Expected 9105759184, got {user1.phone}"

        user2 = db.query(User).filter(User.email == "akshitagarwal1122@gmail.com").first()
        assert user2 is not None, "akshitagarwal1122@gmail.com should exist in db"
        assert user2.phone == "7505905455", f"Expected 7505905455, got {user2.phone}"
    finally:
        db.close()


def test_large_number_expense_and_validation_error_format():
    sess_res = client.post(
        "/api/auth/firebase-session",
        json={"id_token": "test_token", "email": "large_number_user@example.com"}
    )
    assert sess_res.status_code == 200
    token = sess_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Large number within 10,000,000,000 should succeed
    res_large = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "amount": 500000000.0,
            "description": "Property Investment",
            "category": "Bills & Utilities",
            "date": "2026-10-15",
            "payment_mode": "Net Banking"
        }
    )
    assert res_large.status_code == 201
    assert res_large.json()["amount"] == 500000000.0

    # 2. Amount exceeding 10,000,000,000 should return clean 422 with string detail (no [object Object])
    res_overflow = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "amount": 99999999999.0,
            "description": "Invalid huge amount",
            "category": "Bills & Utilities",
            "date": "2026-10-15",
            "payment_mode": "Net Banking"
        }
    )
    assert res_overflow.status_code == 422
    err_body = res_overflow.json()
    assert isinstance(err_body["detail"], str), "detail must be a string so frontend never displays [object Object]"
    assert "amount" in err_body["detail"]
    assert "[object Object]" not in err_body["detail"]


