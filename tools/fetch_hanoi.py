#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ดึงผลหวยฮานอย (ปกติ / พิเศษ / VIP / เฉพาะกิจ) จากหน้า Sanook
หน้าเดียวมีย้อนหลัง ~51 วัน × 4 ประเภท — รันซ้ำทุกวันแล้ว "สะสม" เพิ่มเรื่อยๆ
ออก: hanoi_history.js / .json (ให้เว็บแอป) + .csv (Google Sheet) + .xlsx

ใช้: python tools/fetch_hanoi.py
"""
import urllib.request, re, html as htmlmod, json, datetime, os

HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
URL = 'https://www.sanook.com/news/9837690/'
OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPES = {'ปกติ': 'hanoi', 'พิเศษ': 'hanoiSpecial', 'vip': 'hanoiVip', 'เฉพาะกิจ': 'hanoiTask'}
NAMES = {'hanoi': 'ฮานอย', 'hanoiSpecial': 'ฮานอยพิเศษ', 'hanoiVip': 'ฮานอย VIP', 'hanoiTask': 'ฮานอยเฉพาะกิจ'}
ORDER = ['hanoi', 'hanoiSpecial', 'hanoiVip', 'hanoiTask']
TM = ['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.']

def ts_utc(y, m, d):  # เที่ยงคืน UTC (กำหนดตายตัว เครื่องไหน/CI ตรงกัน)
    return int(datetime.datetime(y, m, d, tzinfo=datetime.timezone.utc).timestamp() * 1000)

def scrape():
    html = urllib.request.urlopen(urllib.request.Request(URL, headers=HDR), timeout=25).read().decode('utf-8', 'ignore')
    text = htmlmod.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)))
    dmarks = [(m.start(), int(m.group(1)), int(m.group(2)), int(m.group(3)))
              for m in re.finditer(r'หวยฮานอย\s*(\d{1,2})/(\d{1,2})/(\d{2,4})', text)]
    block = re.compile(r'ผลหวยฮานอย([ก-๙A-Za-z ]{0,14}?)\s*(?:เลข\s*4\s*ตัว\s*:\s*\d+\s*)?'
                       r'เลข\s*3\s*ตัวบน\s*:\s*(\d{3})\s*เลข\s*2\s*ตัวบน\s*:\s*(\d{2})\s*เลข\s*2\s*ตัวล่าง\s*:\s*(\d{2})')
    def near(pos):
        prev = [d for d in dmarks if d[0] <= pos]
        return (prev[-1] if prev else dmarks[0])[1:]
    fresh = {k: {} for k in ORDER}   # key -> { 'YYYY-M-D': row }
    for m in block.finditer(text):
        raw = m.group(1).strip()
        key = TYPES.get(raw.lower() if raw.lower() == 'vip' else raw)
        if not key:
            continue
        d, mo, y = near(m.start()); y = y + 2500 if y < 100 else y; ce = y - 543
        row = {'ts': ts_utc(ce, mo, d), 'top': int(m.group(3)), 'bottom': int(m.group(4)), 'b3': m.group(2)}
        fresh[key][f'{ce}-{mo}-{d}'] = row
    return fresh

def ymd(ts):
    d = datetime.datetime.utcfromtimestamp(ts / 1000)
    return f'{d.year}-{d.month}-{d.day}'

# ----- merge กับของเดิม (สะสม) -----
store_path = os.path.join(OUT, 'hanoi_history.json')
old = {}
if os.path.exists(store_path):
    try: old = json.load(open(store_path, encoding='utf-8'))
    except Exception: old = {}

fresh = scrape()
merged = {}
for key in ORDER:
    byday = {ymd(r['ts']): r for r in old.get(key, [])}
    byday.update(fresh.get(key, {}))
    merged[key] = sorted(byday.values(), key=lambda r: r['ts'])
    print(f"{NAMES[key]}: {len(merged[key])} งวด")

# ----- เขียนไฟล์ (app ใช้ top/bottom เท่านั้น) -----
app = {k: [{'ts': r['ts'], 'top': r['top'], 'bottom': r['bottom']} for r in v] for k, v in merged.items()}
json.dump(app, open(os.path.join(OUT, 'hanoi_history.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
open(os.path.join(OUT, 'hanoi_history.js'), 'w', encoding='utf-8').write(
    'window.HANOI_HISTORY=' + json.dumps(app, ensure_ascii=False, separators=(',', ':')) + ';')
print("เขียน hanoi_history.json / .js แล้ว")

# ----- CSV รวมทุกประเภท (Google Sheet) -----
def thaidate(ts):
    d = datetime.datetime.utcfromtimestamp(ts / 1000)
    return f'{d.day} {TM[d.month-1]} {d.year+543}'
rows = []
for key in ORDER:
    for r in merged[key]:
        rows.append((r['ts'], NAMES[key], thaidate(r['ts']), r.get('b3', ''), f"{r['top']:02d}", f"{r['bottom']:02d}"))
rows.sort(key=lambda x: (x[0], x[1]))
with open(os.path.join(OUT, 'hanoi_history.csv'), 'w', encoding='utf-8', newline='') as f:
    f.write('วันที่,ประเภท,3 ตัวบน,2 ตัวบน,2 ตัวล่าง\n')
    for _, name, td, b3, top, bot in rows:
        f.write(f'{td},{name},{b3},{top},{bot}\n')
print("เขียน hanoi_history.csv แล้ว")

# ----- xlsx (ชีตเดียว) -----
try:
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'หวยฮานอย'
    ws.append(['วันที่', 'ประเภท', '3 ตัวบน', '2 ตัวบน', '2 ตัวล่าง'])
    for _, name, td, b3, top, bot in rows:
        ws.append([td, name, b3, top, bot])
    for col, w in zip('ABCDE', [16, 16, 10, 10, 10]):
        ws.column_dimensions[col].width = w
    wb.save(os.path.join(OUT, 'hanoi_history.xlsx'))
    print("เขียน hanoi_history.xlsx แล้ว")
except Exception as e:
    print("ข้าม xlsx:", e)
