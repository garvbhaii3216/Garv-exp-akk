import urllib.request
import re

html = urllib.request.urlopen("http://localhost:8000/").read().decode("utf-8")

# 1. Check theme toggle position
theme_match = re.search(r'<div class="fixed top-[^"]*">\s*<button[^>]*id="authThemeToggleBtn"', html)
print("Theme toggle wrapper found:", theme_match.group(0) if theme_match else "NOT FOUND")

# 2. Check toast container position
toast_match = re.search(r'<div id="toastContainer"[^>]*>', html)
print("Toast container found:", toast_match.group(0) if toast_match else "NOT FOUND")

# 3. Check script tags
fb_script = re.search(r'<script [^>]*src="/static/firebase-auth\.js\?v=4"[^>]*>', html)
print("Firebase script tag:", fb_script.group(0) if fb_script else "NOT FOUND")

app_script = re.search(r'<script [^>]*src="/static/app\.js\?v=4"[^>]*>', html)
print("App script tag:", app_script.group(0) if app_script else "NOT FOUND")
