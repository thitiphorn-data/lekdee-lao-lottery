# -*- coding: utf-8 -*-
"""
ตัวอ่านผลหวยจากแต่ละเว็บ (ฟรีทั้งหมด ไม่ต้องใช้ API key)

กติกาการตัดเลขแบบไทย
  หวยลาว (ลาวพัฒนา) : ผลออกเป็นเลข 6 ตัว → ใช้ "เลข 4 ตัว" = 4 ตัวท้าย
                       2 ตัวบน = 2 ตัวท้ายของเลข 4 ตัว, 2 ตัวล่าง = 2 ตัวหน้าของเลข 4 ตัว
                       เช่น 564693 → 4 ตัว 4693 → บน 93 ล่าง 46
  ฮานอย (ทุกประเภท)   : กระดานผลแบบ XSMB ของเวียดนาม
                       3 ตัวบน/2 ตัวบน = ท้ายของ "รางวัลพิเศษ" (Đặc biệt / ĐB)
                       2 ตัวล่าง       = 2 ตัวท้ายของ "รางวัลที่ 1" (Giải nhất / G1)
                       เช่น ĐB 12554, G1 26733 → 3 ตัวบน 554, บน 54, ล่าง 33

แหล่งข้อมูล
  ฮานอยปกติ  = หวยทางการของเวียดนาม (XSMB / Xổ số Miền Bắc) → ดึงจากเว็บผลเวียดนามโดยตรง
               Minh Ngọc + xoso.com.vn (มีหน้าแยกรายวัน ย้อนหลังได้หลายปี)
  ฮานอยเฉพาะกิจ (16:30) / พิเศษ (17:30) / VIP (19:30) = ไม่ใช่หวยทางการ ไม่มีแหล่งกลาง
               → ใช้เว็บข่าวไทย 2 เว็บเทียบกัน: Sanook + สยามรัฐ
  หวยลาว     → Sanook (หน้าแยกรายวัน) + สยามรัฐ
"""
import re
from lotto_common import http_get, page_text, find_date, make_date

HANOI_KEYS = ['hanoi', 'hanoiSpecial', 'hanoiVip', 'hanoiTask']


def hanoi_key(name):
    """ชื่อประเภทในบทความข่าว → key ที่แอปใช้"""
    n = name.strip().lower()
    if 'เฉพาะกิจ' in n: return 'hanoiTask'
    if 'พิเศษ' in n: return 'hanoiSpecial'
    if 'vip' in n or 'วีไอพี' in n: return 'hanoiVip'
    if 'ปกติ' in n or n == '': return 'hanoi'
    return None   # ฮานอยประเภทอื่น (กาชาด/สามัคคี/ฯลฯ) — แอปไม่ได้ใช้


def xsmb_value(db, g1):
    """รางวัลพิเศษ + รางวัลที่ 1 → (3 ตัวบน, 2 ตัวบน, 2 ตัวล่าง)"""
    return (db[-3:], int(db[-2:]), int(g1[-2:]))


# =====================================================================
# หวยลาว
# =====================================================================
def sanook_lao(d):
    """เลข 4 ตัวของงวดวันที่ d จาก Sanook ('4693') — None = ไม่มีงวด/ยังไม่ลงผล"""
    slug = f"{d.day:02d}{d.month:02d}{d.year + 543}"
    html = http_get(f"https://www.sanook.com/news/laolotto/{slug}/", timeout=20)
    m = re.search(r'laoLotto\(\{\\"date\\":\\"' + slug + r'\\"\}\)\.prizeResult":\{"last4Prize":"(\d{4})"', html)
    return m.group(1) if m else None


# =====================================================================
# ฮานอย — Sanook (หน้าเดียว มีย้อนหลัง ~5 วัน × 4 ประเภท)
# =====================================================================
SANOOK_HANOI_URL = 'https://www.sanook.com/news/9837690/'
HANOI_BLOCK = re.compile(
    r'ผลหวยฮานอย\s*([ก-๙A-Za-z ]{0,14}?)\s*'
    r'(?:เลข\s*4\s*ตัว\s*:?\s*(\d{4})\s*)?'
    r'เลข\s*3\s*ตัวบน\s*:?\s*(\d{3})\s*'
    r'เลข\s*2\s*ตัวบน\s*:?\s*(\d{2})\s*'
    r'เลข\s*2\s*ตัวล่าง\s*:?\s*(\d{2})\b')

def parse_hanoi_blocks(text):
    """ข้อความช่วงหนึ่ง → {key: (3 ตัวบน, บน, ล่าง)} (ข้ามบล็อกที่เลขขัดกันเอง)"""
    out = {}
    for m in HANOI_BLOCK.finditer(text):
        key = hanoi_key(m.group(1))
        if not key or key in out:
            continue
        n4, b3, top, bot = m.group(2), m.group(3), m.group(4), m.group(5)
        if b3[-2:] != top or (n4 and n4[-3:] != b3):
            continue  # บทความพิมพ์ผิด (3 ตัวบนไม่ลงท้ายด้วย 2 ตัวบน) — ไม่เอา
        out[key] = (b3, int(top), int(bot))
    return out

def sanook_hanoi():
    """
    คืน {date: {key: (b3, top, bottom)}}
    แบ่งหน้าตามหัวข้อ <h2>/<h3> ที่มีวันที่ — ผลใต้หัวข้อไหนก็เป็นของวันนั้น
    (ของเดิมเดาวันจาก "หัวข้อที่อยู่ใกล้สุด" ทำให้ผลวันล่าสุดไปลงผิดวันได้)
    หัวข้อวันล่าสุดเขียน '6 ตุลาคม 2569' ส่วนวันก่อนหน้าเขียน '5/10/2569' — รองรับทั้งสองแบบ
    """
    html = http_get(SANOOK_HANOI_URL)
    heads = [(m.start(), m.end(), page_text(m.group(1)))
             for m in re.finditer(r'(?is)<h[1-4][^>]*>(.*?)</h[1-4]>', html)]
    out = {}
    for i, (s, e, title) in enumerate(heads):
        if 'ฮานอย' not in title:
            continue
        d = find_date(title)
        if not d:
            continue
        end = heads[i + 1][0] if i + 1 < len(heads) else len(html)
        blocks = parse_hanoi_blocks(page_text(html[e:end]))
        if blocks:
            out.setdefault(d, {}).update(blocks)
    return out


# =====================================================================
# ฮานอยปกติ — ผลทางการ XSMB
# =====================================================================
def minhngoc_xsmb(d):
    """(ĐB, G1) จาก Minh Ngọc — None = วันนั้นไม่มีออก (เช่น ช่วงตรุษเวียดนาม)"""
    html = http_get(f'https://www.minhngoc.net.vn/ket-qua-xo-so/mien-bac/{d:%d-%m-%Y}.html')
    text = page_text(html)
    k = text.find(f'Ngày: {d:%d/%m/%Y}')
    if k < 0:
        return None
    nxt = text.find('Ngày: ', k + 10)
    seg = text[k: nxt if nxt > 0 else len(text)]
    m = re.search(r'ĐB\s+(\d{5})\s+Giải nhất\s+(\d{5})', seg)
    return (m.group(1), m.group(2)) if m else None

def xosocomvn_xsmb(d):
    """(ĐB, G1) จาก xoso.com.vn — None = วันนั้นไม่มีออก"""
    html = http_get(f'https://xoso.com.vn/xsmb-{d:%d-%m-%Y}.html')
    text = page_text(html)
    k = text.find(f'Xổ số miền Bắc ngày {d:%d-%m-%Y}')
    if k < 0:
        return None
    m = re.search(r'ĐB\s+(\d{5})\s+1\s+(\d{5})\s+2\s', text[k:k + 600])
    return (m.group(1), m.group(2)) if m else None


# =====================================================================
# สยามรัฐ — แหล่งที่สองไว้ตรวจเทียบ (ลาว + ฮานอย 4 ประเภท)
# =====================================================================
def siamrath_index(pages):
    """
    ไล่หน้ารวม /lottery → [(kind, date, url)] kind = 'lao' | 'hanoi'
    เลือกเฉพาะบทความ "ผลประจำวันที่" (ข้ามบทความสถิติ/เลขเด็ด)
    """
    found = {}
    for p in range(1, pages + 1):
        try:
            html = http_get(f'https://siamrath.co.th/lottery?page={p}')
        except Exception:
            break
        items = re.findall(r'<a[^>]+href="(?:https://siamrath\.co\.th)?(/lottery/\d+)"[^>]*>(.*?)</a>', html, re.S)
        if not items:
            break
        for href, inner in items:
            title = page_text(inner)
            if 'ประจำวันที่' not in title or 'สถิติ' in title or 'เลขเด็ด' in title:
                continue
            kind = 'hanoi' if 'ฮานอย' in title else 'lao' if 'ลาว' in title else None
            m = re.search(r'ประจำวันที่\s*(\d{1,2})/(\d{1,2})/(\d{2,4})', title)
            d = make_date(*m.groups()) if m else None
            if kind and d:
                found[href] = (kind, d, 'https://siamrath.co.th' + href)
    return list(found.values())

def _siamrath_body(url):
    """ข้อความเนื้อข่าว + วันที่งวดที่ระบุในเนื้อข่าว ('ประจำวันที่ 6 ต.ค.2569')"""
    text = page_text(http_get(url))
    k = text.find('รายงานผลหวย')
    body = text[k:] if k >= 0 else text
    m = re.search(r'ประจำวันที่\s*([^ ]+\s*[^ ]*\s*\d{4})', body)
    return body, (find_date(m.group(1)) if m else None)

def siamrath_lao(url):
    """→ (date, เลข 4 ตัว) หรือ None"""
    body, d = _siamrath_body(url)
    # รูปแบบไม่คงที่: 'เลข 4 ตัว 4693' / 'เลข 4 ตัว : 4693' / 'หวยลาว 4 ตัว : 4693'
    m = re.search(r'(?:เลข\s*)?4\s*ตัว\s*:?\s*(\d{4})\b', body)
    m6 = re.search(r'(?:เลข\s*)?6\s*ตัว\s*:?\s*(\d{6})\b', body)
    if not (d and m):
        return None
    if m6 and m6.group(1)[-4:] != m.group(1):
        return None  # เลข 6 ตัวกับ 4 ตัวขัดกันเอง — ไม่เอา
    return d, m.group(1)

# =====================================================================
# บ้านกีฬา — แหล่งที่สามของฮานอย (WordPress API ค้นบทความ + เนื้อหาได้ทีละ 100)
# =====================================================================
def bankeela_hanoi(pages, per_page=100):
    """→ {date: {key: (b3, top, bottom)}} จากบทความ 'ตรวจหวยฮานอยวันนี้ งวดประจำวัน…'"""
    import json, urllib.parse
    q = urllib.parse.quote('ตรวจหวยฮานอยวันนี้')
    out = {}
    for p in range(1, pages + 1):
        try:
            raw = http_get(f'https://www.bankeela.info/wp-json/wp/v2/posts?search={q}'
                           f'&per_page={per_page}&page={p}&_fields=title,content')
            posts = json.loads(raw)
        except Exception:
            break
        if not isinstance(posts, list) or not posts:
            break
        for post in posts:
            title = page_text(post['title']['rendered'])
            if not title.startswith('ตรวจหวยฮานอยวันนี้') or 'งวดประจำวัน' not in title:
                continue
            d = find_date(title.split('งวดประจำวัน', 1)[1])
            blocks = parse_hanoi_blocks(page_text(post['content']['rendered']))
            if d and blocks:
                out.setdefault(d, {}).update(blocks)
    return out


# =====================================================================
# ข่าวสด — แหล่งที่สามของหวยลาว (มีคลังย้อนหลังแบ่งหน้า)
# =====================================================================
def khaosod_index(pages):
    """ไล่หน้ารวม /laolottery → [(date, url)]"""
    found = {}
    for p in range(1, pages + 1):
        url = 'https://www.khaosod.co.th/laolottery' + (f'/page/{p}' if p > 1 else '')
        try:
            html = http_get(url)
        except Exception:
            break
        items = re.findall(r'<a[^>]+href="(https://www\.khaosod\.co\.th/[a-z-]+/news_\d+)"[^>]*>([^<]{10,300})</a>', html)
        n = 0
        for href, title in items:
            title = page_text(title)
            if 'หวยลาว' not in title or 'งวดประจำวันที่' not in title:
                continue
            d = find_date(title.split('งวดประจำวันที่', 1)[1])
            if d:
                found[href] = (d, href); n += 1
        if not n:
            break
    return list(found.values())

def khaosod_lao(url):
    """→ (date, เลข 4 ตัว) หรือ None"""
    text = page_text(http_get(url))
    k = text.find('ผลรางวัลทั้งหมด')
    m_d = re.search(r'งวด(?:ล่าสุด|ประจำ)?วันที่\s*(\d{1,2}\s*[ก-๙\.]+\s*\d{4})', text)
    body = text[k:k + 400] if k >= 0 else text
    m4 = re.search(r'(?:เลข)?ท้าย\s*4\s*ตัว\s*:?\s*(\d{4})\b', body)
    m6 = re.search(r'เลข\s*6\s*ตัว\s*:?\s*(\d{6})\b', body)
    d = find_date(m_d.group(1)) if m_d else None
    if not (d and m4):
        return None
    if m6 and m6.group(1)[-4:] != m4.group(1):
        return None
    return d, m4.group(1)


def siamrath_hanoi(url):
    """→ (date, {key: (b3, top, bottom)}) หรือ None
    บทความสยามรัฐมีโฆษณาแทรกกลางบล็อก จึงตัดเป็นช่วงตามหัว 'ผลหวยฮานอย…' แล้วหาเลขในช่วงนั้น"""
    body, d = _siamrath_body(url)
    if not d:
        return None
    out = {}
    heads = list(re.finditer(r'ผลหวยฮานอย\s*([ก-๙A-Za-z]{0,10})', body))
    for i, h in enumerate(heads):
        key = hanoi_key(h.group(1))
        if not key or key in out:
            continue
        seg = body[h.end(): heads[i + 1].start() if i + 1 < len(heads) else h.end() + 600]
        b3 = re.search(r'เลข\s*3\s*ตัวบน\s*:?\s*(\d{3})', seg)
        top = re.search(r'เลข\s*2\s*ตัวบน\s*:?\s*(\d{2})', seg)
        bot = re.search(r'เลข\s*2\s*ตัวล่าง\s*:?\s*(\d{2})', seg)
        if b3 and top and bot and b3.group(1)[-2:] == top.group(1):
            out[key] = (b3.group(1), int(top.group(1)), int(bot.group(1)))
    return (d, out) if out else None
