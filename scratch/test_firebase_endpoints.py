import urllib.request
import json
import uuid

apiKey = "AIzaSyDcvwaxhYZrz7H4JbfBJzRTqgz0PeIfHxs"

def call_fb(endpoint, payload):
    url = f"https://identitytoolkit.googleapis.com/v1/{endpoint}?key={apiKey}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
test_pass = "TempPassword123!"

status, res = call_fb("accounts:signUp", {"email": test_email, "password": test_pass, "returnSecureToken": True})
print("SignUp status:", status, "keys:", list(res.keys()))
id_token = res.get("idToken")
local_id = res.get("localId")

# Send verification email
v_status, v_res = call_fb("accounts:sendOobCode", {"requestType": "VERIFY_EMAIL", "idToken": id_token})
print("Send verification status:", v_status, v_res)

# Lookup
l_status, l_res = call_fb("accounts:lookup", {"idToken": id_token})
print("Lookup status:", l_status, "user info:", l_res.get("users", [{}])[0].get("emailVerified"))

# Delete test account
d_status, d_res = call_fb("accounts:delete", {"idToken": id_token})
print("Deleted test account:", d_status)
