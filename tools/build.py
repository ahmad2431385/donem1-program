"""Build data.json for the personal schedule page from the four source files."""
import argparse, csv, datetime as dt, hashlib, io, json, os, re, sys
import openpyxl

AP = argparse.ArgumentParser(description="Dönem 1 kişisel program verisini üretir")
AP.add_argument("--data", default="/home/claude/data", help="ders.xlsx, uyg.xlsx, ogrenci.xlsx, amfi.csv (+ isteğe bağlı pdo.xlsx, secmeli.csv)")
AP.add_argument("--prev", default=None, help="önceki data.json (değişiklik karşılaştırması için)")
AP.add_argument("--out", default="/home/claude/build/data.json")
ARGS = AP.parse_args()
DATA, OUT = ARGS.data, ARGS.out
TZ = dt.timezone(dt.timedelta(hours=3))

TR_MONTHS = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
             "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}
EN_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}


def low(s):
    return s.replace("I", "ı").replace("İ", "i").lower()


def parse_date(v):
    if isinstance(v, dt.datetime):
        d = v.date()
    elif isinstance(v, dt.date):
        d = v
    elif isinstance(v, str):
        m = re.match(r"\s*(\d{1,2})\s+([^\s\d]+)\s+(\d{4})", v)
        if not m:
            return None
        mon = low(m.group(2))
        mm = TR_MONTHS.get(mon) or EN_MONTHS.get(mon)
        if not mm:
            return None
        d = dt.date(int(m.group(3)), mm, int(m.group(1)))
    else:
        return None
    # known typos in source: years outside the 2026-27 academic year
    if d.year < 2026 or (d.year == 2026 and d.month < 8):
        d = d.replace(year=2026 if d.month >= 8 else 2027)
    return d


def parse_time(v):
    if isinstance(v, dt.time):
        return f"{v.hour:02d}:{v.minute:02d}"
    if isinstance(v, dt.datetime):
        return f"{v.hour:02d}:{v.minute:02d}"
    if isinstance(v, str):
        m = re.search(r"(\d{1,2})[.:](\d{2})", v)
        if m:
            return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def time_range(s):
    m = re.findall(r"(\d{1,2})[.:](\d{2})", str(s))
    if len(m) >= 2:
        return f"{int(m[0][0]):02d}:{m[0][1]}", f"{int(m[1][0]):02d}:{m[1][1]}"
    return None, None


def tr_title(s):
    out=[]
    for w in clean(s).split(" "):
        if not w: continue
        lw=low(w)
        if lw in ("ve","ile"):
            out.append(lw); continue
        f=w[0]; rest=low(w[1:])
        out.append(f+rest)
    return " ".join(out).replace("Iıı","III").replace("Iii","III").replace("Ii ","II ")


def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


# ---------------- Students (numbers -> group, subgroup; no names) ----------------
def students():
    ws = openpyxl.load_workbook(f"{DATA}/ogrenci.xlsx").active
    out, g, a = {}, None, None
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0]:
            g = clean(r[0]).upper()
        if r[1]:
            a = clean(r[1]).upper()
        no = clean(r[2])
        if isinstance(r[2], float):
            no = str(int(r[2]))
        no = re.sub(r"\.0$", "", no)
        if no and re.fullmatch(r"\d{6,12}", no):
            out[no] = [g, a]
    return out


# ---------------- Ders programı ----------------
WEEKDAYS = {"PAZARTESİ": 0, "SALI": 1, "ÇARŞAMBA": 2, "PERŞEMBE": 3, "CUMA": 4}


def ders():
    ws = openpyxl.load_workbook(f"{DATA}/ders.xlsx").active
    events, weekly = [], []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not any(r[:7]):
            continue
        _, b, c, d, e, f, g = r[:7]
        title = clean(e)
        if not title:
            continue
        s, t = parse_time(c), parse_time(d)
        konu, hoca = title, ""
        if " / " in title or "/" in title:
            parts = re.split(r"\s*/\s*", title, maxsplit=1)
            # only treat the right side as a lecturer if it looks like a name/title
            if len(parts) == 2 and re.search(r"(Dr\.|Prof|Doç|Öğr|Uzm|Gör)", parts[1]):
                konu, hoca = parts
        dilim, ad = "", ""
        if f:
            fp = re.split(r"\s*/\s*", clean(f), maxsplit=1)
            dilim = fp[0]
            ad = fp[1] if len(fp) > 1 else ""
        yer = clean(g)
        if isinstance(b, str) and b.upper().startswith("HER HAFTA"):
            wd = WEEKDAYS.get(b.upper().replace("HER HAFTA", "").strip())
            wp = re.split(r"\s*/\s*", title, maxsplit=1)
            weekly.append({"wd": wd, "s": s, "e": t, "t": wp[0], "h": wp[1] if len(wp) > 1 else "", "y": yer})
            continue
        day = parse_date(b)
        if not day:
            continue
        events.append({"d": day.isoformat(), "s": s, "e": t, "t": konu, "h": hoca,
                       "dl": dilim, "ad": ad, "y": yer})
    return events, weekly


# ---------------- Uygulama tablosu ----------------
PLACES = [
    ("temel yaşam", "Simülasyon Merkezi – Hulusi Behçet Kütüphanesi Giriş Kat, Salon 1"),
    ("yaralı taşıma", "Simülasyon Merkezi – Hulusi Behçet Kütüphanesi Giriş Kat, Salon 2"),
    ("kırık", "Nöroloji Bilimleri Binası, Ortopedi AD 4. kat"),
    ("mikroskop", "Histoloji AD Uygulama Salonu – Temel Bilimler -2. kat"),
    ("biyoloji", "Temel Bilimler Binası, Tıbbi Biyoloji Pratik Salonu – Kat 2"),
    ("histoloji", "Temel Bilimler -2. kat"),
    ("biyokimya", "Temel Bilimler 3. kat"),
    ("mikrobiyoloji", "Temel Bilimler 1. kat"),
    ("fizyoloji", "Temel Bilimler -1. kat"),
    ("biyofizik", "Temel Bilimler -1. kat"),
    ("anatomi", "Anatomi AD girişi uygulama salonu"),
    ("iletişim", "Simülasyon Merkezi – Hulusi Behçet Kütüphanesi"),
    ("nabız", "Simülasyon Merkezi – Hulusi Behçet Kütüphanesi Giriş Kat, Salon 2"),
    ("dikiş", "Simülasyon Merkezi – Hulusi Behçet Kütüphanesi Giriş Kat, Salon 1"),
    ("enjeksiyon", "Simülasyon Merkezi – Hulusi Behçet Kütüphanesi Giriş Kat"),
    ("münazara", "Simülasyon Merkezi – Hulusi Behçet Kütüphanesi Giriş Kat"),
]


def place_for(name):
    n = low(name)
    for k, p in PLACES:
        if k in n:
            return p
    return "Amfi programına bak"


def split_header(h):
    h = clean(h)
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", h)
    if m and m.group(1):
        return m.group(1).strip(), m.group(2).strip()
    if m and not m.group(1):  # header that is only "(Dr. ...)" -> Şimdi Burada in Hücre
        return "Şimdi ve Burada", m.group(2).strip()
    return h, ""


def uygulama():
    ws = openpyxl.load_workbook(f"{DATA}/uyg.xlsx").active
    rows = list(ws.iter_rows(values_only=True))
    out, header, dilim, last_title = [], None, "", ""
    for i, r in enumerate(rows):
        a = clean(r[0])
        if a and "DİLİMİ" in a.upper() and not any(clean(x) for x in r[2:6]):
            last_title = tr_title(a)
        if low(a).startswith("uygulama tarihi"):
            header = [clean(x) for x in r]
            dilim = last_title
            continue
        if low(a).startswith("uygulama sayısı"):
            header = None
            continue
        if not header:
            continue
        d = parse_date(r[0])
        if not d:
            continue
        s, e = time_range(r[1])
        for ci in range(2, len(header)):
            val = clean(r[ci]) if ci < len(r) else ""
            h = header[ci]
            if not val or not h or low(h) == "saat":
                continue
            if isinstance(r[ci], dt.datetime):
                # Hareket dilimi: anatomy dates listed in their own column (with own time)
                ad = r[ci].date()
                ts, te = time_range(r[ci + 2] if ci + 2 < len(r) else "")
                out.append({"d": ad.isoformat(), "s": ts, "e": te, "n": "Anatomi",
                            "hoca": "", "g": "*", "y": place_for("anatomi"), "dl": dilim})
                continue
            name, hoca = split_header(h)
            name = name.replace("Şimdi Burada", "Şimdi ve Burada").replace(" Ve ", " ve ")
            out.append({"d": d.isoformat(), "s": s, "e": e, "n": name, "hoca": hoca,
                        "g": val, "y": place_for(name), "dl": dilim})
    return out


# ---------------- Haftalık amfi programı (Dönem 1 Türkçe satırları) ----------------
def amfi():
    text = open(f"{DATA}/amfi.csv", encoding="utf-8-sig").read()
    if text.startswith("## Sheet name:"):
        text = text.split("\n", 1)[1]
    rows = list(csv.reader(io.StringIO(text)))
    out, day, hdr, seen_days = [], None, None, set()
    for r in rows:
        if not r or not r[0]:
            continue
        cell0 = clean(r[0])
        md = re.match(r"(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{4})", cell0)
        if md:
            d = parse_date(cell0)
            # only the first block per date is the real weekly table; later copies are stale templates
            # the first block of consecutive days is the real weekly table; later copies are stale templates
            if d in seen_days or (seen_days and d < max(seen_days)):
                break
            seen_days.add(d)
            day = d
            continue
        if cell0.upper() == "SAAT":
            hdr = r
            continue
        if not day or not hdr:
            continue
        s, e = time_range(cell0)
        for i, c in enumerate(r[1:], 1):
            cu = clean(c).upper()
            if not re.search(r"D[ÖO]NEM\s*-?\s*1(?!\d)", cu):
                continue
            if "İNGİLİZCE" in cu and "TÜRKÇE" not in cu:
                continue
            room = clean(hdr[i]) if i < len(hdr) else ""
            room = tr_title(room)
            grp = None
            mg = re.search(r"\b([A-H])\s*-?\s*GRUBU", cu)
            if mg:
                grp = mg.group(1)
            out.append({"d": day.isoformat(), "s": s, "e": e, "r": room, "t": clean(c), "g": grp})
    if seen_days:
        a, b = min(seen_days), max(seen_days)
        week = f"{a.day}–{b.day} {MONTHS_TR[b.month-1]} {b.year}" if a.month == b.month else f"{a.day} {MONTHS_TR[a.month-1]} – {b.day} {MONTHS_TR[b.month-1]} {b.year}"
    else:
        week = ""
    return week, out


MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


# ---------------- PDÖ alt grupları (tutor + salon) ----------------
def pdo():
    import os
    f = f"{DATA}/pdo.xlsx"
    if not os.path.exists(f):
        return {}, {}
    ws = openpyxl.load_workbook(f).active
    groups, members = {}, {}
    sessions, sub, dilim = [], None, "Yaşamın Moleküler Temelleri Dilimi"
    for r in ws.iter_rows(min_row=1, values_only=True):
        b = clean(r[1]); no = clean(r[2])
        if low(b) == "grup":
            sessions = []
            for v in r[5:9]:
                if not v: continue
                d = parse_date(clean(v)); st, en = time_range(v)
                if d: sessions.append({"d": d.isoformat(), "s": st, "e": en})
            continue
        if b and re.fullmatch(r"[a-hA-H]\d", b):
            sub = b.upper()
            raw = [clean(x) for x in str(r[5] or "").split("\n") if clean(x)]
            groups[sub] = {"tutor": raw[0] if raw else "", "room": " ".join(raw[1:]), "ses": sessions}
        if sub and re.fullmatch(r"\d{6,12}", no.replace(".0", "")):
            members[no.replace(".0", "")] = sub
    return groups, members


def secmeli():
    """Elective amfi list. secmeli.xlsx (faculty table) preferred; secmeli.json accepted as a fallback."""
    fx = f"{DATA}/secmeli.xlsx"
    if os.path.exists(fx):
        ws = openpyxl.load_workbook(fx).active
        rows = list(ws.iter_rows(values_only=True))
        hdr_i = next(i for i, r in enumerate(rows) if low(clean(r[0])).startswith("dersin adı"))
        hdr = rows[hdr_i]
        date_cols = [(ci, parse_date(v)) for ci, v in enumerate(hdr) if parse_date(v)]
        hl = [low(clean(h)) for h in hdr]
        col = lambda key: next(i for i, h in enumerate(hl) if h.startswith(key))
        c_t, c_y, c_info, c_d1 = col("saati"), col("amfisi"), col("bilgi"), col("dönem1")
        out, slot = [], (None, None)
        for r in rows[hdr_i + 1:]:
            name = clean(r[0])
            if not name:
                continue
            if low(name).startswith("ingilizce tıp") or low(name).startswith("i̇ngilizce tıp") or "İNGİLİZCE TIP" == name.upper().strip():
                break  # the English-medicine section follows
            if r[c_t]:
                slot = time_range(r[c_t])
            ex = {}
            for ci, d in date_cols:
                if r[ci]:
                    ex[d.isoformat()] = clean(r[ci])
            fix = lambda t: (t.replace("Mındfulness/bilinçli", "Mindfulness / Bilinçli").replace("Araştırmanınetik", "Araştırmanın Etik")
                             .replace("Yüsek", "Yüksek").replace("Dna'dan", "DNA'dan").replace(" Ad ", " AD ").replace("Ftr ", "FTR ")
                             .replace("-fasiyal", " – Fasiyal").replace(" : ", ": "))
            out.append({"ad": fix(tr_title(name)), "hoca": tr_title(clean(r[1])), "s": slot[0], "e": slot[1],
                        "yer": fix(tr_title(clean(r[c_y]))), "bilgi": clean(r[c_info]).capitalize() if r[c_info] else "",
                        "d1": low(clean(r[c_d1])) == "var", "ex": ex})
        out.sort(key=lambda x: (x["s"] or "", x["ad"]))
        for x in out:
            slug = re.sub(r"[^a-z0-9]+", "-", low(x["ad"]).translate(str.maketrans("çğıöşüâî", "cgiosuai"))).strip("-")[:40]
            x["id"] = f"{(x['s'] or '').replace(':', '')}-{slug}"
        return out
    f = f"{DATA}/secmeli.json"
    if os.path.exists(f):
        return json.load(open(f, encoding="utf-8"))
    return None


# ---------------- change detection ----------------
def sig_sets(data, today):
    """Map key -> value text for things a student would care about, only for today and later."""
    out = {}
    for e in data.get("events", []):
        if e["d"] < today or re.match(r"(ÖĞLE ARASI|SERBEST)", e["t"]):
            continue
        out[("ders", e["d"], e["s"])] = {"txt": e["t"], "y": e.get("y", ""), "e": e["e"], "g": "*"}
    for u in data.get("uyg", []):
        if u["d"] < today:
            continue
        k = ("uyg", u["d"], u["s"], u["n"])
        out[k] = {"txt": f'{u["n"]} ({u["g"]} grubu)', "g": u["g"], "e": u["e"], "y": u["y"]}
    for x in data.get("secmeli", []) or []:
        for d, note in (x.get("ex") or {}).items():
            if d >= today:
                out[("sec", d, x["s"], x["id"])] = {"txt": f'{x["ad"]}: {note}', "g": "sec:" + x["id"], "e": x["e"], "y": x["yer"]}
    am_days = {a["d"] for a in data.get("amfi", [])}
    for a in data.get("amfi", []):
        if a["d"] < today:
            continue
        k = ("amfi", a["d"], a["s"], a["t"][:60])
        out[k] = {"txt": a["t"], "g": a["g"] or "*", "e": a["e"], "y": a["r"]}
    return out, am_days


def diff(prev, new, now):
    today = now.strftime("%Y-%m-%d")
    A, adays = sig_sets(prev, today)
    B, bdays = sig_sets(new, today)
    both_days = adays & bdays
    ch = []
    stamp = now.strftime("%Y-%m-%d %H:%M")
    for k in sorted(set(A) | set(B)):
        kind, d, s = k[0], k[1], k[2]
        if kind == "sec" and not prev.get("secmeli"):
            continue  # first time the elective list appears: nothing has "changed"
        if kind == "amfi" and d not in both_days:
            continue  # a new weekly amfi sheet is not a "change"
        a, b = A.get(k), B.get(k)
        if a == b:
            continue
        if a and b:
            typ = "mod"
        elif b:
            typ = "add"
        else:
            typ = "del"
        groups = sorted({x["g"] for x in (a, b) if x})
        ch.append({"at": stamp, "src": kind, "type": typ, "d": d, "s": s,
                   "e": (b or a)["e"], "g": groups,
                   "old": a and {"t": a["txt"], "y": a.get("y", ""), "e": a["e"]},
                   "new": b and {"t": b["txt"], "y": b.get("y", ""), "e": b["e"]}})
    # collapse a removal + addition in the same slot (e.g. a lecture renamed) into one "mod"
    return ch


def main():
    now = dt.datetime.now(TZ)
    prev = json.load(open(ARGS.prev, encoding="utf-8")) if ARGS.prev and os.path.exists(ARGS.prev) else None
    st = students()
    ev, weekly = ders()
    uy = uygulama()
    week, am = amfi()
    pg, pm = pdo()
    prev_sk = {}
    if not pg and prev:
        pg, pm = prev.get("pdoGroups", {}), prev.get("pdo", {})
        prev_sk = prev.get("sk", {})
    sec = secmeli()
    if sec is None and prev:
        sec = prev.get("secmeli")
    data = {"amfiWeek": week, "students": st, "events": ev, "weekly": weekly, "uyg": uy,
            "amfi": am, "pdoGroups": pg, "pdo": pm, "secmeli": sec or []}
    content_hash = hashlib.sha256(json.dumps({k: v for k, v in data.items() if k not in ("students", "pdo")}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    changes = list(prev.get("changes", [])) if prev else []
    if prev and prev.get("hash") != content_hash:
        new_ch = diff(prev, data, now)
        changes = new_ch + changes
        built = now.strftime("%Y-%m-%d %H:%M")
    else:
        new_ch = []
        built = prev.get("built") if prev else now.strftime("%Y-%m-%d %H:%M")
    # keep 21 days of history, drop changes for dates already past
    cutoff = (now - dt.timedelta(days=21)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    changes = [c for c in changes if c["at"][:10] >= cutoff and c["d"] >= today][:300]
    # Student lookup table: numbers are stored only as salted PBKDF2 hashes, so the published file
    # does not list student numbers. The page derives the same hash from the number the student types.
    kdf = (prev or {}).get("kdf") or {"salt": os.urandom(16).hex(), "iter": 200000}
    salt = bytes.fromhex(kdf["salt"])
    H = lambda no: hashlib.pbkdf2_hmac("sha256", no.encode(), salt, kdf["iter"]).hex()[:24]
    sk = {}
    for no in sorted(set(st) | set(pm)):
        s_ = st.get(no)
        p_ = pm.get(no)
        h = H(no)
        if p_ is None and prev_sk.get(h):
            p_ = prev_sk[h][2]  # PDÖ subgroup comes from an uploaded list that is not re-downloaded
        sk[h] = [s_[0], s_[1], p_] if s_ else [p_[0], None, p_, 1]
    # students known only from the PDÖ list (not in the main list) are carried over as they were
    for h, rec in prev_sk.items():
        if h not in sk and len(rec) > 3:
            sk[h] = rec
    pub = {k: v for k, v in data.items() if k not in ("students", "pdo")}
    pub.update({"kdf": kdf, "sk": sk})
    data = pub
    data.update({"hash": content_hash, "built": built, "lastCheck": now.strftime("%Y-%m-%d %H:%M"),
                 "schedule": ["08:00", "12:00", "18:00"], "changes": changes})
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({"changed": bool(prev) and prev.get("hash") != content_hash, "new_changes": len(new_ch),
                      "students": len(st), "events": len(ev), "uyg": len(uy), "amfi": len(am), "amfiWeek": week,
                      "pdo": len(pm), "secmeli": len(sec or [])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
