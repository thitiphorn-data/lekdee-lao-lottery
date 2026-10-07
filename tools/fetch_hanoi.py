#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ดึงผลหวยฮานอย 4 ประเภท แล้ว "สะสม" ลง hanoi_history.json / .js / .csv / .xlsx

  ฮานอยปกติ (18:30)  = หวยทางการของเวียดนาม (XSMB) → Minh Ngọc + xoso.com.vn
                       ทั้งสองเว็บตรงกัน = ผลทางการ ชนะค่าที่เก็บไว้เสมอ (ใช้แก้งวดที่ Sanook พิมพ์ผิด)
  เฉพาะกิจ (16:30) / พิเศษ (17:30) / VIP (19:30) = ไม่ใช่หวยทางการ ไม่มีแหล่งกลาง
                       → เว็บข่าวไทย 3 เว็บ: Sanook + สยามรัฐ + บ้านกีฬา แล้วใช้เสียงข้างมาก
                       (วัดจากฮานอยปกติ: แต่ละเว็บพิมพ์ผิดราว 2-3% แต่ผิดไม่ซ้ำงวดกัน)
  กติกา: 3 ตัวบน/2 ตัวบน = ท้ายรางวัลพิเศษ (ĐB), 2 ตัวล่าง = 2 ตัวท้ายรางวัลที่ 1 (G1)

  - งวดที่เก็บแล้วไม่ถูกลบ, แหล่งเลขเสมอกัน (1 ต่อ 1) → ไม่ทับ แล้วแจ้งเตือน
  - Sanook เก็บย้อนหลังแค่ ~5 วัน ถ้าระบบค้างนานกว่านั้น ใช้ --full กู้จากสยามรัฐ/บ้านกีฬาได้

ใช้:
  python tools/fetch_hanoi.py          # รายวัน: ย้อนหลังราว 1-3 สัปดาห์จากทุกแหล่ง
  python tools/fetch_hanoi.py --full   # ย้อนถึง 1 ม.ค. 2568 ทุกแหล่ง + กู้ 3 ตัวบนจากประวัติ git
"""
import sys, datetime, subprocess, concurrent.futures
from lotto_common import (ROOT, load_json, write_json_js, write_csv, write_xlsx, date_of, ts_of,
                          thai_date, today_th, resolve, src_label, alert, SRC_NAMES)
from sources import (HANOI_KEYS, sanook_hanoi, minhngoc_xsmb, xosocomvn_xsmb, xsmb_value,
                     siamrath_index, siamrath_hanoi, bankeela_hanoi)

START = datetime.date(2025, 1, 1)
FULL = '--full' in sys.argv
WINDOW = 7
SIAM_PAGES = 80 if FULL else 3
BANKEELA = (10, 100) if FULL else (1, 20)   # (จำนวนหน้า, บทความต่อหน้า)
NAMES = {'hanoi': 'ฮานอย', 'hanoiSpecial': 'ฮานอยพิเศษ', 'hanoiVip': 'ฮานอย VIP', 'hanoiTask': 'ฮานอยเฉพาะกิจ'}
OFFICIAL = ('minhngoc', 'xoso')

# ---- ของเดิม: val = (3 ตัวบน, บน, ล่าง) — ไฟล์รุ่นเก่าไม่มี 3 ตัวบน (b3 = '') ----
store = {k: {} for k in HANOI_KEYS}
for k in HANOI_KEYS:
    for r in load_json('hanoi_history.json', {}).get(k, []):
        store[k][date_of(r['ts'])] = {'val': (r.get('b3', ''), r['top'], r['bottom']),
                                      'src': r.get('src') or ['sanook']}
before = {k: len(v) for k, v in store.items()}
fresh = {k: {} for k in HANOI_KEYS}   # key -> date -> {แหล่ง: val}
end = today_th()

# ---- ฮานอยปกติ: ผลทางการ XSMB ----
start = START if FULL else end - datetime.timedelta(days=WINDOW)
days = [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]
def one_xsmb(d):
    got = {}
    for name, fn in (('minhngoc', minhngoc_xsmb), ('xoso', xosocomvn_xsmb)):
        try:
            r = fn(d)
            if r: got[name] = xsmb_value(*r)
        except Exception:
            pass
    return d, got
print(f"XSMB: ตรวจ {len(days)} วัน ({start} ถึง {end}) ...")
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
    for d, got in ex.map(one_xsmb, days):
        if got: fresh['hanoi'][d] = got
print(f"  ได้ผล {len(fresh['hanoi'])} วัน")
if not fresh['hanoi']:
    alert('ฮานอยปกติ: อ่านผล XSMB ไม่ได้เลย — Minh Ngọc / xoso.com.vn อาจล่มหรือเปลี่ยนรูปแบบ')

# ---- เว็บข่าวไทย: ใช้กับเฉพาะกิจ/พิเศษ/VIP (ฮานอยปกติใช้ผลทางการเท่านั้น) ----
def add_news(name, by_date):
    for d, by in by_date.items():
        for k, v in by.items():
            if k != 'hanoi':
                fresh[k].setdefault(d, {})[name] = v
    print(f"{SRC_NAMES[name]}: {len(by_date)} วัน")
    if not by_date:
        alert(f'ฮานอย: อ่านผลจาก {SRC_NAMES[name]} ไม่ได้เลย — เว็บอาจล่มหรือเปลี่ยนรูปแบบ (แก้ใน tools/sources.py)')

try:
    add_news('sanook', sanook_hanoi())
except Exception as e:
    alert(f'ฮานอย: โหลดหน้า Sanook ไม่ได้ ({e})')
add_news('bankeela', bankeela_hanoi(*BANKEELA))

# ---- สยามรัฐ ----
items = [(d, url) for kind, d, url in siamrath_index(SIAM_PAGES) if kind == 'hanoi']
def one_siam(item):
    try: return item[0], siamrath_hanoi(item[1])
    except Exception: return item[0], None
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
    siam = {r[0]: r[1] for title_d, r in ex.map(one_siam, items) if r and r[0] == title_d}
add_news('siamrath', siam)

# ---- กู้ 3 ตัวบนของงวดเก่าจากประวัติ git (ไฟล์ CSV เคยมีค่าตอนงวดนั้นยังอยู่บนหน้า Sanook) ----
def recover_b3():
    try:
        commits = subprocess.run(['git', 'log', '--format=%h', '--', 'hanoi_history.csv'],
                                 cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    except Exception:
        print("ข้ามการกู้ 3 ตัวบน: ไม่มีประวัติ git"); return
    key_of = {v: k for k, v in NAMES.items()}
    th_to_date = {thai_date(d): d for k in HANOI_KEYS for d in store[k]}
    n = 0
    for c in commits:
        csv = subprocess.run(['git', 'show', f'{c}:hanoi_history.csv'], cwd=ROOT, capture_output=True).stdout.decode('utf-8')
        for line in csv.splitlines()[1:]:
            p = line.split(',')
            if len(p) < 5 or not p[2]: continue
            k, d = key_of.get(p[1]), th_to_date.get(p[0])
            s = store.get(k, {}).get(d) if k else None
            if s and s['val'][0] == '' and p[2][-2:] == f"{s['val'][1]:02d}" and int(p[4]) == s['val'][2]:
                s['val'] = (p[2],) + s['val'][1:]; n += 1
    print(f"กู้ 3 ตัวบนจากประวัติ git ได้ {n} งวด")
if FULL:
    recover_b3()

# ---- รวม: สะสม + ตัดสินจากหลายแหล่ง ----
summary = []
for k in HANOI_KEYS:
    added = fixed = 0
    for d in sorted(set(store[k]) | set(fresh[k])):
        old, cand = store[k].get(d), fresh[k].get(d, {})
        # ของเดิมที่ไม่มี 3 ตัวบน: ถ้าบน/ล่างตรงกับแหล่งใหม่ ให้เติม 3 ตัวบนจากแหล่งใหม่ (ไม่นับว่าขัดกัน)
        if old and old['val'][0] == '':
            fill = {v for v in cand.values() if v[1:] == old['val'][1:]}
            if len(fill) == 1:
                old = {'val': fill.pop(), 'src': old['src']}
        age = (end - d).days
        new = resolve(f'{NAMES[k]} {thai_date(d)}', old, cand, trusted=OFFICIAL if k == 'hanoi' else (),
                      pending_ok=age <= 3, alert_new=age <= 21)
        if new is None: continue
        if d not in store[k]: added += 1
        elif new['val'][1:] != store[k][d]['val'][1:]: fixed += 1
        store[k][d] = new
    assert len(store[k]) >= before[k], 'งวดหาย — ไม่ควรเกิด'
    two = sum(len(s['src']) >= 2 for s in store[k].values())
    summary.append(f"{NAMES[k]}: {len(store[k])} งวด (เพิ่มใหม่ {added}, แก้ไข {fixed}) • ยืนยัน 2 แหล่ง {two} งวด")

# ---- เขียนไฟล์ (แอปใช้ top/bottom — b3/src เก็บไว้ให้รอบถัดไปและ CSV) ----
app = {k: [{'ts': ts_of(d), 'top': s['val'][1], 'bottom': s['val'][2], 'b3': s['val'][0], 'src': s['src']}
           for d, s in sorted(store[k].items())] for k in HANOI_KEYS}
write_json_js('hanoi_history', 'HANOI_HISTORY', app)
rows = sorted(((d, NAMES[k], s) for k in HANOI_KEYS for d, s in store[k].items()), key=lambda x: (x[0], x[1]))
table = [(thai_date(d), name, s['val'][0], f"{s['val'][1]:02d}", f"{s['val'][2]:02d}", src_label(s['src']))
         for d, name, s in rows]
header = ['วันที่', 'ประเภท', '3 ตัวบน', '2 ตัวบน', '2 ตัวล่าง', 'แหล่งที่ยืนยัน']
write_csv('hanoi_history.csv', header, table)
write_xlsx('hanoi_history.xlsx', 'หวยฮานอย', header, table, [16, 16, 10, 10, 10, 24])
print("\n".join(summary))
