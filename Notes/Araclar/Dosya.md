---
tags: [chiron, arac]
---

# Dosya Arama ve Özetleme — actions/file_search.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Shell]]

İki araç, genellikle sırayla kullanılır: önce dosya bulunur, sonra içeriği
okunur.

## search_files(query, folder)

Masaüstü / Belgeler / İndirilenler klasörlerinde (veya verilen bir klasörde)
**doğal dil** sorgusuyla arar — tam dosya adı gerekmez, anlamdan yola çıkarak
en iyi eşleşenleri bulur. "rapor dosyam nerede" gibi.

## summarize_file(path, question)

Metin / kod / `.pdf` / `.docx` içeriğini okuyup Türkçe özetler. `question`
verilirse özet yerine o soruyu içerik üzerinden cevaplar.

PDF için `pypdf`, Word için `python-docx` (bkz. `requirements.txt`).

## Kalan

Taşıma/silme yok — yalnızca arama ve okuma. `Docs/FEATURES.md` içinde 🟡 olarak
izleniyor.

Tool: `search_files`, `summarize_file` ([[Arac-Tanimlari]]).
