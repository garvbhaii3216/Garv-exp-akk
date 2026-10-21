# Script to update static/index.html with Firebase script tag, authDemoBox, authTabsWrapper, and emailVerificationScreen

def update_index_html():
    with open('static/index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add Firebase script module in head
    if 'src="/static/firebase-auth.js"' not in content:
        content = content.replace(
            '<script src="/static/app.js?v=3"></script>',
            '<!-- Firebase Authentication (Modular SDK v10) -->\n  <script type="module" src="/static/firebase-auth.js"></script>\n  <!-- Application Logic -->\n  <script src="/static/app.js?v=3"></script>'
        )
        print("Added firebase-auth.js script tag")

    # 2. Add id="authDemoBox" to demo box
    content = content.replace(
        '<div class="p-3 rounded-2xl bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-emerald-500/10 border border-indigo-200/70 dark:border-indigo-800/60 shadow-xs mb-3">',
        '<div id="authDemoBox" class="p-3 rounded-2xl bg-gradient-to-r from-indigo-500/10 via-purple-500/10 to-emerald-500/10 border border-indigo-200/70 dark:border-indigo-800/60 shadow-xs mb-3">'
    )

    # 3. Add id="authTabsWrapper" to tabs container
    content = content.replace(
        '<div class="flex p-1 bg-slate-100 dark:bg-slate-800/90 rounded-2xl border border-slate-200/60 dark:border-slate-700/60 mb-3">',
        '<div id="authTabsWrapper" class="flex p-1 bg-slate-100 dark:bg-slate-800/90 rounded-2xl border border-slate-200/60 dark:border-slate-700/60 mb-3">'
    )

    # 4. Remove 'required' from regFullName, regSecurityQuestion, regSecurityAnswer
    content = content.replace('<input id="regFullName" type="text" required', '<input id="regFullName" type="text"')
    content = content.replace('<select id="regSecurityQuestion" required', '<select id="regSecurityQuestion"')
    content = content.replace('<input id="regSecurityAnswer" type="text" required', '<input id="regSecurityAnswer" type="text"')
    content = content.replace('minlength="8"', 'minlength="6"')

    # 5. Insert #emailVerificationScreen after </form> of registerForm
    ver_screen_html = '''        <!-- Email Verification Screen -->
        <div id="emailVerificationScreen" class="hidden text-center py-6 px-2 space-y-4">
          <div class="inline-flex items-center justify-center w-16 h-16 rounded-3xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 ring-8 ring-indigo-50/50 dark:ring-indigo-950/30">
            <i data-lucide="mail-check" class="w-8 h-8 text-indigo-600 dark:text-indigo-400"></i>
          </div>

          <div class="space-y-2">
            <h3 class="text-base sm:text-lg font-black text-slate-900 dark:text-white">Verify Your Email</h3>
            <p id="verificationEmailMessage" class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed font-medium">
              We have sent you a verification email to <span id="verificationEmailTarget" class="font-bold text-indigo-600 dark:text-indigo-400">user@example.com</span>. Please verify it and log in.
            </p>
          </div>

          <div class="pt-2 space-y-2">
            <button type="button" id="verificationLoginBtn" onclick="switchToLoginTabFromVerification()"
              class="w-full py-2.5 sm:py-3 px-4 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-bold rounded-xl shadow-lg shadow-indigo-600/30 transition-all flex items-center justify-center gap-2 active-press text-xs sm:text-sm">
              <i data-lucide="log-in" class="w-4 h-4"></i>
              <span>Login</span>
            </button>

            <button type="button" id="resendVerificationBtn" onclick="resendVerificationEmailAction()"
              class="w-full py-2 px-3 text-xs font-semibold text-slate-500 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition flex items-center justify-center gap-1.5">
              <i data-lucide="refresh-cw" class="w-3.5 h-3.5"></i>
              <span>Resend verification email</span>
            </button>
          </div>
        </div>
'''

    if 'id="emailVerificationScreen"' not in content:
        # Find closing tag of registerForm
        target = '</form>\n\n        <!-- Database Isolation Note -->'
        if target in content:
            content = content.replace(target, '</form>\n\n' + ver_screen_html + '\n        <!-- Database Isolation Note -->')
            print("Inserted emailVerificationScreen")
        else:
            print("Could not find exact target for emailVerificationScreen, checking alternative...")
            content = content.replace('</form>\n        <!-- Database Isolation Note -->', '</form>\n\n' + ver_screen_html + '\n        <!-- Database Isolation Note -->')
            print("Inserted emailVerificationScreen with alternative target")

    with open('static/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Saved static/index.html successfully!")

update_index_html()
