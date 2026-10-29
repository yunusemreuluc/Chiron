---
tags: [chiron, bellek, config]
---

# Bellek ve Config — memory_manager.py + app_config.py

Bağlı: [[Home]] · [[Mimari]] · [[Arac-Tanimlari]] · [[WhatsApp]]

## app_config.py
`config/api_keys.json` dosyasını okuyup/yazan basit katman. `DEFAULT_CONFIG`:
`gemini_api_key, voice, youtube_api_key, youtube_channel_handle`.
- `load_app_config()` — dosyayı okur, eksik alanları default ile doldurur
- `save_app_config(updates)` — merge edip yazar
- `get_app_config_value(key, default)` — tek değer okuma (çoğu `actions/*.py` bunu kullanır)

`has_gemini_api_key()` 2026-08-21'de silindi — hiçbir yerden çağrılmıyordu.
Anahtarın varlığını gerçekte `backend/api/settings.py` kendi içinde ölçüyor
(`bool(str(config.get("gemini_api_key") or "").strip())`, satır ~51); elindeki
`config` sözlüğünü kullandığı için yardımcıyı çağırsa dosyayı ikinci kez okumuş
olurdu. Yani ortada tekrar değil, **ölü bir kopya** vardı.

`config/api_keys.example.json` şablon, gerçek dosya `config/api_keys.json` git'e girmemeli
(kişisel anahtar içerir).

## memory/memory_manager.py
`memory/memory.json` içine kalıcı, kategori/anahtar/değer şeklinde basit bir JSON hafıza.
- `load_memory()` / `update_memory(data)` (deep-merge) / `_write_memory()`
- `delete_memory(category, key, match_text)` — tam eşleşme veya bulanık metin eşleşmesiyle
  (`_entry_matches` — normalize edip token bazlı karşılaştırır) kayıt siler
- `format_memory_for_prompt(memory)` — hafızayı `[KULLANICI HAKKINDA BİLGİLER]` bloğu olarak
  sistem promptuna eklenecek metne çevirir ([[Mimari]] `_build_config()` içinde kullanılır)

`whatsapp_contacts` kategorisi özel formatlanır (`display_name`, `value`, `aliases`) —
bkz. [[WhatsApp]].

## memory/son_konusma.py — oturumlar arası kısa hafıza (2026-10-30)

Gemini Live oturumu her bağlanışta boş başlar. Son 20 konuşma satırı `memory/son_konusma.json`'a (gitignore)
yazılır; 12 saatten yeni olanlar yeni oturumun sistem komutuna `[ÖNCEKİ KONUŞMA]` olarak girer (ses değişiminde
devir notu yerine geçmez, onun yanına girmez). Ayrıca `_work_context()` Komuta'nın son Claude sohbetini
(`sohbet.work_context`, son 3 gün) `[SÜREN İŞ]` olarak ekler: "şunu da ekle" proje adı olmadan o işin devamı.
Telefon karşılığı `ConversationMemory.kt` (aynı uç, PC'ye ulaşılamazsa son bilinen bağlam).

## Araçlarla bağlantı
`save_memory` / `delete_memory` tool'ları ([[Arac-Tanimlari]]) doğrudan bu modülün
`update_memory` / `delete_memory` fonksiyonlarını çağırır (main.py `_execute_tool` içinde).
