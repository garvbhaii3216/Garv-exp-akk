# Update static/app.js with Firebase Authentication and Email Verification flows

def update_app_js():
    with open('static/app.js', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update loginForm and registerForm handlers
    old_handlers = '''  // Login submission
  loginForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("loginUsername").value.trim();
    const password = document.getElementById("loginPassword").value;
    const saveCheck = document.getElementById("saveProfileCheck");
    const remember_me = saveCheck ? saveCheck.checked : true;

    try {
      const res = await fetch(getApiUrl("/api/auth/login"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, remember_me })
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error((data && data.detail) || `Login failed (${res.status})`);

      applyAuthSession(data, remember_me);
      localStorage.setItem("last_username", username);

      showToast(`Welcome back, ${data.user.full_name}!`, "success");
      showApp();
    } catch (err) {
      showToast(formatNetworkError(err), "error");
    }
  });

  // Register submission -> Direct Registration (No OTP needed)
  registerForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const full_name = document.getElementById("regFullName").value.trim();
    const email = document.getElementById("regEmail").value.trim().toLowerCase();
    const phone = document.getElementById("regPhone").value.trim();
    const password = document.getElementById("regPassword").value;
    const security_question = document.getElementById("regSecurityQuestion")?.value.trim();
    const security_answer = document.getElementById("regSecurityAnswer")?.value.trim();
    const currencyVal = document.getElementById("regCurrency").value.split(":");
    const currency_symbol = currencyVal[0];
    const currency_code = currencyVal[1];

    // Client-side password complexity verification
    if (password.length < 8) {
      showToast("Password must be at least 8 characters long.", "error");
      return;
    }
    if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/[0-9]/.test(password)) {
      showToast("Password must include at least one uppercase letter, one lowercase letter, and one number.", "error");
      return;
    }

    if (!security_question) {
      showToast("Please select a security question for password recovery.", "error");
      return;
    }
    if (!security_answer || security_answer.length < 2) {
      showToast("Please enter your answer to the security question.", "error");
      return;
    }

    const regBtn = document.getElementById("regSubmitBtn");
    const originalText = regBtn ? regBtn.innerHTML : "Create My Account";

    try {
      if (regBtn) {
        regBtn.disabled = true;
        regBtn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Creating Account...</span>`;
        if (window.lucide) safeRenderIcons();
      }

      // Direct registration without OTP requirement
      const regRes = await fetch(getApiUrl("/api/auth/register"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name,
          email,
          phone: phone || null,
          password,
          currency_symbol,
          currency_code,
          security_question,
          security_answer
        })
      });

      const data = await regRes.json().catch(() => null);
      if (!regRes.ok) {
        throw new Error((data && data.detail) || `Registration failed (${regRes.status})`);
      }

      applyAuthSession(data, true);
      localStorage.setItem("last_username", email);
      showToast(`Welcome ${data.user.full_name}! Your account has been created successfully.`, "success");
      showApp();

    } catch (err) {
      showToast(formatNetworkError(err), "error");
    } finally {
      if (regBtn) {
        regBtn.disabled = false;
        regBtn.innerHTML = originalText;
        if (window.lucide) safeRenderIcons();
      }
    }
  });'''

    new_handlers = '''  // ==========================================
  // FIREBASE AUTHENTICATION (EMAIL & PASSWORD)
  // ==========================================

  // Login submission via Firebase Authentication
  loginForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("loginUsername").value.trim().toLowerCase();
    const password = document.getElementById("loginPassword").value;
    const saveCheck = document.getElementById("saveProfileCheck");
    const remember_me = saveCheck ? saveCheck.checked : true;

    if (!email) {
      showToast("Email or password is incorrect", "error");
      return;
    }
    if (!password) {
      showToast("Email or password is incorrect", "error");
      return;
    }

    const loginBtn = document.getElementById("loginSubmitBtn");
    const origHtml = loginBtn ? loginBtn.innerHTML : "Sign In";

    try {
      if (loginBtn) {
        loginBtn.disabled = true;
        loginBtn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin text-white"></i><span>Signing In...</span>`;
        if (window.lucide) safeRenderIcons();
      }

      if (!window.firebaseAuth) {
        throw new Error("Firebase Authentication is initializing. Please try again in a moment.");
      }

      const { user, error } = await window.firebaseAuth.signIn(email, password);

      if (error) {
        // Requirement: If credentials are incorrect, show "Email or password is incorrect"
        showToast("Email or password is incorrect", "error");
        return;
      }

      // Requirement: If a user logs in and their email is not verified, block access and show the same verification screen.
      if (!user.emailVerified) {
        await window.firebaseAuth.signOut();
        showEmailVerificationScreen(user.email);
        return;
      }

      // Verified user! On successful sign-in, redirect to the dashboard
      const idToken = await user.getIdToken();
      let sessionData = {
        access_token: idToken,
        user: {
          id: user.uid,
          email: user.email,
          full_name: user.displayName || user.email.split("@")[0].replace(".", " ").replace(/\\b\\w/g, l => l.toUpperCase()),
          currency_symbol: "₹",
          currency_code: "INR"
        }
      };

      // Sync with backend session endpoint so dashboard data endpoints function smoothly
      try {
        const sessRes = await fetch(getApiUrl("/api/auth/firebase-session"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id_token: idToken, email: user.email, uid: user.uid, remember_me })
        });
        if (sessRes.ok) {
          const sessData = await sessRes.json();
          if (sessData && sessData.access_token) {
            sessionData = sessData;
          }
        }
      } catch (sessErr) {
        console.warn("Backend session sync notice:", sessErr);
      }

      applyAuthSession(sessionData, remember_me);
      localStorage.setItem("last_username", email);
      showToast(`Welcome back, ${sessionData.user.full_name}!`, "success");
      showApp();

    } catch (err) {
      showToast("Email or password is incorrect", "error");
    } finally {
      if (loginBtn) {
        loginBtn.disabled = false;
        loginBtn.innerHTML = origHtml;
        if (window.lucide) safeRenderIcons();
      }
    }
  });

  // Register submission via Firebase Authentication
  registerForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("regEmail").value.trim().toLowerCase();
    const password = document.getElementById("regPassword").value;

    if (!email || !email.includes("@")) {
      showToast("Please enter a valid email address.", "error");
      return;
    }
    if (!password || password.length < 6) {
      showToast("Password should be at least 6 characters.", "error");
      return;
    }

    const regBtn = document.getElementById("regSubmitBtn");
    const origHtml = regBtn ? regBtn.innerHTML : "Create My Account";

    try {
      if (regBtn) {
        regBtn.disabled = true;
        regBtn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin text-white"></i><span>Sending Verification Email...</span>`;
        if (window.lucide) safeRenderIcons();
      }

      if (!window.firebaseAuth) {
        throw new Error("Firebase Authentication is initializing. Please try again in a moment.");
      }

      const { user, error } = await window.firebaseAuth.signUp(email, password);

      if (error) {
        // Requirement: If the email already exists, show "User already exists. Please sign in"
        if (error.code === "auth/email-already-in-use") {
          showToast("User already exists. Please sign in", "error");
          return;
        }
        if (error.code === "auth/weak-password") {
          showToast("Password should be at least 6 characters.", "error");
          return;
        }
        if (error.code === "auth/invalid-email") {
          showToast("Please enter a valid email address.", "error");
          return;
        }
        showToast(error.message || "Registration failed. Please try again.", "error");
        return;
      }

      // Requirement:
      // When a user registers with email/password, do not sign them in automatically.
      // Send a verification email and show a verification screen with this message:
      // “We have sent you a verification email to [user email]. Please verify it and log in.”
      // Include a Login button on the verification screen.
      showEmailVerificationScreen(email);

    } catch (err) {
      showToast(err.message || "Registration failed.", "error");
    } finally {
      if (regBtn) {
        regBtn.disabled = false;
        regBtn.innerHTML = origHtml;
        if (window.lucide) safeRenderIcons();
      }
    }
  });'''

    if old_handlers in content:
        content = content.replace(old_handlers, new_handlers, 1)
        print("Updated loginForm and registerForm handlers")
    else:
        print("Could not find exact old_handlers in app.js")

    # 2. Add showEmailVerificationScreen and switchToLoginTabFromVerification functions
    ver_helpers = '''// ==========================================
// EMAIL VERIFICATION SCREEN HELPERS (FIREBASE AUTH)
// ==========================================
window.lastVerificationEmail = "";

function showEmailVerificationScreen(email) {
  window.lastVerificationEmail = email;
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");
  const tabsWrapper = document.getElementById("authTabsWrapper");
  const demoBox = document.getElementById("authDemoBox");
  const verScreen = document.getElementById("emailVerificationScreen");
  const emailTargetSpan = document.getElementById("verificationEmailTarget");
  const emailMessageP = document.getElementById("verificationEmailMessage");

  if (loginForm) loginForm.classList.add("hidden");
  if (registerForm) registerForm.classList.add("hidden");
  if (tabsWrapper) tabsWrapper.classList.add("hidden");
  if (demoBox) demoBox.classList.add("hidden");

  if (emailTargetSpan) {
    emailTargetSpan.textContent = email;
  }
  if (emailMessageP) {
    emailMessageP.innerHTML = `We have sent you a verification email to <strong class="font-bold text-indigo-600 dark:text-indigo-400">${email}</strong>. Please verify it and log in.`;
  }
  if (verScreen) {
    verScreen.classList.remove("hidden");
  }
  safeRenderIcons();
}
window.showEmailVerificationScreen = showEmailVerificationScreen;

function switchToLoginTabFromVerification() {
  const verScreen = document.getElementById("emailVerificationScreen");
  const tabsWrapper = document.getElementById("authTabsWrapper");
  const demoBox = document.getElementById("authDemoBox");
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");
  const tabLoginBtn = document.getElementById("tabLoginBtn");
  const tabRegisterBtn = document.getElementById("tabRegisterBtn");
  const loginUsername = document.getElementById("loginUsername");
  const loginPassword = document.getElementById("loginPassword");

  if (verScreen) verScreen.classList.add("hidden");
  if (tabsWrapper) tabsWrapper.classList.remove("hidden");
  if (demoBox) demoBox.classList.remove("hidden");
  if (loginForm) loginForm.classList.remove("hidden");
  if (registerForm) registerForm.classList.add("hidden");

  if (tabLoginBtn) {
    tabLoginBtn.className = "w-1/2 py-2 text-xs sm:text-sm font-bold rounded-xl transition-all bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm";
  }
  if (tabRegisterBtn) {
    tabRegisterBtn.className = "w-1/2 py-2 text-xs sm:text-sm font-semibold rounded-xl transition-all text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white";
  }

  if (window.lastVerificationEmail && loginUsername) {
    loginUsername.value = window.lastVerificationEmail;
  }
  if (loginPassword) {
    loginPassword.value = "";
    loginPassword.focus();
  }
  safeRenderIcons();
}
window.switchToLoginTabFromVerification = switchToLoginTabFromVerification;

async function resendVerificationEmailAction() {
  const email = window.lastVerificationEmail || document.getElementById("regEmail")?.value || document.getElementById("loginUsername")?.value;
  if (!email) {
    showToast("Please enter your email to resend verification.", "error");
    return;
  }
  const password = document.getElementById("loginPassword")?.value || document.getElementById("regPassword")?.value;
  if (!password) {
    showToast("Please enter your password in the sign-in form to resend verification.", "info");
    switchToLoginTabFromVerification();
    return;
  }
  if (!window.firebaseAuth) {
    showToast("Firebase is initializing. Please try again.", "info");
    return;
  }
  const res = await window.firebaseAuth.resendVerificationEmail(email, password);
  if (res.success) {
    showToast(`Verification email resent to ${email}!`, "success");
  } else {
    showToast(res.error?.message || "Unable to resend email. Check your password.", "error");
  }
}
window.resendVerificationEmailAction = resendVerificationEmailAction;

'''

    if 'function showEmailVerificationScreen' not in content:
        # Prepend to showAuth
        content = content.replace('function showAuth() {', ver_helpers + 'function showAuth() {', 1)
        print("Added email verification helpers before showAuth")

    # 3. Update showAuth to reset email verification screen if returning to auth
    old_show_auth = '''function showAuth() {
  const authScreen = document.getElementById("authScreen");
  if (authScreen) {
    authScreen.classList.remove("hidden");
    authScreen.style.removeProperty("display");
  }
  const appScreen = document.getElementById("appScreen");
  if (appScreen) {
    appScreen.classList.add("hidden");
    appScreen.style.setProperty("display", "none", "important");
  }

  // Pre-fill last signed in username if available
  const lastUser = localStorage.getItem("last_username");
  const loginInput = document.getElementById("loginUsername");
  if (lastUser && loginInput && !loginInput.value) {
    loginInput.value = lastUser;
  }
  updateThemeIcon();
  safeRenderIcons();
}'''

    new_show_auth = '''function showAuth() {
  const authScreen = document.getElementById("authScreen");
  if (authScreen) {
    authScreen.classList.remove("hidden");
    authScreen.style.removeProperty("display");
  }
  const appScreen = document.getElementById("appScreen");
  if (appScreen) {
    appScreen.classList.add("hidden");
    appScreen.style.setProperty("display", "none", "important");
  }

  // Reset verification screen if returning to auth
  const verScreen = document.getElementById("emailVerificationScreen");
  const tabsWrapper = document.getElementById("authTabsWrapper");
  const demoBox = document.getElementById("authDemoBox");
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");
  if (verScreen) verScreen.classList.add("hidden");
  if (tabsWrapper) tabsWrapper.classList.remove("hidden");
  if (demoBox) demoBox.classList.remove("hidden");
  if (loginForm) loginForm.classList.remove("hidden");
  if (registerForm) registerForm.classList.add("hidden");

  // Pre-fill last signed in username if available
  const lastUser = localStorage.getItem("last_username");
  const loginInput = document.getElementById("loginUsername");
  if (lastUser && loginInput && !loginInput.value) {
    loginInput.value = lastUser;
  }
  updateThemeIcon();
  safeRenderIcons();
}'''

    if old_show_auth in content:
        content = content.replace(old_show_auth, new_show_auth, 1)
        print("Updated showAuth")

    # 4. Update logout to signOut from Firebase
    old_logout = '''async function logout() {
  try {
    if (state.token) {
      await fetch(getApiUrl("/api/auth/logout"), {
        method: "POST",
        headers: { "Authorization": `Bearer ${state.token}` }
      });
    }
  } catch (e) {}'''

    new_logout = '''async function logout() {
  try {
    if (window.firebaseAuth) {
      await window.firebaseAuth.signOut();
    }
  } catch (e) {}
  try {
    if (state.token) {
      await fetch(getApiUrl("/api/auth/logout"), {
        method: "POST",
        headers: { "Authorization": `Bearer ${state.token}` }
      });
    }
  } catch (e) {}'''

    if old_logout in content:
        content = content.replace(old_logout, new_logout, 1)
        print("Updated logout with firebase signOut")

    with open('static/app.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Saved static/app.js successfully!")

update_app_js()
