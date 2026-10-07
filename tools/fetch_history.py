#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ดึงผลหวยลาว (ลาวพัฒนา) แล้ว "สะสม" ลง lao_history.json / .js / .csv / .xlsx

แหล่ง: Sanook (หน้าแยกรายวัน) + สยามรัฐ + ข่าวสด (ตรวจเทียบ) — ฟรีทั้งหมด
  - งวดที่เก็บแล้วไม่ถูกลบ (ของเดิมดึงใหม่ทั้งหมดทุกคืน หน้าไหนโหลดพลาด งวดนั้นหายเงียบ)
  - แหล่งเลขไม่ตรงกัน → ใช้เสียงข้างมาก (2 ใน 3) ถ้าตัดสินไม่ได้ → ไม่บันทึก/ไม่ทับ แล้วแจ้งเตือน
  - กติกา: เลข 4 ตัว = 4 ตัวท้ายของเลข 6 ตัว, บน = 2 ตัวท้าย, ล่าง = 2 ตัวหน้าของเลข 4 ตัว

ใช้:
  python tools/fetch_history.py          # รายวัน: ตรวจย้อนหลัง 21 วัน
  python tools/fetch_history.py --full   # สแกนตั้งแต่ 1 ม.ค. 2568 เติมงวดที่ขาด + เทียบสยามรัฐทุกหน้า
"""
import sys, datetime, concurrent.futures
from lotto_common import (load_json, write_json_js, write_csv, write_xlsx, date_of, ts_of,
                          thai_date, today_th, resolve, src_label, alert, SRC_NAMES)
from sources import sanook_lao, siamrath_index, siamrath_lao, khaosod_index, khaosod_lao

START = datetime.date(2025, 1, 1)
FULL = '--full' in sys.argv
WINDOW = 21
SIAM_PAGES = 80 if FULL else 3
KHAOSOD_PAGES = 40 if FULL else 1

# ---- ของเดิม: เลข 4 ตัว = ล่าง×100 + บน (ย้อนกลับได้พอดี) ----
store = {}
for r in load_json('lao_history.json', []):
    store[date_of(r['ts'])] = {'val': f"{r['bottom']:02d}{r['top']:02d}", 'src': r.get('src') or ['sanook']}
before = len(store)

end = today_th()
start = START if FULL else end - datetime.timedelta(days=WINDOW)
fresh = {}

# ---- Sanook: เฉพาะจันทร์-ศุกร์ (วันที่ไม่มีงวดจะได้ None) ----
days = [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]
days = [d for d in days if d.weekday() <= 4]
def one(d):
    try: return d, sanook_lao(d)
    except Exception: return d, 'ERR'
errors = 0
print(f"Sanook: ตรวจ {len(days)} วันทำการ ({start} ถึง {end}) ...")
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    for d, v in ex.map(one, days):
        if v == 'ERR': errors += 1
        elif v: fresh.setdefault(d, {})['sanook'] = v
print(f"  พบผล {sum('sanook' in v for v in fresh.values())} งวด • โหลดไม่ได้ {errors} หน้า")
if days and errors > len(days) / 2:
    alert(f'หวยลาว: โหลดหน้า Sanook ไม่ได้ {errors}/{len(days)} หน้า — เว็บอาจล่มหรือบล็อก')
elif len(days) >= 5 and not any('sanook' in v for v in fresh.values()):
    alert('หวยลาว: อ่านผลจาก Sanook ไม่ได้เลย — หน้าเว็บอาจเปลี่ยนรูปแบบ (แก้ sanook_lao ใน tools/sources.py)')

# ---- สยามรัฐ + ข่าวสด (วันที่ในหัวข่าวกับในเนื้อข่าวต้องตรงกัน ไม่งั้นข้าม) ----
def collect(name, items, parse):
    def one(item):
        try: return item[0], parse(item[1])
        except Exception: return item[0], None
    got = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for title_d, r in ex.map(one, items):
            if r and r[0] == title_d:
                fresh.setdefault(r[0], {})[name] = r[1]; got += 1
    print(f"{SRC_NAMES[name]}: {len(items)} บทความ • อ่านผลได้ {got}")
    if not got:
        alert(f'หวยลาว: อ่านผลจาก {SRC_NAMES[name]} ไม่ได้เลย — เว็บอาจล่มหรือเปลี่ยนรูปแบบ (แก้ใน tools/sources.py)')

collect('siamrath', [(d, url) for kind, d, url in siamrath_index(SIAM_PAGES) if kind == 'lao' and d >= start], siamrath_lao)
collect('khaosod', [(d, url) for d, url in khaosod_index(KHAOSOD_PAGES) if d >= start], khaosod_lao)

# ---- รวม: สะสม + ตัดสินจากหลายแหล่ง ----
added = fixed = 0
for d in sorted(set(store) | set(fresh)):
    old, age = store.get(d), (end - d).days
    new = resolve(f'หวยลาว {thai_date(d)}', old, fresh.get(d, {}),
                  pending_ok=age <= 3, alert_new=age <= WINDOW)
    if new is None: continue
    if old is None: added += 1
    elif new['val'] != old['val']: fixed += 1
    store[d] = new
assert len(store) >= before, 'งวดหาย — ไม่ควรเกิด'

# ---- เขียนไฟล์ ----
rows = [(d, store[d]) for d in sorted(store)]
app = [{'ts': ts_of(d), 'top': int(s['val'][2:]), 'bottom': int(s['val'][:2]), 'src': s['src']} for d, s in rows]
write_json_js('lao_history', 'LAO_HISTORY', app)
table = [(thai_date(d), s['val'], s['val'][2:], s['val'][:2], src_label(s['src'])) for d, s in rows]
header = ['วันที่', 'เลขท้าย 4 ตัว', '2 ตัวบน', '2 ตัวล่าง', 'แหล่งที่ยืนยัน']
write_csv('lao_history.csv', header, table)
write_xlsx('lao_history.xlsx', 'หวยลาว', header, table, [18, 14, 10, 10, 20])

two = sum(len(s['src']) >= 2 for _, s in rows)
print(f"หวยลาว: {len(rows)} งวด (เพิ่มใหม่ {added}, แก้ไข {fixed}) • ยืนยัน 2 แหล่ง {two} งวด")
if rows:
    print(f"ช่วงข้อมูล: {rows[0][0]} ถึง {rows[-1][0]}")
