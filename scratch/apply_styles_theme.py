# Script to update static/styles.css for auth theme contrast and hidden specificity

def update_styles():
    with open('static/styles.css', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update lines 1083-1098
    old_section_1 = '''#authScreen {
  width: 100% !important;
  max-width: 100vw !important;
  min-height: 100dvh !important;
  box-sizing: border-box !important;
  overflow-x: hidden !important;
}

@media (max-width: 640px) {
  #authScreen {
    padding: 12px 8px !important;
    align-items: flex-start !important;
    padding-top: 16px !important;
    padding-bottom: 24px !important;
  }
}'''

    new_section_1 = '''#authScreen.hidden,
#appScreen.hidden {
  display: none !important;
}

#authScreen:not(.hidden) {
  width: 100% !important;
  max-width: 100vw !important;
  min-height: 100dvh !important;
  box-sizing: border-box !important;
  overflow-x: hidden !important;
}

@media (max-width: 640px) {
  #authScreen:not(.hidden) {
    padding: 12px 8px !important;
    align-items: flex-start !important;
    padding-top: 16px !important;
    padding-bottom: 24px !important;
  }
}'''

    if old_section_1 in content:
        content = content.replace(old_section_1, new_section_1, 1)
        print("Updated section 1 in styles.css")
    else:
        print("Could not find old_section_1, check formatting...")

    # 2. Update lines 1187 to end
    old_section_2 = '''/* ==========================================================================
   RESPONSIVE AUTH LAYOUT: DESKTOP SHOWCASE (>= 1024px) vs MOBILE FIT
   ========================================================================== */
.auth-grid-layout {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  box-sizing: border-box;
}

.auth-desktop-showcase {
  display: none;
}

.auth-card-wrapper {
  width: 100%;
  max-width: 480px;
  box-sizing: border-box;
}

@media (min-width: 1024px) {
  #authScreen {
    padding: 32px 48px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
  }

  .auth-grid-layout {
    display: grid !important;
    grid-template-columns: 1.2fr 0.95fr !important;
    gap: 48px !important;
    align-items: center !important;
    max-width: 1200px !important;
    width: 100% !important;
    margin: 0 auto !important;
  }

  .auth-desktop-showcase {
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
    gap: 20px !important;
    color: #ffffff !important;
    user-select: none !important;
  }

  .auth-card-wrapper {
    width: 100% !important;
    max-width: 490px !important;
    margin: 0 auto !important;
  }
}

@media (max-width: 1023px) {
  .auth-desktop-showcase {
    display: none !important;
  }
  .auth-card-wrapper {
    width: 100% !important;
    max-width: 460px !important;
  }
}'''

    new_section_2 = '''/* ==========================================================================
   RESPONSIVE AUTH LAYOUT & THEME CONTRAST SYSTEM (LIGHT & DARK MODE)
   ========================================================================== */
#authScreen {
  background: linear-gradient(135deg, #f1f5f9 0%, #e0e7ff 45%, #f8fafc 100%) !important;
  color: #0f172a;
  transition: background 0.25s ease, color 0.25s ease;
}

html.dark #authScreen {
  background: linear-gradient(135deg, #020617 0%, #0f172a 45%, #1e1b4b 100%) !important;
  color: #f8fafc;
}

.auth-orb-1 {
  background: rgba(99, 102, 241, 0.16);
}
.auth-orb-2 {
  background: rgba(16, 185, 129, 0.12);
}
html.dark .auth-orb-1 {
  background: rgba(99, 102, 241, 0.22);
}
html.dark .auth-orb-2 {
  background: rgba(16, 185, 129, 0.16);
}

.auth-grid-layout {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  box-sizing: border-box;
}

.auth-desktop-showcase {
  display: none;
}

.auth-card-wrapper {
  width: 100%;
  max-width: 480px;
  box-sizing: border-box;
}

/* Light Mode Defaults for Desktop Showcase (High Contrast, Crisp & Legible) */
.auth-showcase-badge {
  background: rgba(255, 255, 255, 0.95) !important;
  border: 1px solid #c7d2fe !important;
  color: #4338ca !important;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.auth-showcase-title {
  color: #0f172a !important;
}

.auth-showcase-subtitle {
  color: #334155 !important;
  font-weight: 500 !important;
}

.auth-showcase-card {
  background: rgba(255, 255, 255, 0.95) !important;
  border: 1px solid #e2e8f0 !important;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.06), 0 8px 10px -6px rgba(0, 0, 0, 0.04) !important;
  backdrop-filter: blur(12px);
}

.auth-card-divider {
  border-color: #e2e8f0 !important;
}

.auth-card-head {
  color: #1e293b !important;
}

.auth-card-badge {
  background: #ecfdf5 !important;
  color: #047857 !important;
  border: 1px solid #a7f3d0 !important;
}

.auth-stat-box {
  background: #f8fafc !important;
  border: 1px solid #e2e8f0 !important;
}

.auth-stat-label {
  color: #64748b !important;
  font-weight: 700 !important;
}

.auth-stat-val-allowance {
  color: #0f172a !important;
  font-weight: 800 !important;
}

.auth-stat-val-spent {
  color: #e11d48 !important;
  font-weight: 800 !important;
}

.auth-stat-val-balance {
  color: #059669 !important;
  font-weight: 800 !important;
}

.auth-spend-rate {
  color: #4338ca !important;
  font-weight: 600 !important;
}

.auth-spend-rate-val {
  color: #0f172a !important;
  font-weight: 800 !important;
}

.auth-days-left {
  color: #64748b !important;
  font-weight: 600 !important;
}

.auth-feature-card {
  background: rgba(255, 255, 255, 0.95) !important;
  border: 1px solid #e2e8f0 !important;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.04) !important;
}

.auth-feature-title {
  color: #0f172a !important;
  font-weight: 700 !important;
}

.auth-feature-desc {
  color: #475569 !important;
  font-weight: 500 !important;
}

/* Dark Mode Overrides for Showcase (Vibrant Neon Glassmorphism) */
html.dark .auth-showcase-badge {
  background: rgba(255, 255, 255, 0.08) !important;
  border: 1px solid rgba(255, 255, 255, 0.18) !important;
  color: #c7d2fe !important;
  box-shadow: none !important;
}

html.dark .auth-showcase-title {
  color: #ffffff !important;
}

html.dark .auth-showcase-subtitle {
  color: #cbd5e1 !important;
  font-weight: 400 !important;
}

html.dark .auth-showcase-card {
  background: rgba(15, 23, 42, 0.72) !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  box-shadow: 0 12px 30px -5px rgba(0, 0, 0, 0.5) !important;
}

html.dark .auth-card-divider {
  border-color: rgba(255, 255, 255, 0.1) !important;
}

html.dark .auth-card-head {
  color: #cbd5e1 !important;
}

html.dark .auth-card-badge {
  background: rgba(16, 185, 129, 0.2) !important;
  color: #6ee7b7 !important;
  border: 1px solid rgba(16, 185, 129, 0.3) !important;
}

html.dark .auth-stat-box {
  background: rgba(255, 255, 255, 0.05) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
}

html.dark .auth-stat-label {
  color: #94a3b8 !important;
}

html.dark .auth-stat-val-allowance {
  color: #ffffff !important;
}

html.dark .auth-stat-val-spent {
  color: #fda4af !important;
}

html.dark .auth-stat-val-balance {
  color: #6ee7b7 !important;
}

html.dark .auth-spend-rate {
  color: #c7d2fe !important;
}

html.dark .auth-spend-rate-val {
  color: #ffffff !important;
}

html.dark .auth-days-left {
  color: #94a3b8 !important;
}

html.dark .auth-feature-card {
  background: rgba(255, 255, 255, 0.06) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  box-shadow: none !important;
}

html.dark .auth-feature-title {
  color: #ffffff !important;
}

html.dark .auth-feature-desc {
  color: #cbd5e1 !important;
}

@media (min-width: 1024px) {
  #authScreen:not(.hidden) {
    padding: 32px 48px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
  }

  .auth-grid-layout {
    display: grid !important;
    grid-template-columns: 1.2fr 0.95fr !important;
    gap: 48px !important;
    align-items: center !important;
    max-width: 1200px !important;
    width: 100% !important;
    margin: 0 auto !important;
  }

  .auth-desktop-showcase {
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
    gap: 20px !important;
    user-select: none !important;
  }

  .auth-card-wrapper {
    width: 100% !important;
    max-width: 490px !important;
    margin: 0 auto !important;
  }
}

@media (max-width: 1023px) {
  .auth-desktop-showcase {
    display: none !important;
  }
  .auth-card-wrapper {
    width: 100% !important;
    max-width: 460px !important;
  }
}'''

    if old_section_2 in content:
        content = content.replace(old_section_2, new_section_2, 1)
        print("Updated section 2 in styles.css")
    else:
        print("Could not find old_section_2, checking why...")

    with open('static/styles.css', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Saved static/styles.css")

update_styles()
