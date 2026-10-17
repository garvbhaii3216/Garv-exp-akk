import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_auth_config_endpoint():
    response = client.get("/api/auth/config")
    assert response.status_code == 200
    data = response.json()
    assert "google_client_id" in data
    # Should be None/null if placeholder or missing, or a non-placeholder string
    if data["google_client_id"] is not None:
        assert "placeholder" not in data["google_client_id"].lower()
        assert "your-client-id" not in data["google_client_id"].lower()

def test_register_with_security_question_and_forgot_password_flow():
    # 1. Register user with security question and answer
    user_data = {
        "full_name": "Recovery User",
        "email": "recovery_test@example.com",
        "phone": "+919876543210",
        "password": "Password123!",
        "security_question": "What was the name of your first pet?",
        "security_answer": "Shadow"
    }
    reg_res = client.post("/api/auth/register", json=user_data)
    assert reg_res.status_code == 201
    assert "access_token" in reg_res.json()

    # 2. Fetch security question via Email
    q_res = client.post("/api/auth/forgot-password/question", json={"identifier": "recovery_test@example.com"})
    assert q_res.status_code == 200
    q_data = q_res.json()
    assert q_data["question"] == "What was the name of your first pet?"
    assert q_data["identifier"] == "recovery_test@example.com"

    # 3. Fetch security question via Phone number
    q_res_phone = client.post("/api/auth/forgot-password/question", json={"identifier": "+919876543210"})
    assert q_res_phone.status_code == 200
    assert q_res_phone.json()["question"] == "What was the name of your first pet?"

    # 4. Fetch security question for non-existent user
    q_res_not_found = client.post("/api/auth/forgot-password/question", json={"identifier": "unknown_user@example.com"})
    assert q_res_not_found.status_code == 404

    # 5. Reset password with wrong answer
    wrong_reset = client.post("/api/auth/forgot-password/reset", json={
        "identifier": "recovery_test@example.com",
        "security_answer": "WrongAnswer",
        "new_password": "NewSecretPass456!"
    })
    assert wrong_reset.status_code == 400
    assert "Incorrect security answer" in wrong_reset.json()["detail"]

    # 6. Reset password with weak new password (< 8 chars)
    weak_reset = client.post("/api/auth/forgot-password/reset", json={
        "identifier": "recovery_test@example.com",
        "security_answer": "Shadow",
        "new_password": "short"
    })
    assert weak_reset.status_code == 422

    # 7. Reset password with correct answer (case-insensitive and trimmed)
    correct_reset = client.post("/api/auth/forgot-password/reset", json={
        "identifier": "recovery_test@example.com",
        "security_answer": "   shadow   ",
        "new_password": "BrandNewPassword789!"
    })
    assert correct_reset.status_code == 200
    assert "reset successfully" in correct_reset.json()["message"].lower()

    # 8. Verify login with old password fails
    old_login = client.post("/api/auth/login", json={
        "username": "recovery_test@example.com",
        "password": "Password123!"
    })
    assert old_login.status_code == 401

    # 9. Verify login with new password succeeds
    new_login = client.post("/api/auth/login", json={
        "username": "recovery_test@example.com",
        "password": "BrandNewPassword789!"
    })
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()
