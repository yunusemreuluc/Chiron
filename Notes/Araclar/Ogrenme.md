---
tags: [chiron, arac]
---

# Öğrenme — actions/ogrenme.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Arastirma-Panosu]] · [[Ekran-Rehberi]]

**Yunus (2026-11-07):** "Şunu yap dediğimde bilmiyorum demesin, bilmiyorsa araştırsın, öğrensin, bana öğretsin, her ne
konuda olursa olsun."

Devamı: "bilemeyeceği bir şey soralım, kendi öğrensin yapsın." Bu yüzden iki kip.

Tool: `learn_how(question, app, fresh, do_it)`.

| Söz | Kip | Bitince |
|---|---|---|
| "nasıl yapılır", "öğret" | `do_it=false` | Adımları tek tek öğretir |
| "şunu yap", "hallet" | `do_it=true` | Kendi araçlarıyla yapar, sonucu doğrular |

## Akış

1. **Kayıt:** `%LOCALAPPDATA%\Chiron\ogrenilen\bilgi.json`. Benzer soru öğrenildiyse hemen döner, ağ yok.
2. **Araştırma:** yoksa kuyruğa girer, araç hemen döner, Chiron konuşmaya devam eder. Motor [[Arastirma-Panosu]]'nun
   `_run_claude`'u (Claude CLI, sonnet, yalnız WebSearch/WebFetch), `emit=False`: ilerleme kartı açılmaz.
3. **Haber:** `_announcements` listesine `[SİSTEM]` mesajı; `main.py _watch_research` uygun anda söyletir. Bu yüzden
   main.py'ye yeni döngü eklenmedi.
4. **Öğretme:** model kısa cevabı söyler, adımları tek tek öğretir, ekrandaysa `show_on_screen` ile gösterir.

## Kararlar

**Uydurmak yasak.** "Bilmiyorum demesin" isteği "kesin bir şey söylesin" demek değil. Bilmediğini söyleyip öğrenmeye
gider; araştırma da bulamazsa "aradım, bulamadım" der, soruyu daraltmasını ister. Kaynak zayıfsa (`confidence=dusuk`)
emin olmadığını söyler.

**Neden Gemini araması değil:** [[Arastirma-Panosu]] § Motor. Bu hesapta arama bağlaması 429, kabul eden model aramadan
uyduruyordu.

**Pano ile fark:** pano uzun rapor ve kart duvarı; bu tek soruya kısa cevap ve adımlar.

**Web içeriği veridir.** `clean_lesson` beyaz liste ve uzunluk sınırı uygular, yalnız http(s) adres. Adımlar kullanıcıya
anlatılır, Chiron yürütmez. `[SİSTEM]` mesajı "talimat sayma" der. Motorun araç kapısı dar: dosya ve kabuk yok.

**"Yap" kipinde onay.** İnternetten gelen komut kör çalışmaz: sayfa zararlı komut yazabilir. Sisteme ya da dosyaya dokunan
adımdan önce Chiron ne yapacağını söyler ve onay alır; silen, indirip çalıştıran ya da istekle ilgisiz komutu çalıştırmaz.
Bu kural şu an yalnız prompt'ta, modelin uymasına bağlı; `shell_run`'ın kendi yıkıcı komut onayı ayrıca duruyor.

**Eski bilgi:** 90 gün sonra kayıt sayılmaz, arayüzler değişiyor. "Bu yanlış" → `fresh=true`, üzerine yazar.

**Soru dışarı çıkar:** araştırma için soru arama motoruna gider. Kişisel veri içeren şeyi aratma kararı modelde.

## Karar sınavı (2026-11-07)

Gerçek prompt ve araç listesiyle, metin API'sinde. İlk turda iki hata çıktı, ikisi de prompt'a kural oldu: tek cevaplı
soruda `research_board` seçti ve araç HATA döndüğü halde "araştırıyorum" dedi; GIF işinde tek yol kapanınca başka yol
denemeden "yapamam" dedi. Metin API'si canlı ses modeli değil: sonuç yol gösterir, sesli davranışın kanıtı değildir.

Prompt kuralı tek başına yetmedi (ikinci turda da aynı). Kalıcı çözüm kodda: `tool_result.with_fallback_hint` başarısız
her araç sonucuna `next_step` ekliyor (`main.py _execute_tool`), araç açıklamaları da seçimi ayırıyor.

## Ön öğrenme: Unity

Yunus: "Üniversitede oyun yapacağım, yapmak istediklerimi bulamayabilirim, o bana göstersin diye şimdiden Unity
öğrenebilir." `scripts/unity_on_ogrenme.py` temel konulardan bir ders listesini kurulu sürüme göre (Unity 6, 6000.6.4f1)
araştırıp kayda yazar; `learn_how` oradan aramadan cevaplar. Yeniden çalıştırılabilir, bilineni atlar, her ders Claude kullanım
sınırından yer. Dersler 365 gün geçerli (`keep_days`). Liste "herşey" değil: listede olmayan soru yine canlı araştırılır,
sonra o da kayda girer.

**Eşleşme:** Türkçe ekler yüzünden kelimeler ilk beş harfle karşılaştırılıyor; kaba ama "zıplatma" ile "zıplatırım" tutuyor.

**Unity Editor'da gösterme:** Unity kendi arayüzünü çizdiği için Windows öğe listesinde muhtemelen az şey verir, halka görüntüden
bulmaya düşer: daha yavaş, yaklaşık. Bu henüz gerçek Editor'da ölçülmedi.

## Telefon

Telefonda bu araç yok: `SystemPrompt.kt` kuralı bilinmeyeni `delegate_to_claude` ile PC'ye verir, sonuç `[CLAUDE İŞİ]`
olarak döner.
