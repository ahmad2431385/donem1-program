#!/usr/bin/env bash
# Fakültenin Drive'daki (herkese açık) kaynak dosyalarını indirir.
# Kullanım: tools/fetch.sh <klasör>
set -euo pipefail
D="${1:-data}"; mkdir -p "$D"

get() { # $1 = url, $2 = hedef dosya
  curl -fsSL --retry 3 --retry-delay 5 -A "Mozilla/5.0" -o "$2" "$1"
}
is_xlsx() { [ "$(head -c 2 "$1" 2>/dev/null)" = "PK" ]; }

drive() { # zorunlu xlsx dosyası: $1 = fileId, $2 = hedef
  get "https://drive.google.com/uc?export=download&id=$1" "$2"
  is_xlsx "$2" || { echo "HATA: $2 xlsx olarak indirilemedi"; exit 1; }
  echo "indirildi: $2"
}

drive 1FcXgJIn7L9oFJKFCGLrSeefXHocrToAe "$D/ders.xlsx"
drive 1fdYXS38zxnWCoWYsFDca3bPHa0PXzKJV "$D/uyg.xlsx"
drive 1oT06DD-PRquePt2iPr-DhSwjMWX5hb_l "$D/ogrenci.xlsx"

get "https://docs.google.com/spreadsheets/d/1uCfBw8_mRI47Am2SrijTiOYP71jl1ZWatu26sXrJLJw/export?format=csv" "$D/amfi.csv"
if head -c 200 "$D/amfi.csv" | grep -qi "<html"; then echo "HATA: amfi.csv yerine HTML geldi"; exit 1; fi
echo "indirildi: $D/amfi.csv"

# İsteğe bağlı: seçmeli ders amfi programı. İndirilemezse önceki liste korunur.
if get "https://drive.google.com/uc?export=download&id=16zVYCUzAEBcb897bYcXpxYXmK9AD_BXX" "$D/secmeli.xlsx" && is_xlsx "$D/secmeli.xlsx"; then
  echo "indirildi: $D/secmeli.xlsx"
else
  rm -f "$D/secmeli.xlsx"; echo "uyarı: secmeli.xlsx indirilemedi, önceki liste korunacak"
fi
