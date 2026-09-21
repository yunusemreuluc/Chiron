# Açık Konular

Tek oturumda bitmeyen, arkası gelen işler. `Docs/YAPILACAKLAR.md` *ne
yapılacağını* tutuyor; burası *neyin ortasında olduğunu* tutuyor.

`.claude/hooks/session_start.py` yalnızca `## Açık` altındaki `###` başlıklarını
ve `**Durum:**` satırlarını okuyor — gövde metni context'e girmiyor, o yüzden
durumu tek satırda özetle. Biten konuyu `## Kapanmış` altına taşı.

## Açık

### Arabada ses yolu — SCO yerine A2DP
**Durum:** Kod yazıldı ve telefona kuruldu (2026-09-21), gerçek arabada denenmedi
Toyota C-HR eller serbest hattından sonra müziğe dönmüyordu; varsayılan artık SCO'suz
(ses medya akışından, mikrofon telefonda). Ayrıntı ve ölçülecekler: [[Airon-Mobil]]
§ 2026-09-21. Ölçüm kötüyse Ayarlar → Araba → "Telefon hattı kullan".

### Aıron Mobil — Android uygulaması
**Durum:** Faz 1 derlendi (2026-09-15) — telefona kurulup gerçek cihazda denenmedi; Faz 2 "Hey Aıron" bekliyor
Ayrıntı: [[Airon-Mobil]]. Kullanıcı web arayüzünü istemedi; Siri gibi sesle konuşup
arama/WhatsApp/PC sorgusu yapan yerel uygulama istedi.

### Mobil erişim — telefondan Aıron
**Durum:** Canlıda (2026-09-15) — Tailscale kurulu, serve 8001'de, proxy arkası ölçüldü; telefonla ilk PIN girişi bekleniyor
Ayrıntı ve kurulum adımları: [[Uzaktan-Erisim]]. Eski 5 engelin hepsi kapandı:
HOST yerine ayrı port (8001) + `tailscale serve`, WS adresi `window.location`'dan,
telefon görünümü `frontend/app/m`, PIN kapısı, uzak mod (PC hoparlörü + mikrofon
kapalı). Kalan: (1) gerçek `tailscale serve` altında uzak sınıflandırmanın
ölçülmesi, (2) Faz C telefon mikrofonu, (3) kilit ekranına push bildirim.

**Hedef senaryo (2026-09-11, kullanıcının kendi cümlesi):** "PC açık, dışarı
çıktım, telefondan Aıron'a diyeceğim ki PC'deki şu uygulama bitti mi ne oldu, o
da PC'me bakıp cevap verecek."

### Süreklilik hook'larının canlı doğrulaması
**Durum:** Hook'lar kurulu, elle test edildi, gerçek oturumda görülmedi
İlk açılışta context enjeksiyonunun geldiğini gör; geldiyse bu konuyu kapat.

## Kapanmış

<!-- Parser bu başlıkta durur. -->
