with open('static/index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print('Total lines in index.html:', len(lines))
for i, line in enumerate(lines):
    l = line.lower()
    if 'id="tab' in line or 'tabcontent' in l or ('id=' in line and any(k in l for k in ['settle', 'analytic', 'profile', 'banner', 'toast'])):
        print(f'{i+1}: {line.strip()[:100]}')
