"""Dönem 2–5 derleyicileri için ortak yardımcılar.

Kaynak tablolar üç biçimde gelir: Google E-Tablo (htmlview -> hücre ızgarası), Excel (.xlsx) ve Word (.docx).
Hepsi önce "satırlar listesi / hücre metni" biçimine çevrilir; dönem okuyucuları yalnızca bu ızgaralarla çalışır.
"""
import datetime as dt
import hashlib
import html
import json
import re
import urllib.request
import zipfile
from html.parser import HTMLParser

TZ = dt.timezone(dt.timedelta(hours=3))
UA = {"User-Agent": "Mozilla/5.0"}

TR_MONTHS = {"oca": 1, "şub": 2, "mar": 3, "nis": 4, "may": 5, "haz": 6,
             "tem": 7, "ağu": 8, "eyl": 9, "eki": 10, "kas": 11, "ara": 12}
MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def low(s):
    return str(s).replace("I", "ı").replace("İ", "i").lower()


def up(s):
    return str(s).replace("i", "İ").replace("ı", "I").upper()


def tr_title(s):
    out = []
    for w in clean(s).split(" "):
        if not w:
            continue
        lw = low(w)
        if lw in ("ve", "ile"):
            out.append(lw)
            continue
        out.append(w[0] + low(w[1:]))
    t = " ".join(out)
    return re.sub(r"\b(Iıı|Iii)\b", "III", re.sub(r"\bIı\b|\bIi\b", "II", t))


def clean(s):
    return re.sub(r"\s+", " ", str(s if s is not None else "")).strip()


def acad_year(month):
    """2026–2027 eğitim yılı: Ağustos–Aralık 2026, Ocak–Temmuz 2027 (kaynaklardaki yıl yazım hataları yok sayılır)."""
    return 2026 if month >= 8 else 2027


def parse_date(v):
    """'7 Eylül 2026 Pazartesi', '07.09.2026', datetime, '23 Eylü 2026' … -> date (eğitim yılına göre)."""
    if isinstance(v, dt.datetime):
        v = v.date()
    if isinstance(v, dt.date):
        return dt.date(acad_year(v.month), v.month, v.day)
    s = clean(v)
    if not s:
        return None
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        try:
            return dt.date(acad_year(mo), mo, d)
        except ValueError:
            return None
    m = re.search(r"(?<!\d)(\d{1,2})\s*([A-Za-zÇĞİÖŞÜçğıöşü]{3,})\s*(\d{4})?", s)
    if m:
        mo = TR_MONTHS.get(low(m.group(2))[:3])
        if mo:
            try:
                return dt.date(acad_year(mo), mo, int(m.group(1)))
            except ValueError:
                return None
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", s)
    if m:
        mo = int(m.group(2))
        return dt.date(acad_year(mo), mo, int(m.group(3)))
    return None


def parse_time(v):
    if isinstance(v, (dt.time, dt.datetime)):
        return f"{v.hour:02d}:{v.minute:02d}"
    m = re.search(r"(\d{1,2})[.:](\d{2})", str(v or ""))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def time_range(s):
    s = re.sub(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b", " ", str(s or ""))
    m = re.findall(r"(\d{1,2})[.:](\d{2})", s)
    if len(m) >= 2:
        return f"{int(m[0][0]):02d}:{m[0][1]}", f"{int(m[1][0]):02d}:{m[1][1]}"
    return None, None


def norm_no(v):
    """Öğrenci numarası -> 10 haneli metin (Excel'de sayı olarak saklanınca baştaki 0 kaybolur)."""
    if v is None:
        return ""
    if isinstance(v, float):
        v = int(v)
    s = re.sub(r"\.0$", "", clean(v))
    s = re.sub(r"\D", "", s)
    if not 8 <= len(s) <= 11:
        return ""
    return s.zfill(10)


# ---------------- ızgara okuyucular ----------------
class _Tbl(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.cur, self.cell, self.on, self.th, self.span = [], None, None, False, False, (1, 1)

    def handle_starttag(self, t, a):
        a = dict(a)
        if t == "table" and "waffle" in (a.get("class") or ""):
            self.on = True
        if not self.on:
            return
        if t == "tr":
            self.cur = []
        elif t == "th":
            self.th = True
        elif t == "td" and self.cur is not None:
            self.cell, self.span = [], (int(a.get("rowspan", 1)), int(a.get("colspan", 1)))
        elif t == "br" and self.cell is not None:
            self.cell.append("\n")

    def handle_endtag(self, t):
        if not self.on:
            return
        if t == "th":
            self.th = False
        elif t == "td" and self.cell is not None:
            self.cur.append(("".join(self.cell).strip(), self.span))
            self.cell = None
        elif t == "tr" and self.cur is not None:
            self.rows.append(self.cur)
            self.cur = None
        elif t == "table":
            self.on = False

    def handle_data(self, d):
        if self.cell is not None and not self.th:
            self.cell.append(d)


def _fill(rows):
    out, pend = [], {}
    for r, cells in enumerate(rows):
        row, c, it = [], 0, iter(cells)
        while True:
            if (r, c) in pend:
                row.append(pend.pop((r, c)))
                c += 1
                continue
            try:
                txt, (rs, cs) = next(it)
            except StopIteration:
                break
            for dc in range(cs):
                row.append(txt)
                for dr in range(1, rs):
                    pend[(r + dr, c + dc)] = txt
            c += cs
        while (r, c) in pend:
            row.append(pend.pop((r, c)))
            c += 1
        out.append(row)
    return out


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def gsheet_download(file_id):
    """Herkese açık Google E-Tablo -> {sayfa: ızgara}. (htmlview; birleşik hücreler doldurulur)"""
    h = _get(f"https://docs.google.com/spreadsheets/d/{file_id}/htmlview")
    items = re.findall(r'\{name: "((?:[^"\\]|\\.)*)", pageUrl: "[^"]*", gid: "(\d+)"', h)
    if not items:
        raise RuntimeError(f"E-Tablo sayfaları bulunamadı: {file_id}")
    res = {}
    for name, gid in items:
        p = _Tbl()
        p.feed(_get(f"https://docs.google.com/spreadsheets/d/{file_id}/htmlview/sheet?headers=false&gid={gid}"))
        res[json.loads('"' + name + '"')] = _fill(p.rows)
    return res


def xlsx_grids(path, fill_merged=True):
    """Excel -> {sayfa: ızgara (metin)}; birleşik hücreler sol üst değerle doldurulur."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    out = {}
    for ws in wb.worksheets:
        grid = [[c for c in r] for r in ws.iter_rows(values_only=True)]
        if fill_merged:
            for rng in ws.merged_cells.ranges:
                v = ws.cell(rng.min_row, rng.min_col).value
                for r in range(rng.min_row, rng.max_row + 1):
                    for c in range(rng.min_col, rng.max_col + 1):
                        if r - 1 < len(grid) and c - 1 < len(grid[r - 1]):
                            grid[r - 1][c - 1] = v
        out[ws.title] = grid
    return out


def docx_tables(path):
    """Word -> (paragraf metinleri, tablolar[satırlar[hücre metni]]). Yatay birleşik hücreler (gridSpan) çoğaltılır."""
    x = zipfile.ZipFile(path).read("word/document.xml").decode("utf8")
    body = re.search(r"<w:body>(.*)</w:body>", x, re.S).group(1)

    def text(fr):
        fr = re.sub(r"<w:tab/>", " ", fr)
        fr = re.sub(r"<w:br[^>]*/>", "\n", fr)
        fr = re.sub(r"</w:p>", "\n", fr)
        return html.unescape(re.sub(r"<[^>]+>", "", fr)).strip()

    tables = []
    for tb in re.findall(r"<w:tbl>.*?</w:tbl>", body, re.S):
        rows = []
        for tr in re.findall(r"<w:tr[ >].*?</w:tr>", tb, re.S):
            row = []
            for tc in re.findall(r"<w:tc>.*?</w:tc>", tr, re.S):
                span = re.search(r'<w:gridSpan w:val="(\d+)"', tc)
                t = text(tc)
                row.extend([t] * (int(span.group(1)) if span else 1))
            rows.append(row)
        tables.append(rows)
    paras = [text(p) for p in re.findall(r"<w:p[ >].*?</w:p>", re.sub(r"<w:tbl>.*?</w:tbl>", "", body, flags=re.S), re.S)]
    return [p for p in paras if p], tables


def cell(r, i):
    return clean(r[i]) if i < len(r) and r[i] is not None else ""


# ---------------- ortak okuyucular ----------------
def mentioned_groups(title):
    """Ders programı satırı başlığında belirli gruplar anılıyorsa onların harfleri: '(A-B Grubu)', '(H Grubu)', 'A-B GRUBU'.
    Tek harfli ve parantezsiz anmalar ('B grubu vitaminler' gibi) ders konusu olabileceği için sayılmaz."""
    T = up(title)
    m = re.search(r"\(\s*([A-H](?:\s*[-,/]\s*[A-H])*)\s+GRUBU\s*\)", T) or re.search(r"(?<![A-ZÇĞİÖŞÜ])([A-H](?:\s*-\s*[A-H])+)\s+GRUBU\b", T)
    return sorted(set(re.findall(r"[A-H]", m.group(1)))) if m else None


def ders_rows(rows, group_tag=None):
    """'TARİH | Başlama | Bitiş | KONU | DİLİM ADI / ANABİLİM DALI | YER' düzenindeki ders programı."""
    events, hdr = [], None
    for r in rows:
        if hdr is None:
            if any(low(cell(r, i)).startswith("tari") for i in range(min(3, len(r)))):
                hdr = next(i for i in range(len(r)) if low(cell(r, i)).startswith("tari"))
            continue
        day = parse_date(cell(r, hdr))
        title = cell(r, hdr + 3)
        if not day or not title:
            continue
        s, e = parse_time(cell(r, hdr + 1)), parse_time(cell(r, hdr + 2))
        konu, hoca = title, ""
        parts = re.split(r"\s*/\s*", title, maxsplit=1)
        if len(parts) == 2 and re.search(r"(Dr\.|Prof|Doç|Öğr|Uzm|Gör)", parts[1]):
            konu, hoca = parts
        f = cell(r, hdr + 4)
        fp = re.split(r"\s*/\s*", f, maxsplit=1) if f else [""]
        ev = {"d": day.isoformat(), "s": s, "e": e, "t": konu, "h": hoca,
              "dl": fp[0], "ad": fp[1] if len(fp) > 1 else "", "y": cell(r, hdr + 5)}
        if group_tag:
            ev["g"] = [group_tag]
        elif mentioned_groups(konu):  # ör. 'UYGULAMA (A-B Grubu) - Histoloji' yalnız A ve B grubunundur
            ev["g"] = mentioned_groups(konu)
        events.append(ev)
    return events


def amfi_rows(rows, donem, group_re=r"\b([A-H])\s*-?\s*GRUBU"):
    """Haftalık amfi programının ilk tablosundan bu dönemin (Türkçe) satırları."""
    out, day, hdr, seen = [], None, None, set()
    pat = re.compile(rf"D[ÖO]NEM\s*-?\s*{donem}(?!\d)")
    for r in rows:
        c0 = cell(r, 0)
        if not c0:
            continue
        if re.match(r"\d{1,2}\s+[A-Za-zÇĞİÖŞÜçğıöşü]+\s+\d{4}", c0):
            d = parse_date(c0)
            if d in seen or (seen and d < max(seen)):
                break
            seen.add(d)
            day = d
            continue
        if up(c0) == "SAAT":
            hdr = r
            continue
        if not day or not hdr:
            continue
        s, e = time_range(c0)
        for i in range(1, len(r)):
            cu = up(cell(r, i))
            if not pat.search(cu) or ("İNGİLİZCE" in cu and "TÜRKÇE" not in cu):
                continue
            mg = re.search(group_re, cu)
            out.append({"d": day.isoformat(), "s": s, "e": e, "r": cell(hdr, i), "t": cell(r, i),
                        "g": [mg.group(1)] if mg else None})
    week = ""
    if seen:
        a, b = min(seen), max(seen)
        week = (f"{a.day}–{b.day} {MONTHS_TR[b.month-1]} {b.year}" if a.month == b.month
                else f"{a.day} {MONTHS_TR[a.month-1]} – {b.day} {MONTHS_TR[b.month-1]} {b.year}")
    # aynı hücre ardışık saatlerde tekrarlanır: tek kayıtta birleştir
    merged = []
    for x in out:
        p = next((m for m in reversed(merged) if m["d"] == x["d"] and m["r"] == x["r"] and m["t"] == x["t"] and m["e"] and x["s"]
                  and 0 <= (int(x["s"][:2]) * 60 + int(x["s"][3:])) - (int(m["e"][:2]) * 60 + int(m["e"][3:])) <= 20), None)
        if p:
            p["e"] = x["e"]
        else:
            merged.append(dict(x))
    return week, merged


# ---------------- değişiklik takibi (Dönem 1 ile aynı mantık) ----------------
def _sig(data, today):
    out = {}
    for e in data.get("events", []):
        if e["d"] < today or re.match(r"(ÖĞLE|SERBEST)", up(e["t"])):
            continue
        out[("ders", e["d"], e["s"], ",".join(e.get("g") or []))] = {"txt": e["t"], "y": e.get("y", ""), "e": e["e"], "g": e.get("g") or ["*"]}
    for u in data.get("uyg", []):
        if u["d"] < today:
            continue
        out[("uyg", u["d"], u["s"], u["n"], ",".join(u.get("g") or []))] = {"txt": u["n"], "y": u.get("y", ""), "e": u["e"], "g": u.get("g") or ["*"]}
    for x in data.get("secmeli") or []:  # seçmeli dersin o haftaki notu (ders yok, yer değişti …): yalnız o dersi seçenler görür
        for d, note in (x.get("ex") or {}).items():
            if d >= today:
                out[("sec", d, x["s"], x["id"])] = {"txt": f'{x["ad"]}: {note}', "y": x.get("yer", ""), "e": x["e"], "g": ["sec:" + x["id"]]}
    for a in data.get("amfi", []):
        if a["d"] < today:
            continue
        # amfi satırının kimi ilgilendirdiği: grup (g), ders grubu (lg, ör. 3A) ya da uygulama alt grupları (sub)
        g = a.get("g") or a.get("lg") or a.get("sub") or ["*"]
        k = ("amfi", a["d"], a["s"], a["t"][:60])
        if k in out:  # aynı ders/sınav birden çok salonda: salonlar birlikte karşılaştırılır
            o = out[k]
            o["y"] = ", ".join(sorted(set(o["y"].split(", ")) | {a["r"]}))
            o["g"] = sorted(set(o["g"]) | set(g))
            continue
        out[k] = {"txt": a["t"], "y": a["r"], "e": a["e"], "g": list(g)}
    return out, {a["d"] for a in data.get("amfi", [])}


def diff(prev, new, now):
    today = now.strftime("%Y-%m-%d")
    A, ad = _sig(prev, today)
    B, bd = _sig(new, today)
    both = ad & bd
    stamp = now.strftime("%Y-%m-%d %H:%M")
    ch = []
    for k in sorted(set(A) | set(B), key=str):
        if k[0] == "amfi" and k[1] not in both:
            continue
        if k[0] == "sec" and not prev.get("secmeli"):
            continue  # seçmeli listesi bu dönemin dosyasına ilk kez giriyorsa "değişiklik" sayılmaz
        a, b = A.get(k), B.get(k)
        if a == b:
            continue
        if k[0] == "amfi" and a and b and (a["txt"], a["y"], a["e"]) == (b["txt"], b["y"], b["e"]):
            continue  # amfi satırı aynı; yalnız hangi gruba bağlandığı değişti (çözümleme düzeltmesi): değişiklik sayılmaz
        typ = "mod" if a and b else ("add" if b else "del")
        groups = sorted({g for x in (a, b) if x for g in x["g"]})
        ch.append({"at": stamp, "src": k[0], "type": typ, "d": k[1], "s": k[2], "e": (b or a)["e"], "g": groups,
                   "old": a and {"t": a["txt"], "y": a.get("y", ""), "e": a["e"]},
                   "new": b and {"t": b["txt"], "y": b.get("y", ""), "e": b["e"]}})
    return _net_groups(ch, new)


def _net_groups(ch, data):
    """Aynı ders/uygulamanın yalnız grupları değiştiyse (ör. 'B' yerine 'D'), 'kaldırıldı' ve 'eklendi' kayıtları
    yalnız durumu gerçekten değişen gruplara gösterilir: kaldırılan = eski − yeni, eklenen = yeni − eski."""
    letters = sorted({g for x in data.get("events", []) + data.get("uyg", []) for g in (x.get("g") or []) if len(g) == 1})
    exp = lambda gs: set(letters) | (set(gs) - {"*"}) if "*" in gs else set(gs)  # noqa: E731
    sig = lambda c, side: (c["src"], c["d"], c["s"], c[side]["t"], c[side]["y"], c[side]["e"])  # noqa: E731
    adds = {}
    for c in ch:
        if c["type"] == "add":
            adds.setdefault(sig(c, "new"), []).append(c)
    drop = set()
    for c in ch:
        if c["type"] != "del":
            continue
        pair = next((a for a in adds.get(sig(c, "old"), []) if id(a) not in drop), None)
        if not pair:
            continue
        old_g, new_g = exp(c["g"]), exp(pair["g"])
        removed, added = old_g - new_g, new_g - old_g
        if removed:
            c["g"] = sorted(removed)
        else:
            drop.add(id(c))
        if added:
            pair["g"] = sorted(added)
        else:
            drop.add(id(pair))
        adds[sig(c, "old")].remove(pair)
    return [c for c in ch if id(c) not in drop]


def content_hash(d):
    return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def finish(data, prev, now):
    """hash, built, lastCheck, changes alanlarını ekler (Dönem 1'deki kurallarla)."""
    h = content_hash({k: v for k, v in data.items() if k not in ("students",)})
    today = now.strftime("%Y-%m-%d")
    changes = list(prev.get("changes", [])) if prev else []
    if prev and prev.get("hash") != h:
        new_ch = [c for c in diff(prev, data, now) if c["d"] >= today]
        changes = new_ch + changes
        built = now.strftime("%Y-%m-%d %H:%M") if new_ch else (prev.get("built") or now.strftime("%Y-%m-%d %H:%M"))
    else:
        new_ch = []
        built = prev.get("built") if prev else now.strftime("%Y-%m-%d %H:%M")
    cutoff = (now - dt.timedelta(days=21)).strftime("%Y-%m-%d")
    changes = [c for c in changes if c["at"][:10] >= cutoff and c["d"] >= today][:300]
    data.update({"hash": h, "built": built, "lastCheck": now.strftime("%Y-%m-%d %H:%M"), "changes": changes})
    return len(new_ch)
