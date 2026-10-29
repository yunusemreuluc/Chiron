---
tags: [chiron, arac]
---

# Ses Geçişi — switch_assistant (main.py)

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Chiron-Mobil]]

"Daphne'ye geç" / "Chiron'a geç" (2026-10-30). Konuşma kaldığı yerden sürer, değişen yalnız ses ve ad.

- Gemini Live'da ses bağlantı kurulurken sabitleniyor, oturum içinde değişmiyor. Bu yüzden araç
  `config.voice`'u `app_config.voice_for(ad)` ile yazar (Chiron → Algieba, Daphne → Achernar; şu anki
  ses zaten o asistanınsa, yedek ses dahil, aynen kalır), tur bitip çalan ses susunca
  (`_finish_switch`, üst sınır 6 + 8 sn) SIFIRLA'nın reconnect yolunu (`_reset_event`) tetikler.
- Bağlam: son 16 konuşma satırı (`_recent_turns`) yeni oturumun sistem komutuna `[SES DEĞİŞİMİ]`
  bloğu olarak girer; bağlanınca `HANDOFF_GREETING` proaktif mesajıyla yeni ses ilk sözü kendisi söyler.
  SIFIRLA ve ayarlardan ses değişimi bağlamı taşımaz.
- Telefon aynısını yapar: `AssistantService.switchAssistant` / `handoff`, satırlar ekrandaki sohbetten
  (`AssistantBus.lines`), `SystemPrompt.handoff`.
