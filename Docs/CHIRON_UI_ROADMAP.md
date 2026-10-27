# CHIRON UI — Kalan İşler

Bu dosya 17 fazlık bir plan olarak başladı. **Tamamlanan fazlar 2026-07-29'da silindi**
(kullanıcı isteği) — burada yalnızca yapılmamış işler var. Biten bir madde bu dosyadan
çıkarılır; nasıl yapıldığı `Notes/` altındaki belgelerde anlatılır.

Tamamlananların özeti: altyapı, yerleşim, 3D sahne, Energy Core, elektrik arkları,
yörünge düğümleri, düğüm bağlantıları (neural network), AI durum animasyonları, fare
etkileşimi, açılış animasyonu, masaüstü paketleme (WebView2), sesli asistan entegrasyonu,
ayarlar paneli, performans optimizasyonu, uyku modu (çekirdeğe tıklama), tepsi kontrolü,
odaklı düğüme kamera yaklaşması, **Vision paneli**, **alt Timeline**, **Hafıza ve
Otomasyon panelleri**, **ses dalga formu**, **düşünme sesi** ve **telemetri kartı**.

---

## 1. Vision paneli — kalanlar

Panel yapıldı (2026-07-30): canlı kamera görüntüsü, yerel YOLO-World taraması, tespit
çerçeveleri ve etiketleri. OCR 2026-07-31'de eklendi (yerel EasyOCR, Türkçe+İngilizce,
`read_text` aracıyla sesli de kullanılabiliyor). Kamera aç/kapat, "Nesneler" ve
"Yazıyı oku" arayüzden çalışıyor (`backend/api/vision.py`).

- [ ] Yüz tanıma

## 2. Sol panel modülleri — kalanlar

Hafıza ve Otomasyon 2026-07-30'da gerçek veriye bağlandı. Kalan ikisinin arkasında
gösterilecek bir veri **yok**, o yüzden dürüst boş durum gösteriyorlar:

- [ ] Ajanlar — çoklu ajan sistemi henüz planlama aşamasında (bağlanacak bir şey yok)
- [ ] Tarayıcı — oturum durumu tutulmuyor; sayfa içi etkileşim eklenince anlamlı olacak

## 3. Küçük artıklar

- [ ] Telemetri kartında GPU ve sıcaklık yok — Windows'ta `psutil` ikisini de güvenilir
      vermiyor (`sensors_temperatures` çoğu masaüstünde boş döner, GPU için ayrı bir
      satıcı kütüphanesi gerekir). Uydurmak yerine hiç gösterilmiyor.
      (İnternet ve saat 2026-07-31'de eklendi — `Notes/Arayuz.md` § Telemetri şeridi.)
- [ ] Cam düğme stili altı bileşende kopyalanmış — `AssistantDock`,
      `SettingsPanelContent`, `VoicePanelContent`, `VisionPanel`, `Sidebar`,
      `NodeFocusCard` aynı iskeleti (`rounded-full border bg-white/[0.04]
      border-border-subtle ... transition-all duration-200`) elle tekrar yazıyor
      ve değerler kayıyor (`0.04` ↔ `0.045`, `hover:text-foreground` ↔
      `hover:text-primary`). Ortak bir `GlassButton` vardı ama hiçbir yerden
      çağrılmıyordu; 2026-08-06'da kasadaki temizlik kuralı gereği silindi.
      Doğrusu boyut/ton varyantı olan tek bir kontrol — AMA bu görsel bir
      değişiklik: `Notes/Bilinen-Tuzaklar.md` § Bakarak doğrula gereği her
      düğmenin ekran görüntüsüyle karşılaştırılması şart.
- [ ] Duraklat düğmesi yok — zincirin tamamı hazır, yalnızca kullanıcının
      basacağı şey eksik (`Notes/Arayuz.md` § Küçük parçalar).

---

## Bilinçli olarak yapılmayacaklar

- **Mobil optimizasyon** — Chiron artık bir masaüstü uygulaması (WebView2 penceresi).
  Tarayıcıda geliştirme modu hâlâ çalışıyor ama mobil bir hedef değil.
