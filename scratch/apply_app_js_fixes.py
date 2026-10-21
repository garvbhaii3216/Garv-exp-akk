# Script to update static/app.js for auth screen display toggling and auth theme icon

def update_app_js():
    with open('static/app.js', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update updateThemeIcon
    old_update_theme_icon = '''function updateThemeIcon() {
  const icon = document.getElementById("themeIcon");
  if (icon) {
    icon.setAttribute("data-lucide", state.isDarkMode ? "sun" : "moon");
  }
  const headerIcon = document.getElementById("themeIconHeader");
  if (headerIcon) {
    headerIcon.setAttribute("data-lucide", state.isDarkMode ? "sun" : "moon");
  }
  safeRenderIcons();
}'''

    new_update_theme_icon = '''function updateThemeIcon() {
  const icon = document.getElementById("themeIcon");
  if (icon) {
    icon.setAttribute("data-lucide", state.isDarkMode ? "sun" : "moon");
  }
  const headerIcon = document.getElementById("themeIconHeader");
  if (headerIcon) {
    headerIcon.setAttribute("data-lucide", state.isDarkMode ? "sun" : "moon");
  }
  const authIcon = document.getElementById("themeIconAuth");
  if (authIcon) {
    authIcon.setAttribute("data-lucide", state.isDarkMode ? "sun" : "moon");
    if (state.isDarkMode) {
      authIcon.classList.remove("text-indigo-600");
      authIcon.classList.add("text-amber-400");
    } else {
      authIcon.classList.remove("text-amber-400");
      authIcon.classList.add("text-indigo-600");
    }
  }
  const authLabel = document.getElementById("authThemeLabel");
  if (authLabel) {
    authLabel.textContent = state.isDarkMode ? "Dark Mode" : "Light Mode";
  }
  safeRenderIcons();
}'''

    if old_update_theme_icon in content:
        content = content.replace(old_update_theme_icon, new_update_theme_icon, 1)
        print("Updated updateThemeIcon in app.js")
    else:
        print("Could not find old_update_theme_icon, check formatting...")

    # 2. Update showAuth
    old_show_auth = '''function showAuth() {
  document.getElementById("authScreen")?.classList.remove("hidden");
  document.getElementById("appScreen")?.classList.add("hidden");

  // Pre-fill last signed in username if available
  const lastUser = localStorage.getItem("last_username");
  const loginInput = document.getElementById("loginUsername");
  if (lastUser && loginInput && !loginInput.value) {
    loginInput.value = lastUser;
  }
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
        print("Updated showAuth in app.js")
    else:
        print("Could not find old_show_auth, check formatting...")

    # 3. Update showApp
    old_show_app = '''function showApp() {
  document.getElementById("authScreen")?.classList.add("hidden");
  document.getElementById("appScreen")?.classList.remove("hidden");
  safeRenderIcons();

  updateUserProfileHeader();
  loadCategories();
  loadDashboardData();
  switchTab("dashboard");
  checkAppLockPromoBanner();
}'''

    new_show_app = '''function showApp() {
  const authScreen = document.getElementById("authScreen");
  if (authScreen) {
    authScreen.classList.add("hidden");
    authScreen.style.setProperty("display", "none", "important");
  }
  const appScreen = document.getElementById("appScreen");
  if (appScreen) {
    appScreen.classList.remove("hidden");
    appScreen.style.removeProperty("display");
  }
  safeRenderIcons();

  updateUserProfileHeader();
  loadCategories();
  loadDashboardData();
  switchTab("dashboard");
  checkAppLockPromoBanner();
}'''

    if old_show_app in content:
        content = content.replace(old_show_app, new_show_app, 1)
        print("Updated showApp in app.js")
    else:
        print("Could not find old_show_app, check formatting...")

    # 4. Update showAppLockScreen
    old_app_lock_screens = '''  lockScreen.classList.remove("hidden");
  document.getElementById("appScreen")?.classList.add("hidden");
  document.getElementById("authScreen")?.classList.add("hidden");'''

    new_app_lock_screens = '''  lockScreen.classList.remove("hidden");
  const appScreenElem = document.getElementById("appScreen");
  if (appScreenElem) {
    appScreenElem.classList.add("hidden");
    appScreenElem.style.setProperty("display", "none", "important");
  }
  const authScreenElem = document.getElementById("authScreen");
  if (authScreenElem) {
    authScreenElem.classList.add("hidden");
    authScreenElem.style.setProperty("display", "none", "important");
  }'''

    if old_app_lock_screens in content:
        content = content.replace(old_app_lock_screens, new_app_lock_screens, 1)
        print("Updated showAppLockScreen in app.js")

    with open('static/app.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Saved static/app.js")

update_app_js()
