// ========================================================
// FIREBASE AUTHENTICATION (INSTANT REST CLIENT + BACKGROUND MODULAR SDK)
// ========================================================
(function() {
  const firebaseConfig = {
    apiKey: "AIzaSyDcvwaxhYZrz7H4JbfBJzRTqgz0PeIfHxs",
    authDomain: "expense-tracker-3216.firebaseapp.com",
    projectId: "expense-tracker-3216",
    storageBucket: "expense-tracker-3216.firebasestorage.app",
    messagingSenderId: "360128220552",
    appId: "1:360128220552:web:e804c67a8265326e55fe3d",
    measurementId: "G-C4LB77RCW3"
  };

  const API_KEY = firebaseConfig.apiKey;
  const BASE_URL = "https://identitytoolkit.googleapis.com/v1";

  let currentUser = null;
  const authStateListeners = [];

  function notifyAuthSubscribers(user) {
    currentUser = user;
    authStateListeners.forEach(fn => {
      try { fn(user); } catch (e) { console.error("Auth state listener error:", e); }
    });
  }

  function createUserObject(data, idToken, lookupData) {
    lookupData = lookupData || {};
    return {
      uid: data.localId || lookupData.localId || "",
      email: data.email || lookupData.email || "",
      displayName: data.displayName || lookupData.displayName || (data.email ? data.email.split("@")[0] : ""),
      photoURL: data.photoUrl || lookupData.photoUrl || null,
      emailVerified: Boolean(lookupData.emailVerified !== undefined ? lookupData.emailVerified : data.emailVerified),
      async getIdToken(forceRefresh) {
        return idToken;
      },
      async reload() {
        try {
          const res = await fetch(`${BASE_URL}/accounts:lookup?key=${API_KEY}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ idToken })
          });
          if (res.ok) {
            const lData = await res.json();
            const u = lData.users && lData.users[0];
            if (u) {
              this.emailVerified = Boolean(u.emailVerified);
              this.displayName = u.displayName || this.displayName;
            }
          }
        } catch (e) {
          console.warn("User reload notice:", e);
        }
      }
    };
  }

  const firebaseAuth = {
    app: null,
    auth: null,
    config: firebaseConfig,
    isReady: true,

    // Sign In using email and password
    async signIn(email, password) {
      try {
        const res = await fetch(`${BASE_URL}/accounts:signInWithPassword?key=${API_KEY}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: email.trim().toLowerCase(),
            password: password,
            returnSecureToken: true
          })
        });

        const data = await res.json();
        if (!res.ok) {
          return {
            user: null,
            error: {
              code: "auth/invalid-credential",
              message: "Email or password is incorrect"
            }
          };
        }

        // Fetch user verification status via lookup
        let lookupUser = {};
        try {
          const lRes = await fetch(`${BASE_URL}/accounts:lookup?key=${API_KEY}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ idToken: data.idToken })
          });
          if (lRes.ok) {
            const lData = await lRes.json();
            if (lData.users && lData.users[0]) {
              lookupUser = lData.users[0];
            }
          }
        } catch (lErr) {
          console.warn("Lookup notice during signIn:", lErr);
        }

        const user = createUserObject(data, data.idToken, lookupUser);
        notifyAuthSubscribers(user);
        return { user, error: null };
      } catch (netErr) {
        return {
          user: null,
          error: {
            code: "auth/network-request-failed",
            message: "Network error during sign in. Please check your connection."
          }
        };
      }
    },

    // Sign Up using email and password (without automatic sign-in)
    async signUp(email, password) {
      try {
        const cleanEmail = email.trim().toLowerCase();
        const res = await fetch(`${BASE_URL}/accounts:signUp?key=${API_KEY}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: cleanEmail,
            password: password,
            returnSecureToken: true
          })
        });

        const data = await res.json();
        if (!res.ok) {
          const errCode = data.error?.message || "";
          if (errCode.includes("EMAIL_EXISTS")) {
            return {
              user: null,
              error: {
                code: "auth/email-already-in-use",
                message: "User already exists. Please sign in"
              }
            };
          }
          if (errCode.includes("WEAK_PASSWORD")) {
            return {
              user: null,
              error: {
                code: "auth/weak-password",
                message: "Password should be at least 6 characters."
              }
            };
          }
          if (errCode.includes("INVALID_EMAIL")) {
            return {
              user: null,
              error: {
                code: "auth/invalid-email",
                message: "Please enter a valid email address."
              }
            };
          }
          return {
            user: null,
            error: {
              code: "auth/operation-not-allowed",
              message: data.error?.message || "Registration failed."
            }
          };
        }

        // Automatically dispatch verification email
        try {
          await fetch(`${BASE_URL}/accounts:sendOobCode?key=${API_KEY}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              requestType: "VERIFY_EMAIL",
              idToken: data.idToken
            })
          });
        } catch (verErr) {
          console.warn("Send verification email error:", verErr);
        }

        // User is registered but not signed in
        const user = createUserObject(data, data.idToken, { emailVerified: false });
        notifyAuthSubscribers(null);
        return { user, error: null };
      } catch (netErr) {
        return {
          user: null,
          error: {
            code: "auth/network-request-failed",
            message: "Network error during registration. Please check your connection."
          }
        };
      }
    },

    // Resend verification email
    async resendVerificationEmail(email, password) {
      try {
        const signRes = await this.signIn(email, password);
        if (signRes.error) {
          return { success: false, error: signRes.error };
        }
        const idToken = await signRes.user.getIdToken();
        const oobRes = await fetch(`${BASE_URL}/accounts:sendOobCode?key=${API_KEY}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            requestType: "VERIFY_EMAIL",
            idToken
          })
        });
        await this.signOut();
        if (oobRes.ok) {
          return { success: true, error: null };
        }
        const errData = await oobRes.json().catch(() => ({}));
        return { success: false, error: { message: errData.error?.message || "Failed to send email." } };
      } catch (err) {
        return { success: false, error: err };
      }
    },

    // Send Password Reset Email
    async sendPasswordResetEmail(email) {
      try {
        const res = await fetch(`${BASE_URL}/accounts:sendOobCode?key=${API_KEY}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            requestType: "PASSWORD_RESET",
            email: email.trim().toLowerCase()
          })
        });
        if (res.ok) {
          return { success: true, error: null };
        }
        const errData = await res.json().catch(() => ({}));
        return { success: false, error: { message: errData.error?.message || "Failed to send password reset email." } };
      } catch (err) {
        return { success: false, error: err };
      }
    },

    // Sign In / Sign Up with Google using Firebase Authentication
    async signInWithGoogle() {
      try {
        const { initializeApp } = await import("https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js");
        const { getAuth, GoogleAuthProvider, signInWithPopup } = await import("https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js");
        const app = firebaseAuth.app || initializeApp(firebaseConfig);
        const auth = firebaseAuth.auth || getAuth(app);
        firebaseAuth.app = app;
        firebaseAuth.auth = auth;

        const provider = new GoogleAuthProvider();
        provider.setCustomParameters({ prompt: "select_account" });
        const userCredential = await signInWithPopup(auth, provider);
        const user = userCredential.user;
        const idToken = await user.getIdToken();
        const formattedUser = createUserObject({
          localId: user.uid,
          email: user.email,
          displayName: user.displayName,
          photoUrl: user.photoURL,
          emailVerified: user.emailVerified
        }, idToken, { emailVerified: user.emailVerified });

        notifyAuthSubscribers(formattedUser);
        return { user: formattedUser, error: null };
      } catch (err) {
        console.warn("Google sign-in popup notice:", err);
        return {
          user: null,
          error: {
            code: err.code || "auth/popup-failed",
            message: err.message || "Google sign in was cancelled or closed."
          }
        };
      }
    },

    // Sign out
    async signOut() {
      notifyAuthSubscribers(null);
      return { success: true };
    },

    // Get current user
    getCurrentUser() {
      return currentUser;
    },

    // Auth state observer
    onAuthStateChanged(callback) {
      if (typeof callback === "function") {
        authStateListeners.push(callback);
        try { callback(currentUser); } catch (e) {}
      }
      return () => {
        const idx = authStateListeners.indexOf(callback);
        if (idx !== -1) authStateListeners.splice(idx, 1);
      };
    }
  };

  // Synchronously attach to window right now
  window.firebaseAuth = firebaseAuth;
  try {
    window.dispatchEvent(new CustomEvent("firebase-auth-ready", { detail: { auth: firebaseAuth } }));
  } catch (evErr) {}

  // Hydrate Modular SDK in background for optional advanced APIs
  (async () => {
    try {
      const { initializeApp } = await import("https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js");
      const { getAuth } = await import("https://www.gstatic.com/firebasejs/10.14.1/firebase-auth.js");
      const app = initializeApp(firebaseConfig);
      const auth = getAuth(app);
      firebaseAuth.app = app;
      firebaseAuth.auth = auth;
    } catch (sdkErr) {
      // Offline or blocked CDN fallback
      console.log("Firebase modular SDK background load notice:", sdkErr);
    }
  })();
})();
