import re
import os
import logging
from datetime import date, datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc

from backend.models import User, AllowanceCycle, RefillLog, Expense, FixedExpense
from backend.schemas import AIChatRequest, AIChatResponse

logger = logging.getLogger("expense_tracker.ai")

# Strict guardrail patterns targeting sensitive server internals or other users
SENSITIVE_PATTERNS = [
    r"\.env",
    r"database_url",
    r"postgres(?:ql)?://",
    r"sqlite://",
    r"secret_key",
    r"jwt_secret",
    r"admin_secret",
    r"passwords?",
    r"password_hash",
    r"hashed_password",
    r"users?\s+table",
    r"other\s+users?",
    r"all\s+users?",
    r"singhalgarv09",
    r"drop\s+table",
    r"select\s+\*\s+from",
    r"server\s+path",
    r"api_key\s+of\s+server",
    r"system\s+prompt",
    r"jailbreak",
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"cat\s+/etc",
    r"whoami",
]


def check_security_violation(message: str) -> bool:
    """Return True if the message attempts to extract internal server secrets or other users' data."""
    lowered = message.lower()
    for pat in SENSITIVE_PATTERNS:
        if re.search(pat, lowered):
            # Check context: if user is asking "how to set my own password" or "reset password" in profile, allow it
            if "my password" in lowered or "forgot password" in lowered or "change my password" in lowered:
                continue
            return True
    return False


def get_security_refusal(user_name: str) -> str:
    return (
        f"🛡️ **Ask AI Security & Privacy Notice**\n\n"
        f"Hello {user_name}! As your dedicated AI Financial Advisor, I operate with strict privacy safeguards:\n\n"
        f"- 🔒 **Confidentiality**: I cannot access, confirm, or reveal system configurations, database credentials, server secrets, or data belonging to other users.\n"
        f"- 💼 **Personal Scope**: I am exclusively focused on analyzing **your** transactions, financial health, recurring bills, and guiding you through this web application.\n\n"
        f"Feel free to ask me anything about your expenses, daily safe spend, recurring bills, or how to use any feature of the platform!"
    )


def extract_user_dossier(user: User, db: Session) -> Dict[str, Any]:
    """Compile the user's complete, detailed financial context for deep analysis."""
    import calendar

    sym = user.currency_symbol or "₹"
    code = user.currency_code or "INR"
    today = date.today()
    target_month = f"{today.year:04d}-{today.month:02d}"

    # Allowance cycle for current month or most recent
    cycle = (
        db.query(AllowanceCycle)
        .filter(AllowanceCycle.user_id == user.id, AllowanceCycle.month_year == target_month)
        .first()
    )
    if not cycle:
        cycle = (
            db.query(AllowanceCycle)
            .filter(AllowanceCycle.user_id == user.id)
            .order_by(desc(AllowanceCycle.month_year))
            .first()
        )

    initial_allowance = float(cycle.initial_allowance or 0.0) if cycle else 0.0

    # Expenses
    expenses = (
        db.query(Expense)
        .filter(Expense.user_id == user.id)
        .order_by(desc(Expense.date), desc(Expense.id))
        .all()
    )
    total_spent = sum(float(e.amount or 0.0) for e in expenses)

    # Category breakdown
    category_totals = defaultdict(float)
    category_counts = defaultdict(int)
    for e in expenses:
        cat = e.category or "Other"
        category_totals[cat] += float(e.amount or 0.0)
        category_counts[cat] += 1

    sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)

    # Refills / Added Money
    refills = (
        db.query(RefillLog)
        .filter(RefillLog.user_id == user.id)
        .order_by(desc(RefillLog.date), desc(RefillLog.id))
        .all()
    )
    total_refills = sum(float(r.amount or 0.0) for r in refills)

    # Fixed / Recurring Bills
    fixed_bills = (
        db.query(FixedExpense)
        .filter(FixedExpense.user_id == user.id)
        .order_by(asc(FixedExpense.due_day))
        .all()
    )

    monthly_fixed_burden = 0.0
    for fb in fixed_bills:
        if fb.is_active and fb.amount:
            if fb.frequency == "quarterly":
                monthly_fixed_burden += float(fb.amount) / 3.0
            else:
                monthly_fixed_burden += float(fb.amount)

    # Calculate net balance & safe spend
    total_funds = initial_allowance + total_refills
    remaining_balance = total_funds - total_spent

    _, days_in_month = calendar.monthrange(today.year, today.month)
    days_remaining = max(1, days_in_month - today.day + 1)
    daily_safe_spend = max(0.0, remaining_balance / days_remaining)

    # Largest expense
    largest_expense = max(expenses, key=lambda x: float(x.amount or 0.0)) if expenses else None

    return {
        "user_name": user.full_name,
        "email": user.email,
        "currency_symbol": sym,
        "currency_code": code,
        "initial_allowance": initial_allowance,
        "total_funds": total_funds,
        "total_spent": total_spent,
        "remaining_balance": remaining_balance,
        "days_remaining": days_remaining,
        "daily_safe_spend": daily_safe_spend,
        "expense_count": len(expenses),
        "expenses": [
            {
                "id": e.id,
                "title": getattr(e, "description", "") or getattr(e, "title", ""),
                "amount": float(e.amount),
                "category": e.category,
                "date": str(e.date),
                "payment_mode": getattr(e, "payment_mode", "UPI") or "UPI",
                "notes": getattr(e, "receipt_note", "") or "",
            }
            for e in expenses
        ],
        "category_totals": dict(sorted_categories),
        "category_counts": dict(category_counts),
        "top_category": sorted_categories[0] if sorted_categories else None,
        "largest_expense": {
            "title": getattr(largest_expense, "description", "") or getattr(largest_expense, "title", ""),
            "amount": float(largest_expense.amount),
            "category": largest_expense.category,
            "date": str(largest_expense.date),
        }
        if largest_expense
        else None,
        "refill_count": len(refills),
        "total_refills": total_refills,
        "refills": [
            {
                "id": r.id,
                "amount": float(r.amount),
                "source": getattr(r, "funding_source", "Added Money"),
                "date": str(r.date),
                "notes": getattr(r, "reason", "") or "",
            }
            for r in refills
        ],
        "fixed_bills_count": len(fixed_bills),
        "monthly_fixed_burden": monthly_fixed_burden,
        "fixed_bills": [
            {
                "id": fb.id,
                "title": fb.title,
                "frequency": fb.frequency,
                "due_day": fb.due_day,
                "amount_type": "variable" if getattr(fb, "is_variable_amount", False) else "fixed",
                "amount": float(fb.amount) if fb.amount else None,
                "is_active": fb.is_active,
            }
            for fb in fixed_bills
        ],
    }


def call_gemini_api(
    user_message: str,
    dossier: Dict[str, Any],
    history: Optional[List[Any]],
    api_key: str,
) -> Optional[str]:
    """Call Google Gemini REST API using gemini-2.5-flash with gemini-1.5-flash fallback."""
    sym = dossier["currency_symbol"]
    user_name = dossier["user_name"]

    # Build concise category breakdown text
    cat_text = ", ".join(
        [f"{cat}: {sym}{amt:,.2f}" for cat, amt in list(dossier["category_totals"].items())[:6]]
    ) or "None recorded yet"

    # Build fixed bills text
    bills_text = ", ".join(
        [
            f"{b['title']} ({b['frequency'].capitalize()}, Due Day {b['due_day']}, "
            + (f"{sym}{b['amount']:,.2f}" if b["amount"] else "Variable")
            + ")"
            for b in dossier["fixed_bills"]
        ]
    ) or "None set"

    # Build recent expenses text
    recent_text = "; ".join(
        [
            f"{e['title']} ({sym}{e['amount']:,.2f}, {e['category']}, {e['date']})"
            for e in dossier["expenses"][:10]
        ]
    ) or "No expenses logged yet"

    # System instruction
    system_instruction = (
        f"You are Ask AI, an intelligent, empathetic, and deeply analytical AI Financial Assistant inside a personal finance, budgeting, and wealth tracking web application.\n"
        f"You are conversing with {user_name}.\n\n"
        f"CRITICAL SECURITY GUARDRAILS:\n"
        f"- You strictly operate within the context of {user_name}'s personal account records.\n"
        f"- Under NO circumstance should you share, confirm, or discuss server-side environment variables, database URLs, passwords, API keys, source code files, or data of ANY other user.\n"
        f"- If asked about secrets, system internals, or other users, decline politely and redirect back to {user_name}'s budget and website guidance.\n\n"
        f"WEBSITE FEATURES & KNOWLEDGE:\n"
        f"- Dashboard: Shows Total Spent, Remaining Balance, Daily Safe Spend, and Fixed & Recurring Bills.\n"
        f"- Expenses Tab: Allows logging daily expenses with category, payment mode, receipt, and notes. Also features the 'Fixed & Recurring Bills' manager (Electricity, WiFi, Mobile, Rent) for monthly or quarterly commitments with fixed or variable amounts.\n"
        f"- Added Money Tab: Full deposit tracker with search, source filtering, and sort.\n"
        f"- Report FAB: The raised round center button generates an itemized settlement report and allows 1-click sharing of the real PDF file directly to WhatsApp.\n"
        f"- Profile Tab: Update personal details, currency, and security questions.\n"
        f"- Dark/Light Mode: High-contrast theme toggle in top header.\n\n"
        f"CURRENT USER FINANCIAL DOSSIER:\n"
        f"- User: {user_name} ({dossier['email']})\n"
        f"- Currency: {sym} ({dossier['currency_code']})\n"
        f"- Remaining Balance: {sym}{dossier['remaining_balance']:,.2f}\n"
        f"- Total Spent: {sym}{dossier['total_spent']:,.2f} across {dossier['expense_count']} transactions\n"
        f"- Total Added Funds: {sym}{dossier['total_funds']:,.2f} (Deposits: {sym}{dossier['total_refills']:,.2f})\n"
        f"- Daily Safe Spend: {sym}{dossier['daily_safe_spend']:,.2f}/day ({dossier['days_remaining']} days remaining in allowance cycle)\n"
        f"- Top Categories: {cat_text}\n"
        f"- Monthly Recurring Bills Burden: ~{sym}{dossier['monthly_fixed_burden']:,.2f}/month (Bills: {bills_text})\n"
        f"- Recent Transactions: {recent_text}\n\n"
        f"RESPONSE STYLE:\n"
        f"- Answer as Ask AI: insightful, structured markdown, bullet points, emoji badges, precise financial calculations, and actionable advice.\n"
        f"- Keep responses conversational yet crisp and visually appealing."
    )

    # Format multi-turn contents
    contents = []
    if history:
        for item in history[-6:]:
            role = "model" if getattr(item, "role", "") in ("model", "assistant") else "user"
            content = getattr(item, "content", "")
            if content:
                contents.append({"role": role, "parts": [{"text": content}]})

    contents.append({"role": "user", "parts": [{"text": user_message}]})

    models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash"]
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048,
            },
        }
        try:
            with httpx.Client(timeout=12.0) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"]
                else:
                    logger.warning(f"Gemini API {model_name} returned status {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"Gemini API request failed for {model_name}: {e}")

    return None


def run_builtin_financial_analyst(user_message: str, dossier: Dict[str, Any]) -> str:
    """Intelligent built-in financial analysis engine producing rich, conversational personal insights
    answering ANY query about the user's transactions, categories, balance, bills, refills, and habits.
    """
    msg = user_message.lower().strip()
    sym = dossier["currency_symbol"]
    name = dossier["user_name"]
    bal = dossier["remaining_balance"]
    spent = dossier["total_spent"]
    funds = dossier["total_funds"]
    daily_safe = dossier["daily_safe_spend"]
    days_left = dossier["days_remaining"]
    exp_count = dossier["expense_count"]
    cats = dossier["category_totals"]
    bills = dossier["fixed_bills"]
    burden = dossier["monthly_fixed_burden"]
    largest = dossier["largest_expense"]
    expenses = dossier.get("expenses", [])
    refills = dossier.get("refills", [])

    # 1. GREETINGS & INTRODUCTIONS
    if any(re.search(r"\b" + re.escape(w) + r"\b", msg) for w in ["hi", "hello", "hey", "hola", "greetings", "good morning", "good afternoon", "good evening", "who are you", "what can you do", "introduce yourself"]):
        status_tag = "🟢 Safe & Balanced" if bal >= (funds * 0.3) else ("🟡 Low Balance" if bal > 0 else "🔴 Deficit Warning")
        lines = [
            f"### 👋 Hello {name}!",
            "",
            f"I am your personal **Ask AI Financial Assistant**. I have complete access to your account ledger, all your **{exp_count} logged transactions**, recurring bills, and budget cycle.",
            "",
            "#### 📊 Your Live Financial Snapshot:",
            f"- **Current Balance**: **{sym}{bal:,.2f}** ({status_tag})",
            f"- **Total Spent This Month**: **{sym}{spent:,.2f}** across {exp_count} expenses",
            f"- **Daily Safe Spend**: **{sym}{daily_safe:,.2f} / day** ({days_left} days left)",
            "",
            "#### 💬 What you can ask me:",
            f"1. *'What are my recent transactions?'* or *'What did I spend on yesterday?'*",
            f"2. *'How much did I spend on Food / Travel / Shopping?'*",
            f"3. *'Can I afford to buy headphones for {sym}1,500?'*",
            f"4. *'What was my highest single expense?'*",
            f"5. *'Show my upcoming recurring bills'* or *'How can I save money?'*",
            "",
            "Ask me anything about your finances!"
        ]
        return "\n".join(lines)

    # 2. USER PROFILE / IDENTITY
    if any(k in msg for k in ["who am i", "my name", "my email", "my profile", "my account info", "what is my email", "account details"]):
        lines = [
            f"### 👤 Your Account Profile",
            "",
            f"- **Account Name**: **{name}**",
            f"- **Registered Email**: `{dossier.get('email', 'N/A')}`",
            f"- **Active Currency**: **{sym} ({dossier.get('currency_code', 'INR')})**",
            f"- **Total Funds Managed**: **{sym}{funds:,.2f}**",
            f"- **Expenses Logged**: **{exp_count} records**",
            f"- **Refills Logged**: **{len(refills)} records**",
            f"- **Database Isolation**: Protected in your private local database container."
        ]
        return "\n".join(lines)

    # 3. AFFORDABILITY ASSESSMENT ("Can I afford / buy / spend X?")
    afford_match = re.search(
        r"(?:can i (?:afford|buy|spend|get)|should i buy|is it safe to (?:buy|spend)|afford to buy)\s*(?:a|an)?\s*([a-zA-Z\s]+)?(?:for|worth|costing|of)?\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)",
        msg,
    )
    if not afford_match:
        simple_afford = re.search(r"(?:can i (?:afford|spend|buy))\s*(?:rs\.?|inr|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)", msg)
        if simple_afford:
            afford_match = simple_afford

    if afford_match:
        try:
            if len(afford_match.groups()) >= 2 and afford_match.group(2):
                item_name = (afford_match.group(1) or "this purchase").strip()
                num_str = afford_match.group(2).replace(",", "")
            else:
                item_name = "this purchase"
                num_str = afford_match.group(1).replace(",", "")

            cost = float(num_str)
            new_bal = bal - cost
            new_safe = max(0.0, new_bal / days_left) if days_left > 0 else 0.0

            if bal <= 0:
                verdict = "🛑 **Not Recommended / Budget Deficit**"
                advice = f"Your current balance is **{sym}{bal:,.2f}**. Making this purchase will plunge you into a deficit."
            elif cost > bal:
                verdict = "🛑 **Insufficient Balance**"
                advice = f"This purchase of **{sym}{cost:,.2f}** exceeds your available balance of **{sym}{bal:,.2f}** by **{sym}{(cost - bal):,.2f}**."
            elif new_safe < (daily_safe * 0.4) and days_left > 5:
                verdict = "⚠️ **Proceed with Caution**"
                advice = f"You can technically cover this, but it will drop your daily safe spend from **{sym}{daily_safe:,.2f}/day** down to **{sym}{new_safe:,.2f}/day** for the remaining {days_left} days."
            else:
                verdict = "✅ **Safe to Purchase!**"
                advice = f"You have sufficient buffer. After spending **{sym}{cost:,.2f}**, you will retain **{sym}{new_bal:,.2f}**, maintaining a comfortable safe spend of **{sym}{new_safe:,.2f}/day**."

            lines = [
                f"### 🎯 Affordability Assessment: {item_name.title()}",
                "",
                verdict,
                "",
                f"- **Proposed Purchase**: **{sym}{cost:,.2f}**",
                f"- **Current Balance**: **{sym}{bal:,.2f}**",
                f"- **Balance After Purchase**: **{sym}{new_bal:,.2f}**",
                f"- **New Daily Safe Spend**: **{sym}{new_safe:,.2f}/day** ({days_left} days left)",
                "",
                f"**Ask AI Advice**: {advice}",
                "",
                "> 💡 *Tip: If you proceed, remember to log it under the appropriate category to keep your daily pace accurate!*"
            ]
            return "\n".join(lines)
        except Exception:
            pass

    # 4. RECENT TRANSACTIONS / ITEM LISTING
    if any(k in msg for k in ["recent", "latest transaction", "latest expense", "what did i spend on", "my expenses", "show transactions", "list transactions", "show expenses", "past purchases", "what i bought", "purchases"]):
        if not expenses:
            return (
                f"### 📋 Your Transactions\n\n"
                f"You haven't logged any expenses yet this month.\n\n"
                f"- **Available Balance**: **{sym}{bal:,.2f}**\n"
                f"- **Starting Funds**: **{sym}{funds:,.2f}**\n\n"
                f"Tap the **Expenses** tab or click the **'+' button** to record your first transaction!"
            )

        recent_items = sorted(expenses, key=lambda x: str(x.get("date", "")), reverse=True)[:7]
        lines = [f"### 📋 Your Recent Transactions ({len(recent_items)} of {exp_count})", ""]
        for i, exp in enumerate(recent_items, 1):
            date_str = exp.get("date", "N/A")
            cat_str = exp.get("category", "General")
            title_str = exp.get("title") or "Expense"
            amt_str = f"{sym}{exp.get('amount', 0.0):,.2f}"
            mode_str = exp.get("payment_mode", "UPI")
            lines.append(f"{i}. **{title_str}** — **{amt_str}**")
            lines.append(f"   📅 *{date_str}* • 🏷️ *{cat_str}* • 💳 *{mode_str}*")
            lines.append("")

        lines.append("---")
        lines.append(f"📈 **Summary**: Total spent across all {exp_count} transactions is **{sym}{spent:,.2f}**, leaving you with a remaining balance of **{sym}{bal:,.2f}**.")
        return "\n".join(lines)

    # 5. HIGHEST / LARGEST / SMALLEST EXPENSES
    if any(k in msg for k in ["highest", "largest", "biggest", "most expensive", "maximum expense", "max expense"]):
        if not largest or not expenses:
            return f"### 🔍 Highest Expense\n\nYou have not logged any expenses yet this cycle."

        pct = (largest['amount'] / spent * 100.0) if spent > 0 else 0.0
        lines = [
            "### 🔍 Largest Single Expense This Month",
            "",
            f"Your biggest single purchase was **{largest['title']}**:",
            "",
            f"- 💰 **Amount**: **{sym}{largest['amount']:,.2f}**",
            f"- 🏷️ **Category**: **{largest['category']}**",
            f"- 📅 **Date**: **{largest['date']}**",
            f"- 📊 **Share of Total Spend**: **{pct:.1f}%** of all expenses ({sym}{spent:,.2f})",
            "",
            "💡 *Insight: This single transaction represents a significant portion of your budget.*"
        ]
        return "\n".join(lines)

    if any(k in msg for k in ["smallest", "lowest", "cheapest", "minimum expense"]):
        if not expenses:
            return f"### 🔍 Smallest Expense\n\nYou have not logged any expenses yet this cycle."

        smallest_exp = min(expenses, key=lambda x: float(x.get("amount", 0.0)))
        lines = [
            "### 🔍 Smallest Logged Expense",
            "",
            f"Your lowest recorded expense was **{smallest_exp.get('title', 'Expense')}**:",
            "",
            f"- 💰 **Amount**: **{sym}{smallest_exp.get('amount', 0.0):,.2f}**",
            f"- 🏷️ **Category**: **{smallest_exp.get('category', 'General')}**",
            f"- 📅 **Date**: **{smallest_exp.get('date', 'N/A')}**"
        ]
        return "\n".join(lines)

    # 6. SPECIFIC CATEGORY OR ITEM INQUIRY
    cat_aliases = {
        "food": ["food", "dining", "meal", "swiggy", "zomato", "restaurant", "lunch", "dinner", "breakfast", "chai", "coffee", "snacks", "grocery", "groceries"],
        "travel": ["travel", "transport", "cab", "uber", "ola", "auto", "metro", "bus", "train", "fuel", "petrol", "flight"],
        "shopping": ["shopping", "clothes", "clothing", "shoes", "amazon", "flipkart", "myntra", "electronics", "gadget", "watch"],
        "bills": ["bill", "utility", "electricity", "recharge", "wifi", "internet", "broadband", "rent", "water", "gas"],
        "entertainment": ["entertainment", "movie", "cinema", "netflix", "prime", "game", "gaming", "outing", "party", "club"],
        "healthcare": ["health", "medical", "medicine", "pharmacy", "doctor", "clinic", "hospital", "gym", "fitness"],
        "education": ["education", "book", "books", "course", "stationery", "tuition", "fee", "fees", "exam", "college"],
    }

    matched_category_key = None
    for standard_cat, words in cat_aliases.items():
        if any(re.search(r"\b" + re.escape(w) + r"\b", msg) for w in words):
            matched_category_key = standard_cat
            break

    for actual_cat in cats.keys():
        if actual_cat.lower() in msg:
            matched_category_key = actual_cat.lower()
            break

    if matched_category_key:
        matching_expenses = []
        for e in expenses:
            c_name = str(e.get("category", "")).lower()
            t_name = str(e.get("title", "")).lower()
            notes_name = str(e.get("notes", "")).lower()
            relevant_words = cat_aliases.get(matched_category_key, [matched_category_key])
            if any(w in c_name or w in t_name or w in notes_name for w in relevant_words):
                matching_expenses.append(e)

        cat_sum = sum(float(e.get("amount", 0.0)) for e in matching_expenses)
        pct = (cat_sum / spent * 100.0) if spent > 0 else 0.0

        if matching_expenses:
            lines = [
                f"### 🏷️ Spending Analysis: {matched_category_key.title()}",
                "",
                f"You have spent **{sym}{cat_sum:,.2f}** on **{matched_category_key.title()}** across **{len(matching_expenses)} purchases**.",
                "",
                f"- **Share of Total Budget**: **{pct:.1f}%** of your total {sym}{spent:,.2f} spend",
                f"- **Remaining Total Balance**: **{sym}{bal:,.2f}**",
                "",
                "#### 📝 Breakdown of Transactions:"
            ]
            for exp in matching_expenses[:6]:
                lines.append(f"- **{exp.get('title')}**: {sym}{float(exp.get('amount', 0.0)):,.2f} *(on {exp.get('date')})*")

            if len(matching_expenses) > 6:
                lines.append(f"- *...and {len(matching_expenses)-6} more purchases*")

            lines.append("")
            lines.append(f"💡 *Tip: Keeping {matched_category_key.title()} expenses within a planned allocation will help ensure your remaining funds last comfortably until next month.*")
            return "\n".join(lines)
        else:
            lines = [
                f"### 🏷️ Spending on {matched_category_key.title()}",
                "",
                f"I checked your records and found **0 expenses** logged under or related to **'{matched_category_key.title()}'**.",
                "",
                f"- **Total Recorded Spend**: **{sym}{spent:,.2f}** across other categories",
                f"- **Remaining Balance**: **{sym}{bal:,.2f}**",
                "",
                "If you made a purchase in this category, you can add it via the **Expenses** tab!"
            ]
            return "\n".join(lines)

    # 7. OVERALL CATEGORY BREAKDOWN
    if any(k in msg for k in ["breakdown", "categories", "category", "where did my money go", "spending habit", "all categories", "distribution"]):
        if not cats:
            return (
                f"### 📊 Spending & Category Breakdown for {name}\n\n"
                f"You haven't logged any expenses yet! Once you add daily expenses or bills, I will analyze your spending distribution, identify patterns, and highlight cost-saving opportunities.\n\n"
                f"- **Current Balance**: **{sym}{bal:,.2f}**\n"
                f"- **Total Added Funds**: **{sym}{funds:,.2f}**"
            )

        lines = [
            f"### 📊 Spending Distribution for {name}",
            "",
            f"You have logged **{exp_count} expenses**, totaling **{sym}{spent:,.2f}** out of your **{sym}{funds:,.2f}** total funds.",
            "",
            "#### 🏷️ Breakdown by Category:"
        ]
        for cat, amount in cats.items():
            pct = (amount / spent * 100.0) if spent > 0 else 0.0
            lines.append(f"- **{cat}**: **{sym}{amount:,.2f}** *({pct:.1f}% of total)*")

        top_cat_name, top_cat_amt = list(cats.items())[0]
        lines.append("")
        lines.append(f"💡 **Top Category**: Your largest spend area is **{top_cat_name}** at **{sym}{top_cat_amt:,.2f}**. Monitoring this category will give you the most leverage to protect your remaining balance of **{sym}{bal:,.2f}**.")
        return "\n".join(lines)

    # 8. BALANCE, FUNDS & DAILY SAFE SPEND
    if any(k in msg for k in ["balance", "safe spend", "daily safe", "how much money", "funds left", "remaining", "how much can i spend", "am i safe", "deficit"]):
        status_emoji = "🟢" if bal > (funds * 0.3) else ("🟡" if bal > 0 else "🔴")
        lines = [
            "### 💰 Balance & Daily Safe Spend Report",
            "",
            f"{status_emoji} **Net Available Balance**: **{sym}{bal:,.2f}**",
            "",
            f"- **Starting / Initial Allowance**: {sym}{dossier.get('initial_allowance', 0.0):,.2f}",
            f"- **Added Deposits (Refills)**: {sym}{dossier.get('total_refills', 0.0):,.2f}",
            f"- **Total Available Funds**: **{sym}{funds:,.2f}**",
            f"- **Total Spent So Far**: **{sym}{spent:,.2f}** across {exp_count} expenses",
            f"- **Days Remaining in Cycle**: **{days_left} days**",
            f"- **Recommended Daily Safe Spend**: **{sym}{daily_safe:,.2f} / day**",
            "",
            "#### 📈 How Your Daily Safe Spend Works:",
            f"I divide your remaining balance (**{sym}{bal:,.2f}**) by your **{days_left} remaining days**. If your daily variable spending stays below **{sym}{daily_safe:,.2f}**, your money will last comfortably through to your next allowance cycle!"
        ]
        return "\n".join(lines)

    # 9. FIXED RECURRING BILLS
    if any(k in msg for k in ["bill", "fixed", "recurring", "rent", "wifi", "electricity", "upcoming due", "subscription"]):
        if not bills:
            return (
                f"### ⚡ Fixed & Recurring Bills\n\n"
                f"You currently have no fixed recurring bills configured.\n\n"
                f"💡 **Tip**: You can set up recurring commitments like **WiFi, Electricity, Mobile Recharge, or Rent** in the **Expenses** tab under **Fixed & Recurring Bills**!"
            )

        lines = [
            f"### ⚡ Your Fixed & Recurring Bills ({len(bills)} Tracked)",
            "",
            f"Estimated monthly recurring commitment: **{sym}{burden:,.2f} / month**",
            ""
        ]
        for b in bills:
            amt_text = f"{sym}{b['amount']:,.2f}" if b.get("amount") else "Variable"
            status_tag = "Active" if b.get("is_active") else "Paused"
            lines.append(f"- **{b['title']}**: {amt_text} • *{b['frequency'].capitalize()}* (Due Day: {b['due_day']}) [{status_tag}]")

        lines.append("")
        lines.append("🛠️ **How to Log**: When a bill arrives, open the **Expenses** tab ➔ **Fixed & Recurring Bills** and tap **'Log This Bill'** to record it directly into your expense journal with one tap.")
        return "\n".join(lines)

    # 10. REFILLS & DEPOSITS
    if any(k in msg for k in ["refill", "deposit", "added money", "pocket money", "incoming funds", "received money"]):
        refills_count = dossier["refill_count"]
        refills_sum = dossier["total_refills"]
        if not refills:
            return (
                f"### 📥 Added Money & Refills\n\n"
                f"No mid-month deposits or refills have been logged yet.\n\n"
                f"- **Starting Allowance**: **{sym}{dossier.get('initial_allowance', 0.0):,.2f}**\n"
                f"- **Net Balance**: **{sym}{bal:,.2f}**\n\n"
                f"You can log incoming pocket money or salary in the **Added Money** tab!"
            )

        lines = [
            "### 📥 Added Money & Deposits Summary",
            "",
            f"- **Total Refills Logged**: {refills_count} deposits",
            f"- **Total Refilled Volume**: **{sym}{refills_sum:,.2f}**",
            f"- **Starting Base Allowance**: {sym}{dossier.get('initial_allowance', 0.0):,.2f}",
            f"- **Total Gross Funds**: **{sym}{funds:,.2f}**",
            "",
            "#### 📋 Recent Deposits:"
        ]
        for r in refills[:5]:
            note_str = f" ({r.get('notes')})" if r.get("notes") else ""
            lines.append(f"- **{sym}{float(r.get('amount', 0.0)):,.2f}** from *{r.get('source')}* on {r.get('date')}{note_str}")

        lines.append("")
        lines.append("You can view and filter all deposit records in the **Added Money** tab.")
        return "\n".join(lines)

    # 11. SAVINGS ADVICE
    if any(k in msg for k in ["save", "saving", "tip", "advice", "reduce", "budget plan", "cut expense", "improve", "financial advice"]):
        top_cat = dossier.get("top_category")
        if top_cat:
            cat_advice = f"Your highest spending area is **{top_cat[0]}** ({sym}{top_cat[1]:,.2f}). Trimming just 15% here will immediately free up **{sym}{(top_cat[1]*0.15):,.2f}**."
        else:
            cat_advice = "Consistently log every daily expense to pinpoint untracked spending leaks."

        lines = [
            f"### 💡 Personalized Financial & Savings Strategy for {name}",
            "",
            f"Based on your current balance of **{sym}{bal:,.2f}** and daily safe spend of **{sym}{daily_safe:,.2f}/day**:",
            "",
            f"1. **Control Your Highest Outflow**: {cat_advice}",
            f"2. **Respect the Daily Limit**: Keep non-essential daily spending within **{sym}{daily_safe:,.2f}/day**. Any unspent money accumulates to expand your cushion!",
            f"3. **Reserve for Recurring Dues**: You have **~{sym}{burden:,.2f}/month** in fixed bills. Always keep this amount earmarked.",
            f"4. **The 24-Hour Rule**: Before making any impulsive purchase over {sym}500, ask me: *'Can I afford to buy [item] for [amount]?'* and wait 24 hours."
        ]
        return "\n".join(lines)

    # 12. WEBSITE HELP, SHARING & WHATSAPP PDF
    if any(k in msg for k in ["how to", "whatsapp", "pdf", "share", "export", "guide", "settlement", "financial report", "report"]):
        lines = [
            "### 📱 Website & Report Features Guide",
            "",
            "1. **Share Report on WhatsApp as PDF**:",
            "   - Tap the **Report** button in the navigation bar.",
            "   - Click **'Share on WhatsApp'** or **'Download PDF'**.",
            "   - It creates an official, itemized financial statement ready to share!",
            "",
            "2. **Fixed & Recurring Bills**:",
            "   - Go to **Expenses** ➔ tap **Fixed & Recurring Bills** ➔ add recurring commitments.",
            "",
            "3. **Switch Dark / Light Mode**:",
            "   - Use the sun/moon toggle button in the top header to switch themes anytime."
        ]
        return "\n".join(lines)

    # 13. COMPREHENSIVE PERSONAL FINANCIAL SUMMARY (ANSWERS ALL OTHER QUERIES!)
    burn_rate = (spent / funds * 100.0) if funds > 0 else 0.0
    health_status = (
        "Excellent health — your spending pace is well within limits."
        if bal > (funds * 0.4)
        else ("Moderate pace — keep an eye on discretionary spending."
              if bal > (funds * 0.15)
              else "Low cushion — recommend limiting non-essential expenses.")
    )

    lines = [
        f"### 💡 Financial Analysis for {name}",
        "",
        f"Regarding your query: *\"{user_message}\"*",
        "",
        "Here is your personalized account status based on your complete transaction history:",
        "",
        f"- 💵 **Net Available Balance**: **{sym}{bal:,.2f}**",
        f"- 📉 **Total Spent This Cycle**: **{sym}{spent:,.2f}** ({burn_rate:.1f}% of funds used)",
        f"- 📥 **Total Funds (Allowance + Refills)**: **{sym}{funds:,.2f}**",
        f"- 🎯 **Recommended Safe Spend**: **{sym}{daily_safe:,.2f} / day** ({days_left} days remaining)",
        f"- ⚡ **Upcoming Fixed Dues**: **~{sym}{burden:,.2f} / month** across {len(bills)} bills",
        "",
        "#### 📊 AI Assessment:",
        f"**{health_status}**",
        "",
        "#### 🔍 Recommended Next Steps:",
        "1. Ask: *'What are my recent transactions?'* to review latest purchases.",
        f"2. Ask: *'Can I afford to spend {sym}500 today?'* for an instant budget simulation.",
        "3. Ask: *'How much did I spend on Food?'* or any specific category to inspect your habits."
    ]
    return "\n".join(lines)



def generate_suggested_questions(dossier: Dict[str, Any]) -> List[str]:
    """Provide dynamic, highly relevant 1-click follow-up prompts."""
    sym = dossier["currency_symbol"]
    suggestions = [
        "📊 Analyze all my transactions & spending breakdown",
        f"💰 What is my remaining balance and daily safe spend?",
    ]

    if dossier["fixed_bills_count"] > 0:
        suggestions.append("⚡ What are my upcoming fixed recurring bills?")
    else:
        suggestions.append("⚡ How do I set up a fixed recurring bill?")

    if dossier["largest_expense"]:
        suggestions.append(f"🔍 What was my biggest single expense this month?")
    else:
        suggestions.append(f"🎯 Can I afford a purchase of {sym}1,000 today?")

    suggestions.append("📄 How do I share my report on WhatsApp as a PDF?")
    return suggestions[:4]


def process_ai_query(user: User, db: Session, request: AIChatRequest) -> AIChatResponse:
    """Process an AI chat query with privacy guardrails and dual engine (API + Built-in)."""
    clean_msg = request.message.strip()

    # 1. Security Guardrail Check
    if check_security_violation(clean_msg):
        return AIChatResponse(
            reply=get_security_refusal(user.full_name),
            source="security-guardrail",
            suggested_questions=[
                "📊 Analyze my personal spending breakdown",
                "💰 What is my current balance?",
                "⚡ Check my recurring bills",
                "💡 Give me personalized saving tips",
            ],
        )

    # 2. Extract full context for authenticated user
    dossier = extract_user_dossier(user, db)

    # 3. Determine API Key (from request or environment)
    api_key = (request.api_key or "").strip() or os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()

    # 4. Attempt Cloud AI API if key is available
    if api_key:
        reply = call_gemini_api(clean_msg, dossier, request.history, api_key)
        if reply:
            return AIChatResponse(
                reply=reply,
                source="ask-ai-cloud",
                suggested_questions=generate_suggested_questions(dossier),
            )

    # 5. Built-in Financial Analyst Engine
    analyst_reply = run_builtin_financial_analyst(clean_msg, dossier)
    return AIChatResponse(
        reply=analyst_reply,
        source="ask-ai-analyst",
        suggested_questions=generate_suggested_questions(dossier),
    )
