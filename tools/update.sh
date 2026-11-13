#!/usr/bin/env bash
# Kaynakları derleyip out/data.json üretir ve yayından önce kontrol eder.
# Kullanım: tools/update.sh <veri klasörü> <önceki data.json> <çıktı>
set -euo pipefail
D="$1"; PREV="$2"; OUT="$3"; mkdir -p "$(dirname "$OUT")"

build() { python3 tools/build.py --data "$D" --prev "$PREV" --out "$OUT" | tail -1; }
LINE="$(build)"; echo "$LINE"

# Seçmeli dosyası bozuk/eksik okunduysa onu atıp önceki listeyle bir kez daha derle.
SEC="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("secmeli",0))' "$LINE")"
if [ "$SEC" -lt 20 ] && [ -f "$D/secmeli.xlsx" ]; then
  echo "uyarı: seçmeli sayısı $SEC, secmeli.xlsx olmadan yeniden derleniyor"
  rm -f "$D/secmeli.xlsx"; LINE="$(build)"; echo "$LINE"
fi

python3 - "$LINE" "$OUT" <<'PY'
import json, sys
s = json.loads(sys.argv[1]); d = json.load(open(sys.argv[2], encoding="utf-8"))
need = {"students": 300, "events": 900, "uyg": 300, "secmeli": 20}
bad = [f"{k}={s.get(k)} (en az {v})" for k, v in need.items() if (s.get(k) or 0) < v]
if len(d.get("sk") or []) < 300: bad.append(f"sk={len(d.get('sk') or [])} (en az 300)")
if "students" in d: bad.append("çıktıda 'students' anahtarı var")
if bad:
    print("KONTROL BAŞARISIZ, yayın yapılmayacak: " + "; ".join(bad)); sys.exit(1)
print(f"Kontrol tamam. Yeni değişiklik: {s.get('new_changes')} · Amfi haftası: {s.get('amfiWeek')}")
PY
