"""Sınav kuralları ve ders kredisi dosyalarını izler (Dönem 1–5).

Bu dosyalar programı değil, Sınav·Not sayfasındaki hesaplama kurallarını ve kredileri besler; o yüzden
otomatik işlenmez, elle gözden geçirilir. Betik her çalıştığında hepsini indirir:
  - açılamayan dosya varsa  -> çıkış kodu 3 (iş başarısız görünür, GitHub e-posta atar)
  - içeriği değişen varsa    -> yeni özetler kaydedilir, çıkış kodu 4 (bir kez haber verilir)
  - hepsi aynıysa            -> 0

Kullanım: python3 tools/watch.py --state tools/watch.json --out out/watch.json
"""
import argparse
import hashlib
import html
import json
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}
DRIVE = "https://drive.usercontent.google.com/download?id={}&export=download&confirm=t"
DOC = "https://docs.google.com/document/d/{}/mobilebasic"
FILES = [
    # (anahtar, açıklama, tür, kimlik/adres)   tür: file = Drive'a yüklenmiş dosya, doc = Google Doküman, url = doğrudan adres
    ("d1_kredi", "Dönem 1 ders kredileri", "doc", "1saVjyvmWIgWBKupFP_AMM1ci3b9cV2pzWbzvkGgLAa4"),
    ("d1_kural", "Dönem 1 sınav kuralları", "file", "1JDSmobsH28_ES8nhLmIeN8iwIvP2_BSz"),
    ("d2_kredi", "Dönem 2 ders kredileri", "doc", "1QXtQAkRzbdWfWizpJ6sVdaNmyXSQPW8E_ow2WA6z0Lg"),
    ("d2_kural", "Dönem 2 sınav kuralları", "url", "https://cdn.istanbul.edu.tr/FileHandler2.ashx?f=donem-2-sinav-kurallari-2026-2027.pdf"),
    ("d3_kredi", "Dönem 3 ders kredileri", "file", "1TX3iGDpmdUgJ-2BKuc8h-EkjynL9FYJo"),
    ("d3_kural", "Dönem 3 sınav kuralları", "url", "https://cdn.istanbul.edu.tr/FileHandler2.ashx?f=donem-3-olcme-ve-degerlendirme-kurallari-2026-2027.pdf"),
    ("d4_kredi", "Dönem 4 ders kredileri", "file", "1HLd9a646kWohk7R6c4MA07ugNHssqzP6"),
    ("d4_kural", "Dönem 4 sınav kuralları", "file", "1EmID9yoRtcAJpEChD18f2PJGM3PsCBLm"),
    ("d5_kredi", "Dönem 5 ders kredileri", "file", "1ZfZT8w3y85B0yjDQB5MSEq8TRqYZUWaF"),
    ("d5_kural", "Dönem 5 sınav kuralları", "file", "1JhKaAzVJyXUbykbQU5bzvANwFN1AdCYo"),
]


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
        return r.read()


def doc_text(raw):
    """Google Doküman sayfasından yalnızca görünen metin (sayfa kodundaki değişken parçalar özetleri bozmasın)."""
    s = raw.decode("utf-8", "replace")
    m = re.search(r"<body[^>]*>(.*)</body>", s, re.S)
    s = m.group(1) if m else s
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s, flags=re.S | re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()


def fingerprint(kind, ref):
    if kind == "doc":
        txt = doc_text(get(DOC.format(ref)))
        if len(txt) < 200:
            raise RuntimeError("doküman metni okunamadı")
        return hashlib.sha256(txt.encode()).hexdigest()[:20], len(txt)
    data = get(DRIVE.format(ref) if kind == "file" else ref)
    if data[:4] != b"%PDF" and data[:2] != b"PK":
        raise RuntimeError("beklenen PDF/Word/Excel dosyası gelmedi (erişim kapalı olabilir)")
    return hashlib.sha256(data).hexdigest()[:20], len(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        state = json.load(open(a.state, encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    new, bad, changed = dict(state), [], []
    for key, label, kind, ref in FILES:
        try:
            h, size = fingerprint(kind, ref)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{label}: {str(e)[:120]}")
            continue
        old = (state.get(key) or {}).get("hash")
        if old and old != h:
            changed.append(label)
        new[key] = {"hash": h, "size": size, "ad": label}
        print(f"tamam: {label} ({size} bayt)")
    json.dump(new, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    if bad:
        print("HATA: şu dosyalar açılamadı: " + "; ".join(bad))
    if changed:
        print("DEĞİŞTİ (Sınav·Not kuralları/kredileri gözden geçirilmeli): " + ", ".join(changed))
    sys.exit(3 if bad else 4 if changed else 0)


if __name__ == "__main__":
    main()
