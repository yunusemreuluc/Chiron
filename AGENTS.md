# CHIRON — Codex Kuralları

Global `~/.codex/AGENTS.md` bu projede de geçerlidir: **Codex küçük ve tanımlı işleri yapar, büyük işler Claude'a aittir.**
Aşağıdakiler bu projeye özeldir ve globalin üstüne biner.

## Proje

Python masaüstü + web tabanlı AI ortamı. Giriş noktaları: `desktop.py`, `main.py`.
`main.py` ve `tool_defs.py` çok büyük dosyalar — içlerinde geniş değişiklik yapma.

## Bu projede DOKUNMA

- **`Notes/`, `Docs/`, `.obsidian/`** — bunlar kullanıcının Obsidian vault'u. Claude yönetir, sen yazma.
- **UI ve tasarım kodu** (`frontend/`, arayüz stilleri) — tasarım kararları Claude'a ait.
  Bu projenin açık kuralı: arayüz asla sadeleştirilmez, genel/jenerik hale getirilmez.
  "Daha basit yaparım" diye düşünüyorsan dur.
- **`venv/`, `weights/`, `*.pt`, `__pycache__/`** — üretilmiş veya indirilmiş içerik.
- **`core/prompt.txt`** — model davranışını değiştirir, küçük iş değildir.

## Yeni tool ekleme = YAPMA

Bu projede yeni bir tool eklemek dört ayrı yerde değişiklik gerektirir
(fonksiyon + `@register_tool`, `tool_defs.py` içindeki `TOOL_DECLARATIONS`,
`core/prompt.txt`, ve `Notes/Araclar/` altında bir sayfa).
Bu tanımı gereği büyük iştir. Başlama, Claude'a bırak.

## Uygun işler

- Tek fonksiyonluk bug düzeltme
- Type hint ekleme, `pyrightconfig.json` uyarılarını giderme
- Formatlama, kullanılmayan import temizliği
- `requirements.txt` okuma/kontrol (değiştirme değil)
- Var olan bir desene bakarak küçük yardımcı fonksiyon yazma

## Dil

Kod içindeki Türkçe isimleri ve yorumları koru, İngilizceye çevirme.

## Git

Bu repoda commit/push kesinlikle yok — global kural burada da geçerli.
Çalışma anında commit edilmemiş değişiklikler olabilir; onlara dokunma.
