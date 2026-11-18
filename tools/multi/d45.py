"""Dönem 4 ve 5: her grubun haftalık ders/staj tablosu (sayfa başına bir grup).

Tablo düzeni: dilim başlığı · 'N. Hafta' satırı (Pazartesi–Cuma tarihleri) · saat satırları (1. sütun saat,
2. sütun hangi alt grubun satırı olduğu: 'B', 'B1', 'B2-1' …; boşsa bütün grup) · hücrelerde ders/uygulama.
Dönem 5'te 'B1' gibi etiketler o haftada 'B3' de geçiyorsa üçlü, geçmiyorsa ikili grubu gösterir.
"""
import json
import re
from .common import clean, up, parse_date, time_range, norm_no, amfi_rows, tr_title

SKIP = re.compile(r"^(SAAT|UYGULAMA GRUBU)$")


def _title(r):
    vals = [clean(x) for x in r if x is not None and clean(x)]
    if not vals or len(set(vals)) != 1:
        return None
    t = vals[0]
    if re.search(r"\d{1,2}[.:]\d{2}", t) or re.match(r"^\d+\.\s*HAFTA", up(t)) or up(t) in ("SAAT",):
        return None
    return t


def _date(v):
    """Hücre bir tarihse tarih (Excel tarihi ya da '14.06.2027' / '14 Haziran 2027' gibi yazı); değilse None."""
    if v is None:
        return None
    if isinstance(v, str) and not re.search(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d\d-\d\d|\d{1,2}\s+[A-Za-zÇĞİÖŞÜçğıöşü]+\s+\d{4}", v):
        return None
    try:
        return parse_date(v)
    except Exception:  # noqa: BLE001
        return None


def weekly(grid, letter, donem, warn, sheet):
    out, title, days, block = [], "", None, []

    def flush():
        if not block:
            return
        three = donem == 5 and any(re.fullmatch(rf"{letter}3", sp) for _, _, sp, _ in block)
        for d, (s, e), sp, txt in block:
            if not sp or sp == letter:
                g = [letter]
            elif donem == 5 and re.fullmatch(rf"{letter}[123]", sp):
                g = [("3:" if three else "2:") + sp]
            else:
                g = [sp]
            t = clean(txt)
            konu, hoca = t, ""
            parts = re.split(r"\s*/\s*", t, maxsplit=1)
            if len(parts) == 2 and re.search(r"(Dr\.|Prof|Doç|Öğr|Uzm|Gör|DR\.|PROF|DOÇ)", parts[1]):
                konu, hoca = parts
            ev = {"d": d, "s": s, "e": e, "t": konu, "h": hoca, "dl": title, "ad": "", "y": "", "g": g}
            U = up(konu)
            if "UYGULAMA" in U and "SINAV" not in U:
                ev["k"] = "uyg"
            elif U.startswith("ÖĞLE"):
                ev["k"] = "lunch"
            out.append(ev)
        block.clear()

    for r in grid:
        if not r:
            continue
        a = clean(r[0]) if r[0] is not None else ""
        t = _title(r)
        if t:
            flush()
            title = tr_title(re.sub(r"\s*DİLİMİ\s*$", " Dilimi", t))
            continue
        # hafta satırı: 'N. Hafta' + Pazartesi–Cuma tarihleri; bütünleme haftalarında ilk hücre boş, yalnız tarihler var
        dates = [_date(r[j]) if j < len(r) else None for j in range(2, 7)]
        if re.match(r"^\d+\s*\.\s*HAFTA", up(a)) or (not a and sum(1 for d in dates if d) >= 3):
            flush()
            days = [d.isoformat() if d else None for d in dates]
            continue
        if not days or SKIP.match(up(a)):
            continue
        s, e = time_range(a)
        if not s:
            continue
        sp = up(clean(r[1])) if len(r) > 1 and r[1] is not None else ""
        sp = sp.replace(" ", "")
        if sp and sp[0] != letter and re.fullmatch(r"[A-G](\d(-\d)?)?", sp):
            warn.append(f"{sheet}: '{sp}' etiketi {letter} grubunun sayfasında; {letter}{sp[1:]} sayıldı")
            sp = letter + sp[1:]
        for j in range(5):
            if not days[j]:
                continue
            v = r[j + 2] if j + 2 < len(r) else None
            if v is None or not clean(v):
                continue
            block.append((days[j], (s, e), sp, v))
    flush()
    return out


def students4(sheets):
    out = {}
    for grid in sheets.values():
        for r in grid:
            no = norm_no(r[3]) if len(r) > 3 else ""
            g1, g2, g4 = (up(clean(r[i])) if r[i] is not None else "" for i in range(3))
            if no and re.fullmatch(r"[A-G]", g1):
                out[no] = [x for x in (g1, g2, g4) if x]
    return out


def students5(sheets):
    out = {}
    for grid in sheets.values():
        for r in grid:
            no = norm_no(r[3]) if len(r) > 3 else ""
            raw1 = up(clean(r[0])) if r[0] is not None else ""
            g1 = raw1[:1]
            g2 = up(clean(r[1])) if r[1] is not None else ""
            if not g2 and re.fullmatch(r"[A-G][12]", raw1):  # kaynakta grup sütununa ikili grup yazılmış (ör. 'E1')
                g2 = raw1
            g3 = up(clean(r[2])) if r[2] is not None else ""
            if no and re.fullmatch(r"[A-G]", g1):
                out[no] = [g1] + (["2:" + g2] if g2 else []) + (["3:" + g3] if g3 else [])
    return out


def build_common(donem, src, students):
    warn, ev = [], []
    for name, grid in src["ders"].items():
        m = re.search(r"([A-G])\s*(GRUBU)?\s*$", up(name)) if donem == 4 else re.search(rf"^{donem}\s*([A-G])$", up(name).replace(" ", ""))
        if not m or (donem == 4 and "GRUBU" not in up(name)):
            continue
        ev += weekly(grid, m.group(1), donem, warn, name)
    week, am = amfi_rows(src["amfi"], donem)
    for a in am:  # gruplu amfi satırları bu dönemlerde ders salonudur
        a["lg"], a["g"] = a["g"], None
    for e in ev:  # boş alanlar yayımlanan dosyayı gereksiz büyütüyor
        for k in ("h", "ad", "y", "dl"):
            if not e.get(k):
                e.pop(k, None)
    # kaynakta aynı satır bazen iki kez yazılmış (ör. bütünleme haftası, bayram): birebir aynıları bir kez tutulur
    seen, uniq = set(), []
    for e in ev:
        k = json.dumps(e, sort_keys=True, ensure_ascii=False)
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    ev = uniq
    st = students(src["ogrenci"])
    data = {"v": 1, "donem": donem, "amfiWeek": week, "events": ev, "uyg": [], "amfi": am}
    groups = sorted({g for e in ev for g in e["g"] if len(g) == 1})
    stats = {"students": len(st), "events": len(ev), "groups": len(groups), "amfi": len(am)}
    return data, st, stats, warn
