# Dönem 1 Programım

İstanbul Tıp Fakültesi Dönem 1 Türkçe öğrencileri için kişisel ders programı sayfası.

**Adres:** https://itfdonembirturkcedersprogram.netlify.app (Netlify, bu depodan otomatik yayınlanır) Öğrenci numarasını giren öğrenci kendi amfi derslerini, uygulamalarını, PDÖ oturumunu ve seçmeli derslerini görür.

**Resmi değildir.** Veriler fakültenin yayımladığı programlardan günde dört kez (03:35, 07:30, 12:00, 15:00 civarı) otomatik alınır. Şüphede kalınca asıl programlara bakın.

- `index.html` – sayfa
- `data.json` – birleştirilmiş program verisi (öğrenci numaraları yalnızca tek yönlü karma olarak bulunur, isim yoktur)
- `desc.json` – ders açıklamaları
- `tools/build.py` – kaynak tablolardan `data.json` üreten betik
