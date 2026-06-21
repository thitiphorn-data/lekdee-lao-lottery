#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ดึงผลหวยลาว (รายวัน จันทร์-ศุกร์) จาก Sanook ตั้งแต่ 1 ม.ค. 2568 ถึงปัจจุบัน
แล้วบันทึกเป็น lao_history.json (ให้เว็บแอปโหลด) + lao_history.xlsx (ให้คนอ่าน)

รันแบบ server-side ตรงๆ ไม่ผ่าน CORS proxy จึงไม่โดน rate-limit เหมือนในเบราว์เซอร์
ใช้: python tools/fetch_history.py
"""
import urllib.request, re, json, datetime, concurrent.futures, time, sys, os

HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START = datetime.date(2025, 1, 1)
END = datetime.date.today()

def slug_of(d):
    return f"{d.day:02d}{d.month:02d}{d.year + 543}"

def fetch_one(d):
    slug = slug_of(d)
    url = f"https://www.sanook.com/news/laolotto/{slug}/"
    for attempt in range(3):
        try:
            html = urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=20).read().decode('utf-8', 'ignore')
            m = re.search(r'laoLotto\(\{\\"date\\":\\"' + slug + r'\\"\}\)\.prizeResult":\{"last4Prize":"(\d{4})"', html)
            if m:
                n4 = int(m.group(1))
                return {'date': d, 'last4': m.group(1), 'top': n4 % 100, 'bottom': n4 // 100}
            return None  # ไม่มีงวด (วันหยุด/ยังไม่ออก)
        except Exception:
            time.sleep(0.6 * (attempt + 1))
    return 'ERR'

# รวบรวมเฉพาะวันจันทร์-ศุกร์
days = []
d = START
while d <= END:
    if d.weekday() <= 4:  # 0=จันทร์ .. 4=ศุกร์
        days.append(d)
    d += datetime.timedelta(days=1)

print(f"สแกน {len(days)} วันทำการ (จ-ศ) ตั้งแต่ {START} ถึง {END} ...")
results, errors, done = {}, 0, 0
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(fetch_one, d): d for d in days}
    for fut in concurrent.futures.as_completed(futs):
        d = futs[fut]; r = fut.result(); done += 1
        if r == 'ERR':
            errors += 1
        elif r:
            results[d] = r
        if done % 40 == 0:
            print(f"  {done}/{len(days)} • พบผล {len(results)} งวด • error {errors}", flush=True)

rows = [results[d] for d in sorted(results)]
print(f"เสร็จ: พบผลจริง {len(rows)} งวด, error {errors}")

# ---- lao_history.json (สำหรับเว็บแอป) ----
data = [{'ts': int(datetime.datetime(r['date'].year, r['date'].month, r['date'].day).timestamp() * 1000),
         'top': r['top'], 'bottom': r['bottom']} for r in rows]
with open(os.path.join(OUT_DIR, 'lao_history.json'), 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
print("เขียน lao_history.json แล้ว")

# ---- lao_history.js (ให้เว็บแอป include ได้ทั้งจากไฟล์ file:// และ https) ----
with open(os.path.join(OUT_DIR, 'lao_history.js'), 'w', encoding='utf-8') as f:
    f.write('window.LAO_HISTORY=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';')
print("เขียน lao_history.js แล้ว")

# ---- lao_history.xlsx (สำหรับคนอ่าน) ----
try:
    import openpyxl
    TM = ['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.']
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'หวยลาว'
    ws.append(['วันที่', 'เลขท้าย 4 ตัว', '2 ตัวบน', '2 ตัวล่าง'])
    for r in rows:
        dd = r['date']
        ws.append([f"{dd.day} {TM[dd.month-1]} {dd.year+543}", r['last4'], f"{r['top']:02d}", f"{r['bottom']:02d}"])
    for col, w in zip('ABCD', [18, 14, 10, 10]):
        ws.column_dimensions[col].width = w
    wb.save(os.path.join(OUT_DIR, 'lao_history.xlsx'))
    print("เขียน lao_history.xlsx แล้ว")
except Exception as e:
    print("ข้าม xlsx:", e)

if rows:
    print(f"ช่วงข้อมูล: {rows[0]['date']} ถึง {rows[-1]['date']}")
