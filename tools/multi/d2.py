"""Dönem 2 Türkçe: öğrenci listesi (grup A–H, alt grup a1/a2), ders programı, uygulama tablosu, amfi."""
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


def build(src):
    """src: {'ogrenci': ızgara, 'ders': ızgara, 'uyg': ızgara, 'amfi': ızgara}"""
    st = students(src["ogrenci"])
    ev = ders_rows(src["ders"])
    uy, warn = uygulama(src["uyg"])
    week, am = amfi_rows(src["amfi"], 2)
    data = {"v": 1, "donem": 2, "amfiWeek": week, "events": ev, "uyg": uy, "amfi": am,
            "groups": {"g": GROUPS}}
    stats = {"students": len(st), "events": len(ev), "uyg": len(uy), "amfi": len(am)}
    need = {"students": 300, "events": 900, "uyg": 100}
    return data, st, stats, need, warn
