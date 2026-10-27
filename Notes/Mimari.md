---
tags: [chiron, mimari]
---

# Mimari — main.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Bellek-ve-Config]]

## Model
`LIVE_MODEL = "models/gemini-2.5-flash-native-audio-latest"` — Gemini Live API, gerçek zamanlı sesli
oturum. Bağlantı `main.py:781` civarında `genai.Client(api_key=..., http_options={"api_version":"v1alpha"})`
ile kurulur.

**Dil ipucu (2026-07-25)**: Kullanıcı "beni tam anlamıyla anlamıyor" dedi — `_build_config()`'teki
`SpeechConfig`'de `language_code` hiç set edilmiyordu (sadece `voice_config`), yani model dil
konusunda otomatik algılamaya bırakılıyordu. `speech_config=types.SpeechConfig(language_code="tr-TR",
voice_config=...)` eklendi — `google-genai` SDK'sının `SpeechConfig`'i bu alanı destekliyor
(`types.SpeechConfig.model_fields` ile doğrulandı). Gerçek uygulamada bağlantı test edildi, sorunsuz
bağlanıyor (`PYTHONUNBUFFERED=1` olmadan stdout redirect'i buffer'a takılıp log'un boş görünmesine
yol açabiliyor — test ederken bunu unutma). Gerçek anlama kalitesindeki iyileşme kullanıcının kendi
sesli testiyle doğrulanmalı, otomatik test edilemez.

## Ana sınıflar
- `WebcamStreamer` (main.py:47) — arka planda sürekli kare çeker, sadece en güncel JPEG'i tutar
  (queue yok). `start()/stop()/get_latest_frame()`. JPEG kalite 72, max boyut 640px.
- `ChironLive` (main.py:185) — tüm oturum yaşam döngüsünü yönetir:
  - `_build_config()` — sistem promptu ([[Arac-Tanimlari]]) + hafıza ([[Bellek-ve-Config]]) + tool
    tanımlarını birleştirip `LiveConnectConfig` oluşturur.
  - `_execute_tool(fc)` (main.py:386) — model bir function_call döndürünce burada `if name == "..."`
    zinciriyle ilgili `actions/*` fonksiyonuna yönlendirir. Yeni bir araç eklerken hem burada bir
    `elif`, hem [[Arac-Tanimlari]]'ndaki `TOOL_DECLARATIONS`, hem de `main.py` üst kısmındaki import
    eklenmeli.
  - `run()` (main.py:769) — bağlantı döngüsü; kopunca 3 deneme sessiz retry (2sn), sonrası 5sn
    aralıkla sürekli tekrar dener.

## Paralel task'lar (`run()` içinde `TaskGroup`)
- `_send_realtime()` — mikrofon verisini session'a gönderir
- `_listen_audio()` — pyaudio ile mikrofon okur (Chiron konuşurken/mute'ken göndermez)
- `_receive_audio()` — modelden gelen ses/transkript/tool_call'ları işler
- `_play_audio()` — gelen sesi çalar
- `_stream_webcam_frames()` — webcam aktifse 1.5sn'de bir en güncel kareyi session'a yollar
- `_update_ui_webcam_preview()` — UI önizlemesini ~24 FPS günceller (AI akışından bağımsız)
- `_watch_reset()` — arayüzdeki sıfırlama komutu geldiğinde `_reset_event`'i bekler, set
  edilince `_ConversationReset` fırlatır

## Sohbeti sıfırlama (reset)
Gemini Live oturumu sürekli/stateful olduğu için "sohbeti sıfırla" gerçek bir konuşma
geçmişi temizleme değil, **oturumu kapatıp yenisini açmak** anlamına gelir:
1. UI'de kullanıcı onaylayınca `ui.on_reset_command` → `ChironLive._on_reset_command()`
   çağrılır, bu da `_reset_event`'i thread-safe (`call_soon_threadsafe`) set eder.
2. `_watch_reset()` task'ı uyanır, `_ConversationReset` (main.py üst kısmında tanımlı özel
   exception) fırlatır — bu `asyncio.TaskGroup`'u kırar ve `async with` bloğundan çıkar.
3. `run()`'ın `except Exception as e:` bloğu `_is_reset_exception(e)` ile (TaskGroup
   `BaseExceptionGroup` fırlattığı için iç içe kontrol gerekir) bunu ayırt eder, normal
   hata/backoff akışına girmeden `connect_attempts` sıfırlanıp hemen yeniden bağlanılır.
4. Yeni bağlantı `_build_config()`'i tekrar çağırdığından hem sistem promptu hem de
   ([[Bellek-ve-Config]]) kalıcı hafıza aynı kalır — sadece o oturumun konuşma bağlamı
   ve arayüzdeki görünür sohbet paneli temizlenir.

## Hata/durum yönetimi
- `_result_looks_like_error()` — araç sonucundaki metne bakıp hata olup olmadığını tahmin eder
  (Türkçe anahtar kelimeler: "hata", "bulunamadı" vb.)
- `_should_play_success_sfx()` — hangi araçlarda başarı sesi çalınacağını belirler
- UI durumları: `LISTENING / THINKING / SPEAKING / ERROR / INITIALISING` — `core/web_ui.py`
  bunları 3D sahnenin durumlarına çevirir (bkz. `STATE_MAP`)

## Giriş noktası
**`main.py` giriş noktası DEĞİL** — `ChironLive` sınıfını barındıran bir kütüphane modülü.
Uygulama `desktop.py` ile başlar: FastAPI'yi arka plan thread'inde açar, `ChironLive`'ı
`core/web_ui.WebUI` adaptörüyle ayrı bir thread'de çalıştırır, WebView2 penceresini
ana thread'de gösterir. Bkz. [[Kurulum-ve-Baslatma]].

2026-07-29'a kadar burada Tkinter penceresini açan bir `main()` vardı; o arayüz
(`ui.py`, 3108 satır) ve çift alkış uyandırma (`wakeup_listener.py`) tamamen kaldırıldı.
