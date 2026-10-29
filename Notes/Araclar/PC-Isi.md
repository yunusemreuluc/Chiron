---
tags: [chiron, arac]
---

# PC'de iş — `delegate_to_pc`

Bağlı: [[Ajan-Ofisi]] § Komuta ekranı · [[Chiron-Mobil]] § 2026-10-29

**Ne:** Sesli Chiron'a "Dilcep'te alt barı değiştir", "hesap kısmını geliştir" denince işi Komuta'daki son Claude
sohbetine yazar (aynı oturum sürer, ekranda Komuta'da adım adım görünür). Telefondaki `delegate_to_claude`'un
PC karşılığı.

**Neden (2026-10-29):** Yunus "telefonda iş verince yapmıyordu, PC'de de öyle değil mi" dedi — PC'deki sesli
Chiron'un iş verme aracı hiç yoktu.

**Nasıl:** `actions/pc_isi.py` → `POST http://127.0.0.1:8000/api/remote/komuta {text, new_topic}`. Yerel istek
olduğu için uç `via="pc"` yazar (origin `sohbet`, telefona bildirim gitmez); telefondan gelen aynı uç
`sohbet_tel`. `backend.core.sohbet` import EDİLMEZ: ikinci bir iş kuyruğu kurulur, diskteki süren işleri
"yarıda kaldı" yapardı.

**Prompt kuralı (`core/prompt.txt` § PC'DE İŞ):** ilk iş aracı çağırmak; soru/onay/netleştirme yok; "hallediyorum"
ancak `success=true`'dan sonra; Claude'dan söz edilmez. Telefonda aynı hata yaşandı: model "Hemen hallediyorum"
deyip aracı çağırmadan netleştirme sorusu sordu.

**Bitince sesli haber (2026-10-29):** `delegate_to_pc` iş kimliğini `_pending`'e koyar; main.py `_watch_pc_jobs` 10 sn'de
bir `finished_announcements()` ile bakar, biten işi `[SİSTEM] PC işi sonucu` olarak Gemini'ye verir (birinci ağızdan,
Claude'suz). Chiron konuşurken/duraklıyken bekler. Yalnız sesle verilen işler; bellekte (yeniden başlatmada düşer). Testler `tests/test_pc_isi.py`.
