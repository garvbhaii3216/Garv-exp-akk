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

