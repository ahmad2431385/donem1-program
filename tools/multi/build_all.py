"""Dönem 2–5 verisini indirir, derler, kontrol eder; d2.json … d5.json ve ogr.json (giriş dizini) üretir.

Kullanım:
  python3 tools/multi/build_all.py --d1 out/data.json --prev . --out out [--cache DİZİN] [--only 2,3]

- Her dönem bağımsızdır: biri indirilemez/okunamaz ya da kontrolden geçemezse o dönemin önceki dosyası
  korunur, diğerleri yine yayınlanır; betik sonunda hata koduyla çıkar (GitHub sahibine haber verir).
- Öğrenci numaraları yayınlanan dosyalara açık yazılmaz: Dönem 1 ile aynı tuz ve PBKDF2 ile karma alınır.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import traceback
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from multi import common  # noqa: E402

SOURCES = {
    2: {"ogrenci": ("sheet", "1JKQHtNaOixMEVFfWKdo1vh2MKISbMaXMWQjDMl_gAAM"),
        "ders": ("sheet", "1JMxqm8dnckDKS_EVS6GFut2BDjS63khIjQEzVhAOrj8"),
        "uyg": ("sheet", "1SezCE6ZoHcNScL7Z1epqJQ9Q8B6GMFeO0ykp16Jr0rw")},
}
AMFI = ("sheet", "1uCfBw8_mRI47Am2SrijTiOYP71jl1ZWatu26sXrJLJw")


def drive_file(fid, path):
    url = f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
    with urllib.request.urlopen(urllib.request.Request(url, headers=common.UA), timeout=120) as r:
        data = r.read()
    if data[:2] != b"PK":
        raise RuntimeError(f"{fid} beklenen dosya değil (Drive erişimi?)")
    open(path, "wb").write(data)
    return path


class Src:
    """Kaynakları indirir; --cache verilirse oradaki <dönem>_<anahtar>.json / .xlsx / .docx dosyalarını kullanır."""

    def __init__(self, cache, tmp):
        self.cache, self.tmp, self.mem = cache, tmp, {}

    def get(self, donem, key, spec):
        kind, fid = spec
        name = f"d{donem}_{key}" if donem else key
        if (name, kind) in self.mem:
            return self.mem[(name, kind)]
        if kind == "sheet":
            p = self.cache and os.path.join(self.cache, name + ".json")
            val = json.load(open(p, encoding="utf-8")) if p and os.path.exists(p) else common.gsheet_download(fid)
        else:
            ext = {"xlsx": ".xlsx", "docx": ".docx"}[kind]
            p = self.cache and os.path.join(self.cache, name + ext)
            if not (p and os.path.exists(p)):
                p = drive_file(fid, os.path.join(self.tmp, name + ext))
            val = common.xlsx_grids(p) if kind == "xlsx" else common.docx_tables(p)
        self.mem[(name, kind)] = val
        return val


def first(sheets):
    return next(iter(sheets.values()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--d1", required=True, help="Dönem 1 data.json (tuz ve Dönem 1 öğrenci karmaları buradan)")
    ap.add_argument("--prev", default=".", help="önceki d2..d5.json ve ogr.json'un bulunduğu dizin")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default=None)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tmp = os.path.join(a.out, ".src")
    os.makedirs(tmp, exist_ok=True)
    now = dt.datetime.now(common.TZ)
    d1 = json.load(open(a.d1, encoding="utf-8"))
    kdf = d1["kdf"]
    salt = bytes.fromhex(kdf["salt"])
    H = lambda no: hashlib.pbkdf2_hmac("sha256", no.encode(), salt, kdf["iter"]).hex()[:24]  # noqa: E731
    prev_ogr_p = os.path.join(a.prev, "ogr.json")
    prev_ogr = json.load(open(prev_ogr_p, encoding="utf-8")) if os.path.exists(prev_ogr_p) else {"sk": {}}
    src = Src(a.cache, tmp)
    only = {int(x) for x in a.only.split(",") if x.strip()}
    import importlib
    report, failed, students = {}, [], {}
    for donem in sorted(SOURCES):
        if only and donem not in only:
            continue
        prev_p = os.path.join(a.prev, f"d{donem}.json")
        prev = json.load(open(prev_p, encoding="utf-8")) if os.path.exists(prev_p) else None
        try:
            mod = importlib.import_module(f"multi.d{donem}")
            grids = {}
            for k, spec in SOURCES[donem].items():
                v = src.get(donem, k, spec)
                grids[k] = first(v) if spec[0] == "sheet" else v  # E-Tablo: ilk sayfa; Excel/Word: hepsi
            grids["amfi"] = first(src.get(0, "amfi", AMFI))
            data, st, stats, need, warn = mod.build(grids)
            bad = [f"{k}={stats.get(k)} (en az {v})" for k, v in need.items() if (stats.get(k) or 0) < v]
            if bad:
                raise RuntimeError("kontrol başarısız: " + "; ".join(bad))
            nch = common.finish(data, prev, now)
            data["schedule"] = d1.get("schedule")
            json.dump(data, open(os.path.join(a.out, f"d{donem}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            students[donem] = st
            report[donem] = {"ok": True, **stats, "new_changes": nch, "warnings": len(warn)}
            for w in warn[:40]:
                print(f"  [D{donem}] uyarı: {w}")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            failed.append(donem)
            report[donem] = {"ok": False, "error": str(e)[:300]}
            if prev:  # önceki yayın korunur
                json.dump(prev, open(os.path.join(a.out, f"d{donem}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    # giriş dizini: karma -> {dönem: kayıt}
    sk = {}
    for h, rec in (d1.get("sk") or {}).items():
        sk.setdefault(h, {})["1"] = rec
    for donem in sorted(SOURCES):
        if donem in students:
            for no, tags in students[donem].items():
                sk.setdefault(H(no), {})[str(donem)] = tags
        else:  # bu dönem yeniden derlenemedi: önceki dizindeki kayıtları taşı
            for h, recs in prev_ogr.get("sk", {}).items():
                if str(donem) in recs:
                    sk.setdefault(h, {})[str(donem)] = recs[str(donem)]
    ogr = {"v": 1, "kdf": kdf, "sk": sk, "built": now.strftime("%Y-%m-%d %H:%M"),
           "donemler": sorted({int(k) for r in sk.values() for k in r})}
    json.dump(ogr, open(os.path.join(a.out, "ogr.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({"donemler": report, "ogr": len(sk)}, ensure_ascii=False))
    if failed:
        print("HATA: şu dönemler güncellenemedi, önceki hâlleri korundu: " + ", ".join(map(str, failed)))
        sys.exit(2)


if __name__ == "__main__":
    main()
