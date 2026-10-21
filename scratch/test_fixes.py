with open('static/app.js', 'r', encoding='utf-8') as f:
    js_code = f.read()

assert 'function switchExpenseSubTab' in js_code
assert 'function loadFixedExpenses' in js_code
assert 'function handleSaveFixedExpense' in js_code
assert 'function promptLogFixedBill' in js_code
assert 'function executeLogFixedBill' in js_code

with open('static/index.html', 'r', encoding='utf-8') as f:
    html_code = f.read()

assert 'id="remainingBalanceCard"' in html_code
assert 'id="statTotalSpent"' in html_code

rem_idx = html_code.find('id="remainingBalanceCard"')
spent_idx = html_code.find('id="statTotalSpent"')
assert rem_idx < spent_idx, f"Expected rem_idx ({rem_idx}) < spent_idx ({spent_idx})"

assert 'bg-white dark:bg-gradient-to-r' in html_code
assert 'text-slate-900 dark:text-white' in html_code

print("All assertion tests passed successfully!")
