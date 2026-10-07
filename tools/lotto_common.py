# -*- coding: utf-8 -*-
"""
ของใช้ร่วมกันของสคริปต์ดึงผลหวย: HTTP, แปลงวันที่, อ่าน/เขียนไฟล์, แจ้งเตือน

หลักการเก็บข้อมูล (ใช้ทั้งลาวและฮานอย):
  1. สะสมอย่างเดียว — งวดที่เคยบันทึกแล้วจะไม่ถูกลบ (เว็บต้นทางโหลดพลาดก็ไม่ทำให้งวดหาย)
  2. ทุกงวดจำว่ายืนยันจากแหล่งไหนบ้าง (ฟิลด์ src) — ยิ่งหลายแหล่งตรงกันยิ่งเชื่อถือได้
  3. ถ้าแหล่งข้อมูลให้เลขไม่ตรงกัน → ไม่เดา ไม่ทับของเดิม แต่แจ้งเตือนให้คนตรวจ
"""
import urllib.request, re, html as htmlmod, json, datetime, os, sys, time
from collections import Counter

# console ของ Windows เป็น cp1252 พิมพ์ภาษาไทยแล้ว error — บังคับ UTF-8
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding='utf-8')
    except Exception: pass

HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TM = ['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.']
TM_FULL = ['มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน',
           'กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม']
UTC = datetime.timezone.utc
SRC_NAMES = {'sanook': 'Sanook', 'siamrath': 'สยามรัฐ', 'khaosod': 'ข่าวสด', 'bankeela': 'บ้านกีฬา',
             'minhngoc': 'Minh Ngọc', 'xoso': 'xoso.com.vn'}

def src_label(srcs):
    return '+'.join(SRC_NAMES.get(s, s) for s in srcs)


def http_get(url, tries=3, timeout=25):
    """ดึงหน้าเว็บ (ลองซ้ำ 3 ครั้ง) — ล้มทุกครั้งจะ raise ให้คนเรียกตัดสินใจเอง"""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=HDR)
            return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'ignore')
        except Exception as e:
            last = e
            time.sleep(0.8 * (attempt + 1))
    raise last


def page_text(html):
    """HTML → ข้อความล้วน (ตัด script/style/แท็ก, ยุบช่องว่าง)"""
    html = re.sub(r'(?is)<script.*?</script>|<style.*?</style>', ' ', html)
    return htmlmod.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))).strip()


# ---------- วันที่ ----------
def ts_of(d):
    """เที่ยงคืน UTC ของวันงวด (กำหนดตายตัว เครื่องไหน/CI ได้ค่าตรงกัน — index.html ใช้แบบเดียวกัน)"""
    return int(datetime.datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000)

def date_of(ts):
    return datetime.datetime.fromtimestamp(ts / 1000, UTC).date()

def thai_date(d):
    return f"{d.day} {TM[d.month-1]} {d.year+543}"

def today_th():
    """วันนี้ตามเวลาไทย (CI รันเป็น UTC)"""
    return (datetime.datetime.now(UTC) + datetime.timedelta(hours=7)).date()

def make_date(day, month, year):
    """รับปี 2 หลัก (69) / พ.ศ. (2569) / ค.ศ. (2026) → date หรือ None ถ้าวันที่ไม่มีจริง"""
    year = int(year)
    if year < 100: year += 2500
    if year > 2400: year -= 543
    try: return datetime.date(year, int(month), int(day))
    except ValueError: return None

def thai_month(name):
    """'ต.ค.' / 'ตุลาคม' / 'ต.ค' → 10"""
    n = name.strip().rstrip('.')
    for i, (a, b) in enumerate(zip(TM, TM_FULL)):
        if n == a.rstrip('.') or n == b:
            return i + 1
    return None

DATE_SLASH = re.compile(r'(\d{1,2})/(\d{1,2})/(\d{2,4})')
DATE_THAI = re.compile(r'(\d{1,2})\s*([ก-๙]+\.?[ก-๙]*\.?)\s*(\d{4})')

def find_date(text):
    """หาวันที่แรกในข้อความ รองรับ '6/10/69', '5/10/2569', '6 ตุลาคม 2569', '6 ต.ค.2569'"""
    best = None
    m = DATE_SLASH.search(text)
    if m: best = (m.start(), make_date(*m.groups()))
    for m in DATE_THAI.finditer(text):
        mo = thai_month(m.group(2))
        if mo:
            if best is None or m.start() < best[0]:
                best = (m.start(), make_date(m.group(1), mo, m.group(3)))
            break
    return best[1] if best else None


# ---------- ไฟล์ ----------
def load_json(name, default):
    path = os.path.join(ROOT, name)
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def write_json_js(base, var, data):
    """เขียน <base>.json (เว็บดึงสด) + <base>.js (ใช้ได้แม้เปิดจาก file://)"""
    s = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    with open(os.path.join(ROOT, base + '.json'), 'w', encoding='utf-8') as f:
        f.write(s)
    with open(os.path.join(ROOT, base + '.js'), 'w', encoding='utf-8') as f:
        f.write(f'window.{var}={s};')

def write_csv(name, header, rows):
    """CSV UTF-8 ไม่มี BOM (ให้ Google Sheet ดึงด้วย IMPORTDATA)"""
    with open(os.path.join(ROOT, name), 'w', encoding='utf-8', newline='') as f:
        f.write(','.join(header) + '\n')
        for r in rows:
            f.write(','.join(str(x) for x in r) + '\n')

def write_xlsx(name, sheet, header, rows, widths):
    try:
        import openpyxl
    except ImportError:
        print("ข้าม xlsx: ไม่ได้ติดตั้ง openpyxl")
        return
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = sheet
    ws.append(header)
    for r in rows:
        ws.append(list(r))
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    wb.save(os.path.join(ROOT, name))


# ---------- แจ้งเตือน ----------
_alerts = []

def alert(msg):
    """บันทึกปัญหาที่คนต้องตรวจ — workflow จะเปิด issue จากไฟล์ ALERT_FILE"""
    _alerts.append(msg)
    print('⚠️ ', msg)
    path = os.environ.get('ALERT_FILE')
    if path:
        with open(path, 'a', encoding='utf-8') as f:
            f.write('- ' + msg + '\n')

def alerts():
    return list(_alerts)


# ---------- ตัดสินผลจากหลายแหล่ง ----------
def resolve(label, stored, fresh, trusted=(), min_new=2, pending_ok=False, alert_new=True):
    """
    stored: {'val': ค่า, 'src': [แหล่ง]} หรือ None (งวดที่เก็บไว้แล้ว)
    fresh : {แหล่ง: ค่า} ที่ดึงได้รอบนี้ (แหล่งที่ดึงไม่ได้ไม่ต้องใส่)
    trusted: แหล่งทางการ — ถ้าดึงได้ครบและตรงกันเอง จะชนะทุกแหล่งเสมอ

    แหล่งที่เคยยืนยันค่าที่เก็บไว้ (stored['src']) นับเป็นเสียงด้วย
    เพราะเว็บข่าวเก็บย้อนหลังไม่นาน งวดเก่าจึงมักเหลือแหล่งให้เทียบน้อยลง
      - ทุกเสียงตรงกัน        → บันทึก (รวมรายชื่อแหล่ง)
      - เสียงข้างมากชัดเจน    → ใช้เสียงข้างมาก (เช่น 2 ใน 3 — แต่ละเว็บพิมพ์ผิดราว 2-3% และผิดไม่ซ้ำงวดกัน)
      - เสมอกัน (เช่น 1 ต่อ 1) → ไม่ทับ/ไม่บันทึก แล้วแจ้งเตือนให้คนตรวจ
    min_new: งวดใหม่ต้องมีอย่างน้อยกี่แหล่งที่ตรงกันจึงบันทึก (ยังไม่ถึง = รอรอบหน้า ไม่ใช่ error)
    pending_ok: งวดใหม่ที่ยังสดอยู่ (บางเว็บอาจยังไม่ลงผล) — ถ้าเสมอกันให้รอรอบหน้าแทนการแจ้งเตือน
    alert_new: งวดใหม่ที่เสมอกันให้แจ้งเตือนไหม (งวดเก่ามากที่ย้อนเติมด้วย --full แค่ข้ามไป)
    คืน {'val','src'} ที่ควรบันทึก หรือ None (ยังไม่บันทึก)
    """
    if not fresh:
        return stored
    votes = dict(fresh)
    for s in (stored['src'] if stored else []):
        votes.setdefault(s, stored['val'])
    tally = Counter(votes.values()).most_common()
    detail = ', '.join(f'{s}={v}' for s, v in sorted(votes.items()))
    official = {s: v for s, v in fresh.items() if s in trusted}
    if trusted and len(official) == len(trusted) and len(set(official.values())) == 1:
        best = next(iter(official.values()))
    elif len(tally) > 1 and tally[0][1] == tally[1][1]:
        if stored is None and pending_ok:
            print(f'รอ {label}: แหล่งยังไม่ตรงกัน ({detail}) — รอแหล่งที่สามรอบหน้า')
            return None
        if stored is None and not alert_new:
            print(f'ข้าม {label}: แหล่งไม่ตรงกัน ({detail}) — ไม่บันทึก')
            return None
        alert(f'{label}: แหล่งข้อมูลไม่ตรงกัน ({detail}) — ' +
              ('คงค่าเดิมไว้ รอคนตรวจ' if stored else 'ยังไม่บันทึกงวดนี้'))
        return stored
    else:
        best = tally[0][0]
    if len(tally) > 1:
        print(f'หมายเหตุ {label}: แหล่งไม่ตรงกัน ({detail}) — ใช้ {best}')
    srcs = sorted(s for s, v in votes.items() if v == best)
    if stored is None and len(srcs) < min_new:
        return None
    if stored and stored['val'] != best:
        print(f'แก้ไข {label}: {stored["val"]} → {best}')
    return {'val': best, 'src': srcs}
