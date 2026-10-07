#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ตรวจข้อมูลก่อน commit — ด่านสุดท้ายกันข้อมูลเสียขึ้นเว็บ

  1. ห้ามงวดหาย: ทุกวันที่ที่มีในเวอร์ชันล่าสุดบน git (HEAD) ต้องยังอยู่ครบ
  2. ค่าต้องสมเหตุสมผล: เลข 00-99, วันที่ไม่ซ้ำ, ไม่มีวันในอนาคต, 3 ตัวบนลงท้ายด้วย 2 ตัวบน
  3. แสดงงวดที่ค่าเปลี่ยนจากเดิม (ให้เห็นใน log ว่าแก้อะไรไป)

exit 0 = ผ่าน, exit 1 = ไม่ผ่าน (workflow จะไม่ commit แล้วแจ้งเตือน)
ใช้: python tools/check_data.py
"""
import json, subprocess, sys, datetime
from lotto_common import ROOT, load_json, date_of, today_th, thai_date, alert

problems = []

def head_version(name):
    try:
        out = subprocess.run(['git', 'show', f'HEAD:{name}'], cwd=ROOT, capture_output=True, check=True).stdout
        return json.loads(out.decode('utf-8'))
    except Exception:
        return None

def check(label, cur, old):
    days = [date_of(r['ts']) for r in cur]
    if len(days) != len(set(days)):
        problems.append(f'{label}: มีวันที่ซ้ำ')
    limit = today_th() + datetime.timedelta(days=1)
    for r in cur:
        d = date_of(r['ts'])
        if not (0 <= r['top'] <= 99 and 0 <= r['bottom'] <= 99):
            problems.append(f'{label} {thai_date(d)}: เลขผิดรูปแบบ {r}')
        if d > limit:
            problems.append(f'{label} {thai_date(d)}: เป็นวันในอนาคต')
        b3 = r.get('b3')
        if b3 and (len(b3) != 3 or b3[-2:] != f"{r['top']:02d}"):
            problems.append(f'{label} {thai_date(d)}: 3 ตัวบน {b3} ไม่ลงท้ายด้วย 2 ตัวบน {r["top"]:02d}')
    if old is None:
        return
    now = {date_of(r['ts']): (r['top'], r['bottom']) for r in cur}
    for r in old:
        d = date_of(r['ts'])
        if d not in now:
            problems.append(f'{label} {thai_date(d)}: งวดหายไปจากข้อมูล')
        elif now[d] != (r['top'], r['bottom']):
            print(f"แก้ไข {label} {thai_date(d)}: {r['top']:02d}/{r['bottom']:02d} → {now[d][0]:02d}/{now[d][1]:02d}")
    print(f"{label}: {len(old)} → {len(cur)} งวด")

check('หวยลาว', load_json('lao_history.json', []), head_version('lao_history.json'))
han, han_old = load_json('hanoi_history.json', {}), head_version('hanoi_history.json') or {}
for k in ['hanoi', 'hanoiSpecial', 'hanoiVip', 'hanoiTask']:
    check(k, han.get(k, []), han_old.get(k) if han_old else None)

if problems:
    print("\n=== ข้อมูลไม่ผ่านการตรวจ (ไม่ commit) ===")
    for p in problems:
        alert(p)
    sys.exit(1)
print("ข้อมูลผ่านการตรวจ")
