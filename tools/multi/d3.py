"""Dönem 3 Türkçe: A/B grupları ayrı ders programı; hasta başı (İç H. / ÇSvH), öğretim üyesi uygulaması (alt grup A1–B8),
mikrobiyoloji-patoloji uygulaması (ayrı liste: A1, A2, B1, B2)."""
import datetime as dt
import re
from .common import cell, clean, low, up, tr_title, parse_date, time_range, norm_no, ders_rows, amfi_rows

DEPT = {"İÇH": "İç Hastalıkları", "ÇSVH": "Çocuk Sağlığı ve Hastalıkları", "ÇSH": "Çocuk Sağlığı ve Hastalıkları"}
DILIM_KOD = {"H": "Hareket II", "KL": "Kan-Lenfoid II", "D": "Dolaşım II", "SL": "Solunum II", "END": "Endokrin-Metabolizma II",
             "ÜRG": "Ürogenital ve Üreme II"}


NAMEFIX = {"Kbb": "KBB", "Geratri": "Geriatri", "Gastroent.": "Gastroenteroloji", "Çocuk Gastro.": "Çocuk Gastroenterolojisi",
           "Göğüs Hast.": "Göğüs Hastalıkları", "Genel Cer.": "Genel Cerrahi", "İç Hast.": "İç Hastalıkları",
           "Çocuk Kardiyo": "Çocuk Kardiyolojisi", "Çocuk Kardiyoloji": "Çocuk Kardiyolojisi", "Çocuk Nefroloji": "Çocuk Nefrolojisi",
           "Çocuk End.- Met.": "Çocuk Endokrinolojisi", "İç Hast. Endokrin": "Endokrinoloji", "İç Hast. Tıbbi Genetik": "Tıbbi Genetik",
           "Çocuk Nöroloji": "Çocuk Nörolojisi", "Çocuk Hematolojisi": "Çocuk Hematolojisi"}


def amfi_groups(am):
    """3A/3B ders amfileri ('TÜRKÇE-A') ve öğretim üyesi uygulaması salonları ('A3 - A-4 - KARDİYOLOJİ')."""
    for a in am:
        t = up(a["t"])
        m = re.search(r"TÜRKÇE\s*-?\s*([AB])\b", t) or re.search(r"\b([AB])\s*GRUBU", t)
        if m:
            a["lg"] = [m.group(1)]
        tail = t.split("DİLİMİ", 1)[-1]
        subs = sorted({f"{x}{y}" for x, y in re.findall(r"\b([AB])\s*-?\s*([1-8])\b", tail)})
        if subs:
            a["sub"] = subs
        a["g"] = None
    return am


def students(main, mp_grid):
    mp = {}
    for r in mp_grid:
        no, g = norm_no(r[0] if r else None), up(cell(r, 3))
        if no and re.fullmatch(r"[AB][12]", g):
            mp[no] = g
    out = {}
    for r in main:
        no = norm_no(cell(r, 0))
        g = up(cell(r, 3))[:1]
        if not no or g not in ("A", "B"):
            continue
        sub = up(cell(r, 4))
        tags = [g] + ([sub] if re.fullmatch(r"[AB][1-8]", sub) else [])
        if no in mp:
            tags.append("mp:" + mp[no])
        out[no] = tags
    return out, len(mp)


def _hb_topics(paras):
    """'İçH - U 1' / 'ÇSH -U 1' başlığından sonra gelen konu metni."""
    topics, key = {}, None
    for p in paras:
        m = re.match(r"^(\S+)\s*-\s*U\s*(\d+)$", clean(p))
        if m and re.search(r"(?i)h$", m.group(1)):
            key = ("ÇSVH" if "S" in up(m.group(1)) else "İÇH", int(m.group(2)))
            continue
        if key and key not in topics and len(clean(p)) > 15:
            t = clean(p)
            topics[key] = t if len(t) <= 160 else t[:157].rsplit(" ", 1)[0] + "…"
        key = None if key in topics else key
    return topics


def hasta_basi(doc, group):
    """tarih -> (bölüm kodu, U no) — bu grubun hasta başı uygulaması."""
    paras, tables = doc
    out = {}
    for t in tables:
        for r in t:
            for j in range(0, len(r) - 1):
                d = parse_date(r[j]) if re.search(r"\d{1,2}\.\d{1,2}\.\d{4}", r[j] or "") else None
                m = re.search(r"([İI]çH|ÇSv?H)\s*U\s*(\d+)", r[j + 1] or "", re.I)
                if d and m:
                    k = "İÇH" if low(m.group(1)).startswith(("iç", "ıç")) else "ÇSVH"
                    out[d.isoformat()] = (k, int(m.group(2)))
    return out, _hb_topics(paras)


def ogretim_uyesi(sheets):
    """Öğretim üyesi uygulama tabloları -> [{d, s, e, n, g:[A3], dl}]"""
    out = []
    for grid in sheets.values():
        dilim, depts, s, e = "", None, "11:10", "12:10"
        for r in grid:
            a = r[0] if r else None
            sa = clean(a)
            if "UYGULAMA PROGRAMI" in up(sa):
                m = re.search(r"DÖNEM-?\s*3\s+(.*?)\s+DİLİMİ", up(sa))
                dilim = tr_title(m.group(1)) if m else ""
                s, e = time_range(sa)
                s, e = s or "11:10", e or "12:10"
                depts = None
                continue
            if low(sa).startswith("anabilim"):
                depts = [NAMEFIX.get(t, t) for t in (tr_title(clean(x).replace("\n", " ")) if x else "" for x in r)]
                continue
            if depts and isinstance(a, (dt.datetime, dt.date)):
                d = parse_date(a)
                for j in range(1, len(r)):
                    g = up(clean(r[j]))
                    if re.fullmatch(r"[AB][1-8]", g) and j < len(depts) and depts[j]:
                        out.append({"d": d.isoformat(), "s": s, "e": e, "n": depts[j], "hoca": "Öğretim üyesi uygulaması",
                                    "g": [g], "y": "", "dl": dilim})
    return out


def mikpat(doc):
    """Mikrobiyoloji / Patoloji uygulama programı -> uyg kayıtları (mp:A1 …)."""
    _, tables = doc
    out = []
    for t in tables:
        for r in t:
            if len(r) < 6:
                continue
            raw = r[3] or ""
            d = parse_date(raw) if re.search(r"\d{1,2}\.\d{1,2}\.\d{4}", raw) else None
            if not d:
                continue
            s, e = time_range(raw)
            s, e = s or "14:30", e or "16:20"
            for j, name in ((4, "Mikrobiyoloji"), (5, "Patoloji")):
                v = clean(r[j])
                m = re.match(r"([AB][12])\s*-", up(v))
                if not m:
                    continue
                code = re.search(r"\(\s*([A-ZÇĞİÖŞÜ]+)\s*\d?\s*\)", up(v))
                k = code.group(1) if code else ""
                dl = DILIM_KOD.get(k) or ("Sindirim II" if k == "SND" and d < dt.date(2027, 3, 15) else "Sinir Duyu II" if k == "SND" else "")
                out.append({"d": d.isoformat(), "s": s, "e": e, "n": name, "hoca": "", "g": ["mp:" + m.group(1)], "y": "", "dl": dl})
    return out


def build(src):
    st, n_mp = students(src["ogrenci"], next(iter(src["mikpat_liste"].values())))
    ev = ders_rows(src["ders_A"], "A") + ders_rows(src["ders_B"], "B")
    hb = {"A": hasta_basi(src["hastabasi_A"], "A"), "B": hasta_basi(src["hastabasi_B"], "B")}
    warn = []
    for x in ev:
        g = x["g"][0]
        T = up(x["t"])
        if T.startswith("HASTA BAŞI"):
            m = re.search(rf"\b{g}\s*GRUBU\s*\(([^)]*)\)", T)
            k = "İÇH" if m and "İÇ" in m.group(1) else ("ÇSVH" if m else "")
            table, topics = hb[g]
            code = table.get(x["d"])
            if code and k and code[0] != k:
                warn.append(f"hasta başı {g} {x['d']}: ders programı {k}, tablo {code[0]}")
            k = k or (code[0] if code else "")
            x["t"] = f"Hasta Başı Uygulaması · {DEPT.get(k, 'İç H. / ÇSvH')}"
            x["h"] = ""
            if code:
                x["ad"] = f"{'İçH' if code[0]=='İÇH' else 'ÇSvH'} U{code[1]}" + (f" · {topics[code]}" if code in topics else "")
            x["y"] = ""
        elif T.startswith("ÖĞRETİM ÜYESİ UYGULAMA") or T.startswith("UYGULAMA (PATOLOJİ"):
            x["t"] = "UYGULAMA · " + ("Öğretim üyesi uygulaması" if T.startswith("ÖĞRETİM") else "Patoloji / Mikrobiyoloji")
    uy = ogretim_uyesi(src["ogruye_A"]) + ogretim_uyesi(src["ogruye_B"]) + mikpat(src["mikpat_prog"])
    week, am = amfi_rows(src["amfi"], 3, group_re=r"(?!)")
    am = amfi_groups(am)
    tm = lambda x: int(x[:2]) * 60 + int(x[3:]) if x else None  # noqa: E731
    for u in uy:
        if not u["hoca"]:
            continue
        for a in am:
            same_t = a["s"] and u["s"] and tm(a["s"]) < tm(u["e"]) and tm(u["s"]) < tm(a["e"])
            same_n = up(u["n"].split()[0])[:6] in up(a["t"])
            if a["d"] == u["d"] and u["g"][0] in a.get("sub", []) and (same_t or same_n):
                u["y"] = a["r"]
                break
    data = {"v": 1, "donem": 3, "amfiWeek": week, "events": ev, "uyg": uy, "amfi": am}
    stats = {"students": len(st), "events": len(ev), "uyg": len(uy), "mikpat": n_mp, "amfi": len(am),
             "ogruye": sum(1 for u in uy if u["hoca"]), "hastabasi": sum(1 for x in ev if x["t"].startswith("Hasta Başı"))}
    need = {"students": 300, "events": 1500, "ogruye": 200, "mikpat": 300, "hastabasi": 50}
    return data, st, stats, need, warn
