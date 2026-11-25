"""Dönem 2 Türkçe: öğrenci listesi (grup A–H, alt grup a1/a2), ders programı, uygulama tablosu, amfi."""
import datetime as dt
import json
import os
import re
from .common import cell, clean, low, up, tr_title, parse_date, time_range, norm_no, ders_rows, amfi_rows

GROUPS = list("ABCDEFGH")


def students(grid):
    out = {}
    for r in grid:
        no = norm_no(cell(r, 2))
        g = up(cell(r, 0))
        if no and g in GROUPS:
            a = low(cell(r, 1))
            out[no] = [g] + ([a] if re.fullmatch(r"[a-h][12]", a) else [])
    return out


def _groups_in(v):
    """'A' · 'AB' · 'ABCD 2/1' · 'A-B Grubu' · 'EFGH 1/2' -> ['A','B',...]"""
    toks = re.split(r"[\s,+\-/]+", up(re.sub(r"\(.*?\)", " ", v)))
    out = []
    for t in toks:
        if re.fullmatch(r"[A-H]{1,8}", t):
            out += list(t)
    return sorted(set(out))


def _name(n):
    n = clean(re.sub(r"\(\s*\d+\s*\)", "", n))
    n = re.sub(r"\s+\d+$", "", n)
    if re.search(r"(?i)sınav", n):
        n = re.sub(r"(?i)\s*sınav.*$", "", n) + " Uygulama Sınavı"
    return n


def _place(p):
    p = clean(p)
    if not p or "web sitesinde" in low(p) or low(p) == "uygulama":
        return ""
    if up(p) == "AMFİ":
        return "Amfi programına bak"
    return p


def uygulama(grid):
    out, warn = [], []
    dilim, sess, in_block = "", None, False
    for i, r in enumerate(grid):
        vals = [cell(r, j) for j in range(len(r))]
        nonempty = [v for v in vals if v]
        if not nonempty:
            in_block = False
            continue
        a = vals[0]
        if len(nonempty) >= 3 and len(set(nonempty)) == 1 and not low(a).startswith("dönem 2 dikey"):
            dilim = tr_title(re.sub(r"\s*-\s*(\d)$", r" \1", clean(a)))
            in_block = False
            continue
        if low(a).startswith("uygulama adı"):
            sess = {}
            for j in range(2, len(vals)):
                d = parse_date(vals[j])
                s, e = time_range(vals[j])
                if d:
                    sess[j] = (d.isoformat(), s, e)
            in_block = bool(sess) or low(vals[1] if len(vals) > 1 else "").startswith("uygulama yeri")
            continue
        if not in_block or not a or a.endswith(":") or not any(vals[2:]):
            if a.endswith(":") or (a and not any(vals[2:])):
                in_block = False
            continue
        name, place = _name(a), _place(vals[1] if len(vals) > 1 else "")
        if low(name).startswith("anatomi"):
            continue  # anatomi tarihleri ders programında tüm sınıfa ayrıca yer alıyor
        star_cols = []
        for j in range(2, len(vals)):
            v = vals[j]
            if not v or v in ("-", "–") or re.fullmatch(r"[\d.:\s\-–]+", v):
                continue
            d, s, e = sess.get(j, (None, None, None))
            if not d or "TÜM" in up(v):
                dd = parse_date(v)
                ts, te = time_range(v)
                if dd:
                    d, s, e = dd.isoformat(), ts or s, te or e
            if not d:
                warn.append(f"uyg satır {i+1}: '{name}' sütun {j+1} tarihsiz: {v[:30]}")
                continue
            if v.strip() == "*":
                star_cols.append((j, d, s, e))
                continue
            g = ["*"] if "TÜM" in up(v) else _groups_in(v)
            if not g:
                warn.append(f"uyg satır {i+1}: '{name}' sütun {j+1} grup okunamadı: {v[:30]}")
                continue
            out.append({"d": d, "s": s, "e": e, "n": name, "hoca": "", "g": g, "y": place, "dl": dilim, "_c": (i, j)})
        for j, d, s, e in star_cols:
            out.append({"d": d, "s": s, "e": e, "n": name, "hoca": "", "g": ["*rest"], "y": place, "dl": dilim, "_c": (i, j)})
    # '*' = o oturumda başka uygulamaya yazılmamış gruplar
    taken = {}
    for u in out:
        if u["g"] != ["*rest"]:
            for g in (GROUPS if u["g"] == ["*"] else u["g"]):
                taken.setdefault((u["d"], u["s"]), set()).add(g)
    for u in out:
        if u["g"] == ["*rest"]:
            rest = [g for g in GROUPS if g not in taken.get((u["d"], u["s"]), set())]
            u["g"] = rest if len(rest) < len(GROUPS) else ["*"]
        u.pop("_c", None)
    seen, uniq = set(), []
    for u in out:
        k = (u["d"], u["s"], u["n"], tuple(u["g"]))
        if k not in seen:
            seen.add(k)
            uniq.append(u)
    return uniq, warn


# ---------------- Dikey Koridor II uygulama takvimi (konu, hoca, yer ve grup) ----------------
AYLAR = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
         "eylül": 9, "eylü": 9, "ekim": 10, "kasım": 11, "aralık": 12}
GUNLER = ["pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi", "pazar"]
GENEL_DK = ("Beceri", "Dikey Koridor II")   # uygulama tablosunda konu yazılmadan geçen Dikey Koridor oturumları


def dikey(grid):
    """Satır: oturum ('1/1\\n7 Eylül 2026 Pazartesi\\n08:30-10:20'); sütun: konu ('Onam Alma\\nProf. Dr. …\\nYeri');
    hücre: grup(lar) ('E', 'AB') ya da 'Telafi (Tüm Gruplar)'. Yıl, akademik yıla göre düzeltilir (Eylül–Aralık 2026, Ocak–Haziran 2027)."""
    warn, out = [], []
    if not grid:
        return out, warn
    heads = {}
    for j, v in enumerate(grid[0]):
        if j and v and clean(str(v)):
            parts = [clean(x) for x in str(v).split("\n") if clean(x)]
            heads[j] = parts
    for i, r in enumerate(grid[1:], 2):
        a = str(r[0]) if r and r[0] else ""
        if not a:
            continue
        t = low(a)
        m = re.search(r"(\d{1,2})\s+([a-zçğıöşü]+)\s+\d{4,5}", t)
        tm = re.search(r"(\d{1,2})[:.](\d{2})\s*-\s*(\d{1,2})[:.](\d{2})", t)
        vals = {j: clean(str(r[j])) for j in heads if j < len(r) and r[j] not in (None, "") and clean(str(r[j]))}
        vals = {j: v for j, v in vals.items() if v != clean(a)}   # birleşik satır ('TÜM GRUPLAR …') konu belirtmiyor
        if not vals:
            if "tüm gruplar" in t:
                warn.append(f"dikey satır {i}: tüm gruplar oturumu, konu yazılmamış; atlandı")
            continue
        mon = AYLAR.get(m.group(2)) if m else None
        if not (m and mon and tm):
            warn.append(f"dikey satır {i}: tarih/saat okunamadı: {a[:40]!r}")
            continue
        d = dt.date(2026 if mon >= 9 else 2027, mon, int(m.group(1)))
        gun = next((g for g in GUNLER if g in t), None)
        if gun and GUNLER[d.weekday()] != gun:
            warn.append(f"dikey satır {i}: {d} {GUNLER[d.weekday()]}, belgede '{gun}' yazıyor (tarih esas alındı)")
        s, e = f"{int(tm.group(1)):02d}:{tm.group(2)}", f"{int(tm.group(3)):02d}:{tm.group(4)}"
        for j, v in vals.items():
            h = heads[j]
            g = ["*"] if "TELAF" in up(v) or "TÜM" in up(v) else sorted(set(c for c in up(v).replace(" ", "") if c in GROUPS))
            if not g:
                warn.append(f"dikey satır {i}: grup okunamadı: {v[:30]!r}")
                continue
            out.append({"d": d.isoformat(), "s": s, "e": e, "konu": h[0], "hoca": h[1] if len(h) > 1 else "",
                        "y": _dk_yer(h[2]) if len(h) > 2 else "", "g": g, "telafi": "TELAF" in up(v)})
    return out, warn


def _dk_yer(p):
    return "Amfi programına bak" if "AMFİ PROGRAM" in up(p) else _place(p)


def dikey_enrich(uy, atamalar, warn):
    """Uygulama tablosundaki konusuz Dikey Koridor oturumunu, o gruba atanmış konuyla (hoca ve yeriyle) değiştirir."""
    for a in atamalar:
        ayni = [u for u in uy if u["d"] == a["d"] and u["s"] == a["s"]]
        dl = next((u.get("dl", "") for u in ayni if u.get("dl")), "")
        if a["telafi"]:
            uy.append({"d": a["d"], "s": a["s"], "e": a["e"], "n": f"Dikey Koridor II · {a['konu']} (telafi)", "hoca": a["hoca"],
                       "g": ["*"], "y": a["y"], "dl": dl})
            continue
        for g in a["g"]:
            gen = next((u for u in ayni if u["n"] in GENEL_DK and (g in u["g"] or u["g"] == ["*"])), None)
            if gen:
                gen["g"] = [x for x in (GROUPS if gen["g"] == ["*"] else gen["g"]) if x != g]
                dl = gen.get("dl") or dl
            elif any(g in u["g"] or u["g"] == ["*"] for u in ayni):
                warn.append(f"dikey {a['d']} {a['s']} {g}: tabloda bu saatte grubun başka uygulaması var ({a['konu']} yine eklendi)")
        uy.append({"d": a["d"], "s": a["s"], "e": a["e"], "n": f"Dikey Koridor II · {a['konu']}", "hoca": a["hoca"],
                   "g": a["g"], "y": a["y"], "dl": dl})
    return [u for u in uy if u["g"]]


# ---------------- Anatomi uygulaması: grup (1–3) saatleri, öğrencinin salonu ve masası ----------------
ANATOMI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "d2_anatomi.json")


def anatomi_static():
    try:
        return json.load(open(ANATOMI, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def anatomi_events(ev, prog, warn):
    """Programdaki 'DİSEKSİYON' satırları (aynı gün, aynı saat) yalnız o saatin anatomi grubuna gösterilir.
    'an:?' = salon listesinde olmayan öğrenciler: üç saati de görmeye devam eder."""
    for p in prog:
        hit = [e for e in ev if e["d"] == p["d"] and e["s"] == p["s"] and ("DİSEK" in up(e["t"]) or "ANATOM" in up(e.get("y", "")))]
        if not hit:
            warn.append(f"anatomi {p['d']} {p['s']}: programda diseksiyon satırı yok")
        for e in hit:
            e["g"] = [f"an:{p['grup']}", "an:?"]
            e["an"] = 1


def anatomi_tags(h, ogr):
    """Öğrencinin (karma) anatomi etiketleri: ['an:2', 'anyer:1.3'] ya da listede yoksa ['an:?']."""
    v = (ogr or {}).get(h)
    if not v:
        return ["an:?"]
    g, s, m = v.split(".")
    return [f"an:{g}", f"anyer:{s}.{m}"]


def build(src):
    """src: {'ogrenci': ızgara, 'ders': ızgara, 'uyg': ızgara, 'amfi': ızgara}"""
    st = students(src["ogrenci"])
    ev = ders_rows(src["ders"])
    uy, warn = uygulama(src["uyg"])
    dk = src.get("dikey")
    if dk:
        sheet = dk.get("TR") or next(iter(dk.values()))
        atamalar, w = dikey(sheet)
        warn += w
        uy = dikey_enrich(uy, atamalar, warn)
    an = anatomi_static()
    if an:
        anatomi_events(ev, an["program"], warn)
    week, am = amfi_rows(src["amfi"], 2)
    data = {"v": 1, "donem": 2, "amfiWeek": week, "events": ev, "uyg": uy, "amfi": am,
            "groups": {"g": GROUPS}}
    stats = {"students": len(st), "events": len(ev), "uyg": len(uy), "amfi": len(am)}
    need = {"students": 300, "events": 900, "uyg": 100}
    return data, st, stats, need, warn
