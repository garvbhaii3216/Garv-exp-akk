# Script to update static/index.html, static/styles.css, and static/app.js for Theme toggle, high contrast colors in light/dark mode, and instant trial login transition

def update_index():
    with open('static/index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update #authScreen container and add theme switcher
    old_auth_start = '<div id="authScreen" class="hidden min-h-[100dvh] w-full max-w-full overflow-x-hidden relative flex items-center justify-center p-3 sm:p-6 lg:p-10 bg-gradient-to-br from-slate-950 via-indigo-950 to-slate-900 box-border">\n    <!-- Ambient glowing backdrop orbs -->\n    <div class="absolute -top-32 -left-32 w-80 h-80 bg-indigo-500/20 rounded-full blur-3xl pointer-events-none"></div>\n    <div class="absolute -bottom-32 -right-32 w-80 h-80 bg-emerald-500/15 rounded-full blur-3xl pointer-events-none"></div>'

    new_auth_start = '''<div id="authScreen" class="hidden min-h-[100dvh] w-full max-w-full overflow-x-hidden relative flex items-center justify-center p-3 sm:p-6 lg:p-10 box-border">
    <!-- Floating Theme Switcher on Auth Screen -->
    <div class="fixed top-4 right-4 z-50 flex items-center gap-2">
      <button type="button" onclick="toggleDarkMode()" id="authThemeToggleBtn" title="Switch Theme (Dark / Light)"
        class="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/90 dark:bg-slate-800/90 backdrop-blur-md border border-slate-200/90 dark:border-slate-700/80 shadow-md hover:shadow-lg text-slate-800 dark:text-slate-100 hover:text-indigo-600 dark:hover:text-indigo-400 text-xs font-bold transition-all active-press cursor-pointer">
        <i data-lucide="moon" id="themeIconAuth" class="w-4 h-4 text-indigo-600 dark:text-amber-400"></i>
        <span id="authThemeLabel" class="text-xs font-semibold">Theme</span>
      </button>
    </div>

    <!-- Ambient glowing backdrop orbs -->
    <div class="auth-orb-1 absolute -top-32 -left-32 w-80 h-80 rounded-full blur-3xl pointer-events-none transition-opacity duration-300"></div>
    <div class="auth-orb-2 absolute -bottom-32 -right-32 w-80 h-80 rounded-full blur-3xl pointer-events-none transition-opacity duration-300"></div>'''

    if old_auth_start in content:
        content = content.replace(old_auth_start, new_auth_start, 1)
        print("Updated authScreen container with theme switcher in index.html")
    else:
        print("Could not find exact old_auth_start in index.html, searching partially...")
        # fallback search
        import re
        content = re.sub(
            r'<div id="authScreen"[^>]*>[\s\S]*?<!-- Ambient glowing backdrop orbs -->[\s\S]*?<div class="relative z-10',
            new_auth_start + '\n\n    <div class="relative z-10',
            content,
            count=1
        )
        print("Replaced authScreen header via regex")

    # 2. Update desktop showcase with high-contrast theme-adaptive classes
    old_showcase = '''      <div class="auth-desktop-showcase pr-2 select-none">
        
        <!-- Enterprise Badge -->
        <div class="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-bold bg-white/10 backdrop-blur-md border border-white/20 text-indigo-200 shadow-sm w-fit">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>Version 3.2 • Enterprise Allowance &amp; Expense Tracker</span>
        </div>

        <!-- Big Bold Title -->
        <div class="space-y-3">
          <h1 class="text-3xl xl:text-4xl font-black text-white tracking-tight leading-tight">
            Take Complete Control of Your Monthly Finances.
          </h1>
          <p class="text-slate-300 text-sm xl:text-base leading-relaxed">
            Engineered for students and families to effortlessly track starting allowances, mid-month refills, day-to-day spending, and transparent WhatsApp PDF settlement reports.
          </p>
        </div>

        <!-- Live Financial Snapshot Mock Card -->
        <div class="bg-white/10 dark:bg-slate-900/60 backdrop-blur-xl p-5 rounded-2xl border border-white/20 shadow-xl space-y-3">
          <div class="flex items-center justify-between border-b border-white/10 pb-2.5">
            <span class="text-xs font-semibold text-slate-300">Monthly Budget Snapshot (Demo)</span>
            <span class="text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">Active Cycle</span>
          </div>
          <div class="grid grid-cols-3 gap-3">
            <div class="p-2.5 rounded-xl bg-white/5 border border-white/10">
              <span class="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Allowance</span>
              <div class="text-base font-extrabold text-white mt-0.5">₹10,000</div>
            </div>
            <div class="p-2.5 rounded-xl bg-white/5 border border-white/10">
              <span class="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Total Spent</span>
              <div class="text-base font-extrabold text-rose-300 mt-0.5">₹3,240</div>
            </div>
            <div class="p-2.5 rounded-xl bg-white/5 border border-white/10">
              <span class="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Balance</span>
              <div class="text-base font-extrabold text-emerald-300 mt-0.5">₹6,760</div>
            </div>
          </div>
          <div class="flex items-center justify-between text-xs text-indigo-200 pt-1">
            <span class="flex items-center gap-1.5"><i data-lucide="zap" class="w-3.5 h-3.5 text-amber-300"></i> Daily Safe Spend: <strong class="text-white">₹322 / day</strong></span>
            <span class="text-[11px] text-slate-300">21 days remaining</span>
          </div>
        </div>

        <!-- 4 Core Highlights -->
        <div class="grid grid-cols-2 gap-3 pt-1">
          <div class="flex items-start gap-2.5 p-3 rounded-xl bg-white/5 border border-white/10">
            <i data-lucide="sparkles" class="w-5 h-5 text-amber-300 shrink-0 mt-0.5"></i>
            <div>
              <div class="text-xs font-bold text-white">Ask AI Assistant</div>
              <div class="text-[11px] text-slate-300">Deep spending &amp; transaction analysis</div>
            </div>
          </div>
          <div class="flex items-start gap-2.5 p-3 rounded-xl bg-white/5 border border-white/10">
            <i data-lucide="file-spreadsheet" class="w-5 h-5 text-emerald-300 shrink-0 mt-0.5"></i>
            <div>
              <div class="text-xs font-bold text-white">WhatsApp Parent Report</div>
              <div class="text-[11px] text-slate-300">Itemized PDF statement generation</div>
            </div>
          </div>
          <div class="flex items-start gap-2.5 p-3 rounded-xl bg-white/5 border border-white/10">
            <i data-lucide="calendar" class="w-5 h-5 text-indigo-300 shrink-0 mt-0.5"></i>
            <div>
              <div class="text-xs font-bold text-white">Fixed Recurring Bills</div>
              <div class="text-[11px] text-slate-300">Rent, WiFi, Mobile due tracker</div>
            </div>
          </div>
          <div class="flex items-start gap-2.5 p-3 rounded-xl bg-white/5 border border-white/10">
            <i data-lucide="shield-check" class="w-5 h-5 text-purple-300 shrink-0 mt-0.5"></i>
            <div>
              <div class="text-xs font-bold text-white">Isolated Per-User DB</div>
              <div class="text-[11px] text-slate-300">Strict privacy &amp; local encryption</div>
            </div>
          </div>
        </div>

      </div>'''

    new_showcase = '''      <div class="auth-desktop-showcase pr-2 select-none">
        
        <!-- Enterprise Badge -->
        <div class="auth-showcase-badge inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-bold transition shadow-xs w-fit">
          <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          <span>Version 3.2 • Enterprise Allowance &amp; Expense Tracker</span>
        </div>

        <!-- Big Bold Title -->
        <div class="space-y-3">
          <h1 class="auth-showcase-title text-3xl xl:text-4xl font-black tracking-tight leading-tight">
            Take Complete Control of Your <span class="bg-gradient-to-r from-indigo-600 via-indigo-500 to-purple-600 dark:from-indigo-400 dark:via-purple-300 dark:to-indigo-300 bg-clip-text text-transparent">Monthly Finances.</span>
          </h1>
          <p class="auth-showcase-subtitle text-sm xl:text-base leading-relaxed">
            Engineered for students and families to effortlessly track starting allowances, mid-month refills, day-to-day spending, and transparent WhatsApp PDF settlement reports.
          </p>
        </div>

        <!-- Live Financial Snapshot Mock Card -->
        <div class="auth-showcase-card p-5 rounded-2xl transition space-y-3">
          <div class="flex items-center justify-between border-b auth-card-divider pb-2.5">
            <span class="text-xs font-bold auth-card-head">Monthly Budget Snapshot (Demo)</span>
            <span class="text-[11px] font-bold px-2 py-0.5 rounded-full auth-card-badge">Active Cycle</span>
          </div>
          <div class="grid grid-cols-3 gap-3">
            <div class="p-2.5 rounded-xl auth-stat-box">
              <span class="text-[10px] auth-stat-label uppercase font-bold tracking-wider">Allowance</span>
              <div class="text-base font-extrabold auth-stat-val-allowance mt-0.5">₹10,000</div>
            </div>
            <div class="p-2.5 rounded-xl auth-stat-box">
              <span class="text-[10px] auth-stat-label uppercase font-bold tracking-wider">Total Spent</span>
              <div class="text-base font-extrabold auth-stat-val-spent mt-0.5">₹3,240</div>
            </div>
            <div class="p-2.5 rounded-xl auth-stat-box">
              <span class="text-[10px] auth-stat-label uppercase font-bold tracking-wider">Balance</span>
              <div class="text-base font-extrabold auth-stat-val-balance mt-0.5">₹6,760</div>
            </div>
          </div>
          <div class="flex items-center justify-between text-xs pt-1">
            <span class="flex items-center gap-1.5 auth-spend-rate">
              <i data-lucide="zap" class="w-3.5 h-3.5 text-amber-500"></i>
              Daily Safe Spend: <strong class="auth-spend-rate-val">₹322 / day</strong>
            </span>
            <span class="text-[11px] auth-days-left">21 days remaining</span>
          </div>
        </div>

        <!-- 4 Core Highlights -->
        <div class="grid grid-cols-2 gap-3 pt-1">
          <div class="auth-feature-card flex items-start gap-2.5 p-3 rounded-xl transition">
            <i data-lucide="sparkles" class="w-5 h-5 text-amber-500 shrink-0 mt-0.5"></i>
            <div>
              <div class="auth-feature-title text-xs font-bold">Ask AI Assistant</div>
              <div class="auth-feature-desc text-[11px]">Deep spending &amp; transaction analysis</div>
            </div>
          </div>
          <div class="auth-feature-card flex items-start gap-2.5 p-3 rounded-xl transition">
            <i data-lucide="file-spreadsheet" class="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5"></i>
            <div>
              <div class="auth-feature-title text-xs font-bold">WhatsApp Parent Report</div>
              <div class="auth-feature-desc text-[11px]">Itemized PDF statement generation</div>
            </div>
          </div>
          <div class="auth-feature-card flex items-start gap-2.5 p-3 rounded-xl transition">
            <i data-lucide="calendar" class="w-5 h-5 text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5"></i>
            <div>
              <div class="auth-feature-title text-xs font-bold">Fixed Recurring Bills</div>
              <div class="auth-feature-desc text-[11px]">Rent, WiFi, Mobile due tracker</div>
            </div>
          </div>
          <div class="auth-feature-card flex items-start gap-2.5 p-3 rounded-xl transition">
            <i data-lucide="shield-check" class="w-5 h-5 text-purple-600 dark:text-purple-400 shrink-0 mt-0.5"></i>
            <div>
              <div class="auth-feature-title text-xs font-bold">Isolated Per-User DB</div>
              <div class="auth-feature-desc text-[11px]">Strict privacy &amp; local encryption</div>
            </div>
          </div>
        </div>

      </div>'''

    if old_showcase in content:
        content = content.replace(old_showcase, new_showcase, 1)
        print("Updated desktop showcase in index.html")
    else:
        print("Could not find exact old_showcase, checking why...")

    # 3. Update auth-card-wrapper border in light mode
    content = content.replace(
        'class="auth-card-wrapper mx-auto bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl p-4 sm:p-7 rounded-3xl shadow-2xl border border-white/30 dark:border-slate-800 transition-all overflow-hidden box-border"',
        'class="auth-card-wrapper mx-auto bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl p-4 sm:p-7 rounded-3xl shadow-2xl border border-slate-200/90 dark:border-slate-800 transition-all overflow-hidden box-border"'
    )

    with open('static/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Saved static/index.html")

update_index()
