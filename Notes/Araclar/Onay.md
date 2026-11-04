---
tags: [chiron, arac]
---

# Onay — Claude Code izin sorusuna Chiron'dan cevap

Bağlı: [[Arayuz]] § Oturum yörüngeleri ve Gözetim · [[PC-Isi]] · [[Ajan-Ofisi]]

2026-11-04. Yunus: "yörüngede onay bekledi geliyor ya, tıkladığımda önüme terminal gelsin, yazayım onaylayayım;
ya da sesli komutla söyleyeyim."

## Akış

1. Claude Code bir araç için izin soracakken global `~/.claude/settings.json` → `PermissionRequest` →
   `~/.claude/hooks/chiron-onay.py` çalışır (ofis-olay'ın yanında, `async` DEĞİL, `timeout: 140`).
   Yedek: `~/.claude/settings.json.bak-onay`.
2. Hook isteği `POST /api/onay/istek`'e bırakır, `GET /api/onay/{id}/bekle` ile uzun yoklama yapar.
3. Karar: Gözetim'deki **onay terminali** (`ApprovalTerminal`, oturum detayının üstünde; "Senin sıran"daki
   CEVAPLA ya da yörüngede onay bekleyen küçük çekirdeğe tıklama) ya da **ses** (`answer_approval`).
4. Hook çıktısı: izin → `{"behavior":"allow"}` (+ "bir daha sorma" seçildiyse Claude Code'un kendi
   `permission_suggestions` kuralı `updatedPermissions` olarak); red → `{"behavior":"deny","message":…}` —
   yazılan talimat Claude'a "neden reddedildi" olarak gider, yani "hayır, şunu yap" çalışır.
5. Karar yoksa hook **hiçbir şey döndürmez** → Claude Code'un kendi terminal sorusu gelir. Bu durumlar:
   Chiron kapalı · `CHIRON_CLAUDE_JOB` (Chiron'un kendi işleri, onay düzenleri ayrı) · süre doldu
   (`WAIT_S` 60 sn) · "Terminalde cevaplayacağım".

**Bilinmeyen (belgede yok):** hook beklerken terminal sorusu aynı anda görünüyor mu. Görünmüyorsa terminal
başındayken soru 60 sn'ye kadar gecikir — bu yüzden süre 120'den 60'a indirildi. Gerçek oturumda gözlenince buraya yaz.

## Ses — `answer_approval`

`actions/onay.py`, `tool_defs.py`, `core/prompt.txt` § ONAY. `decision`: izin | red | liste; `session` (proje adı,
tek bekleyen varsa boş); `message` (red talimatı); `always`; `confirm`.
**İzin iki adımlı** (shell_run gibi): `confirm=false` isteği geri okutur, kullanıcı açıkça "evet" derse `confirm=true`.
Ekrandan/bildirimden gelen metin Gemini'yi kandırsa bile tek çağrıda izin çıkmaz. Red tek adım.
Yeni istek gelince `main.py _watch_onay` (3 sn) "[SİSTEM] Onay bekliyor" ile sesli söyletir; kendisi izin vermez.

## Güvenlik

- `/istek`, `/bekle`, `/vazgec`, `/haber` yalnız yerel (`is_remote_scope`); telefon yalnız `/karar` verebilir (PIN'li).
- Komut metni ekrana gelmeden `ofis.mask`.
- Hook yalnız `127.0.0.1`/`localhost` adresine gider (`CHIRON_ONAY_URL` testi için, başka adres yok sayılır).
- Kalıcı izin uydurulmaz: yalnız Claude Code'un önerdiği kural.

## Test

`tests/test_onay.py` (8): aracı (izin/red/terminal/süre/haber), uzak kapı, hook çıktısı (izin, red, sessiz,
CHIRON_CLAUDE_JOB, Chiron yok), yörünge özeti. Uçtan uca 2026-11-04: gerçek hook + tarayıcıdaki onay terminali →
hook `deny` + yazılan mesajı üretti (38 sn).
