---
tags: [chiron, altyapi]
---

# Yerel Model — Ollama

Bağlı: [[Home]] · [[Mimari]] · [[Bilinen-Tuzaklar]] · [[Dosya]] · [[Arayuz]]

> **KALDIRILDI (2026-08-01).** Ollama ve `qwen2.5:7b` kurulup ölçüldü, sonra
> kullanıcı isteğiyle makineden tamamen silindi (~7.1 GB geri alındı).
>
> **Sebep:** kurulumun amacı Gemini kota sorununu çözmekti, ama ölçüm asıl
> sebebin başka olduğunu gösterdi — kotayı yakan şey araç çağrıları değil,
> 25 saniyede bir görü çağrısı atan ekran bekçisiydi
> ([[Bilinen-Tuzaklar]] § Kotayı yakan şey araçlar değil). Bekçi düzeltilince
> tüketim %96'dan %3'e indi ve yerel modele gerek kalmadı.
>
> **Bu not neden duruyor:** ölçümler gerçek zamana mal oldu ve yerel model
> tekrar gündeme gelirse (ajan çalışma zamanı) baştan yapılmaları gerekirdi.
> Aşağıdaki her sayı bu makinede ölçüldü.

Kurulan sürüm: **Ollama 0.32.5**, model **`qwen2.5:7b`** (4.7 GB).

## Ollama Gemini'yi KALDIRMAZ — metin yarısını alır

Beklentiyi baştan doğru kurmak önemli, çünkü ilk düşünce "kotadan kurtulduk"
oluyor. İki şeyin yerel karşılığı **yok**:

1. **Gemini Live ses oturumu** — Chiron'un kalbi, gerçek zamanlı sesten sese.
   Ollama metin üretir, konuşmaz.
2. **Hassas ekran konumlandırma** — [[Ekran-Mudahale]] "şu düğmeyi bul, piksel
   koordinatını ver" istiyor ve [[Otonom-Duzeltme]] buna bağlı. Yerel görü
   modelleri bu işte belirgin zayıf; yanlış koordinat = yanlış yere tıklama.

Yerele taşınabilecekler saf metin işleri: `summarize_file`, `search_files`,
günlük brifing metni, aktivite günlüğü analizi, planlanan semantik hafıza
araması ve arka plan ajanları.

**Gizlilik kazancı küçük değil:** `summarize_file` şu an dosya içeriğini
Google'a gönderiyor, `activity_log.json` gerçek konuşmaları tutuyor.

## Donanım ve yerleşim (RTX 4050 Laptop, 6 GB VRAM)

`num_ctx` **doğrudan** GPU yerleşimini ve hızı belirliyor — çünkü KV önbelleği
VRAM'den yer yiyor. Ölçüldü (aynı prompt, `auto_fix.py` özeti):

| `num_ctx` | Üretim | Yerleşim |
|---|---|---|
| 2048 | 26.4 tok/sn | %16 CPU / %84 GPU |
| **4096** | **24.8 tok/sn** | %18 CPU / %82 GPU |
| 8192 | 22.0 tok/sn | %24 CPU / %76 GPU |
| 32768 (varsayılan) | 14.9 tok/sn | %39 CPU / %61 GPU |

**Varsayılanı kullanmak %40 hız kaybettiriyor.** Chiron'un prompt'ları ~2100
token; 32K bağlam gereksiz ve zararlı. Seçilen değer **4096**: 2048'in kazancı
1.6 tok/sn ile marjinal, ama uzun dosyalarda kırpılma riski getiriyor.

6 GB'da 7B model **hiçbir ayarda tam GPU'ya sığmıyor** (2048'de bile %16 CPU).
Kabul edilebilir: 24.8 tok/sn ile 3-5 cümlelik özet ~6 saniyede geliyor.

## 3D sahneyle çekişme — YOK (ölçüldü)

Endişe mantıklıydı: model 4.1 GB VRAM tutuyor, sahne de aynı GPU'da. Aynı
oturumda A/B yapıldı (farklı günlerde ölçmek anlamsız — [[Bilinen-Tuzaklar]]
§ Kare hızı ölçümü kendi kendini doğrulamalı):

| | Model yüklü | Model düşük |
|---|---|---|
| Yoğun ortalama FPS | 90.8 | 90.3 |
| Kare süresi p50 | 10.8 ms | 10.8 ms |
| 16.7 ms bütçesini aşan | %0.4 | %0.7 |

Fark gürültü içinde. WebGL sahnesinin VRAM ayak izi küçük (birkaç shader, ufak
geometri, büyük doku yok) ve model boştayken GPU'da iş yapmıyor.

**Uyarı:** ilk ölçüm modelin yüklü olduğu turda 90.8 FPS verdi ve bu dünkü
68.8/77.6 taban değerinin ÜSTÜNDEYDİ — yani makine o gün daha yüklüydü, taban
karşılaştırılabilir değildi. Aynı oturumda A/B yapılmasaydı "model FPS'i
artırıyor" gibi saçma bir sonuç çıkacaktı.

## Türkçe kalitesi — gerçek işle test edildi

Sentetik soru sorulmadı: `summarize_file`'ın **birebir kendi prompt'u** gerçek
proje dosyalarında çalıştırıldı.

- **Kasa notu özeti** ([[Otonom-Duzeltme]]) — doğru ve derli toplu.
- **İçerikten soru** ("kaç güvenlik kapısı var?") — **üçünü de doğru saydı ve
  doğru açıkladı.** Kodu gerçekten okuyor.
- **Olmayan bilgi** ("veritabanı bağlantısı nasıl kuruluyor?") — **"yoktur"
  dedi, uydurmadı.** En kritik test buydu: uyduran bir model `summarize_file`'ı
  Gemini'den kötü değil TEHLİKELİ yapardı, çünkü yanlış cevap emin bir tonla
  gelir ([[Bilinen-Tuzaklar]] § Arayüzde dürüstlük).

**Ama kusursuz değil:** uzun bir kod dosyası özetinde (`ambient_context.py`)
sonuna uydurma bir cümle ekledi ("bilgiler her oturumda yeniden alınıyor,
böylece veri aktarımının engellenmesi amaçlanmaktadır" — kaynakta böyle bir şey
yok). Yani kod özetlerinde ara sıra süsleme yapıyor; not/soru-cevap işlerinde
görülmedi.

## Kurulum

```
winget install --id Ollama.Ollama --silent
ollama pull qwen2.5:7b
```

**İndirme koparsa:** `Error: unexpected EOF` alındı (%36'da, 23 MB/s giderken —
bant genişliği değil bağlantı sorunu). Ollama kısmi indirmeyi **sürdürüyor**,
komutu tekrar çalıştırmak yeterli; ikinci denemede tamamlandı.

## Model seçimi neden Qwen

Türkçe belirleyici oldu. Açık modellerin Türkçesi eşit değil: Qwen2.5 ve Gemma
iyi, Llama 3.1 daha popüler ama Türkçesi belirgin zayıf. Chiron baştan sona
Türkçe konuşuyor.
