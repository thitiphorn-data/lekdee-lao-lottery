#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ตรวจว่าข้อมูลยัง "สด" อยู่ไหม — กันกรณีระบบรันผ่านแต่ดึงข้อมูลใหม่ไม่ได้ (พังเงียบ)

สำคัญ: หน้าต้นทางฮานอยเก็บย้อนหลังแค่ ~4 วัน ถ้าปล่อยให้ค้างนานกว่านั้น
ข้อมูลช่วงที่ขาดจะหายถาวร กู้ไม่ได้ — จึงต้องเตือนตั้งแต่เนิ่นๆ

exit 0 = ปกติ, exit 1 = ข้อมูลค้าง (ให้ workflow แจ้งเตือน)
ใช้: python tools/check_fresh.py
"""
import json, os, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = datetime.datetime.now(datetime.timezone.utc).date()

# หวยลาวออก จ-ศ (เสาร์-อาทิตย์เว้น) จึงยอมให้ห่างได้มากกว่า
# ฮานอยออกทุกวัน ถ้าค้างเกิน 2 วันถือว่าผิดปกติ
LIMITS = {'lao': 5, 'hanoi': 3, 'hanoiSpecial': 3, 'hanoiVip': 3, 'hanoiTask': 3}

def latest(draws):
    if not draws:
        return None
    ts = max(d['ts'] for d in draws)
    return datetime.datetime.fromtimestamp(ts / 1000, datetime.timezone.utc).date()

def load(name):
    path = os.path.join(ROOT, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)

problems, report = [], []

lao = load('lao_history.json')
hanoi = load('hanoi_history.json') or {}
sets = {'lao': lao if lao is not None else []}
for k, v in hanoi.items():
    sets[k] = v

for key, draws in sets.items():
    last = latest(draws)
    limit = LIMITS.get(key, 3)
    if last is None:
        problems.append(f"- **{key}**: ไม่มีข้อมูลเลย")
        continue
    age = (TODAY - last).days
    mark = "OK " if age <= limit else "STALE"
    report.append(f"{mark} {key:14s} {len(draws):5d} งวด  ล่าสุด {last} (ค้าง {age} วัน / จำกัด {limit})")
    if age > limit:
        problems.append(f"- **{key}**: ล่าสุด {last} — ค้างมาแล้ว {age} วัน (เกินเกณฑ์ {limit} วัน)")

print("\n".join(report))

if problems:
    print("\n=== พบข้อมูลค้าง ===")
    print("\n".join(problems))
    # ส่งต่อให้ workflow เอาไปใส่ใน issue
    summary = "ข้อมูลค้าง ไม่ได้อัปเดตตามกำหนด:\n" + "\n".join(problems)
    gh_out = os.environ.get('GITHUB_OUTPUT')
    if gh_out:
        with open(gh_out, 'a', encoding='utf-8') as f:
            f.write("stale<<EOF\n" + summary + "\nEOF\n")
    sys.exit(1)

print("\nข้อมูลสดทั้งหมด")
