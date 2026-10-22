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
