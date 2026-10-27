# CHIRON — Özellik Takibi

Tamamlanan özellikler 2026-07-29'da bu listeden **silindi** (kullanıcı isteği).
Burada yalnızca yapılmamış ya da yarım kalanlar var.

Biten bir özellik listeden çıkarılır. Çalışan özelliklerin ne olduğu ve nasıl
çalıştığı `Notes/` altındaki belgelerde.

**Durumlar:** 🟡 yarım · 🔵 planlandı · 💡 fikir

---

## Çekirdek AI

| Özellik | Durum | Öncelik | Not |
|---|---|---|---|
| Konuşma geçmişi | 🟡 | Orta | Oturum içinde var (son 200 satır), kalıcı değil |
| Çoklu ajan | 🔵 | Yüksek | Planlama aşamasında |

## Görü (Vision)

| Özellik | Durum | Öncelik | Not |
|---|---|---|---|
| Yüz tanıma | 🔵 | Orta | — |
| El hareketi tanıma | 🔵 | Yüksek | Bkz. YAPILACAKLAR.md #3 (ertelendi) |
| Sahne anlama | 🔵 | Yüksek | `analyze_screen` var; sürekli/proaktif değil |

## Otomasyon

| Özellik | Durum | Öncelik | Not |
|---|---|---|---|
| Program kapatma | 🔵 | Orta | Açma çalışıyor |
| Tarayıcı otomasyonu | 🟡 | Yüksek | URL açma/arama var; sayfa içi etkileşim yok |
| Dosya yönetimi | 🟡 | Yüksek | Arama + özetleme var; taşıma/silme yok |

## Arayüz

| Özellik | Durum | Öncelik | Not |
|---|---|---|---|
| Telemetride GPU/sıcaklık | 🔵 | Düşük | psutil Windows'ta ikisini de güvenilir vermiyor |

## AI Durumları

Idle / Listening / Thinking / Speaking / Vision hepsi **çalışıyor** (3D çekirdek,
düğümler, arklar ve bağlantılar bu duruma tepki veriyor; konuşurken çekirdek
turkuaz-yeşile dönüyor).

| Durum | Durum | Not |
|---|---|---|
| Otomasyon çalışıyor | 🔵 | Ayrı bir sahne durumu yok — şu an "thinking"e düşüyor (Timeline'da görünüyor) |
| Hata | 🟡 | Sohbette + Timeline'da görünüyor, hata sesi çalıyor; 3D sahnede ayrı durum yok |

## İleride (fikir)

Eklenti sistemi · Akıllı ev · Mobil uygulama · VR/AR · Bulut senkronizasyon ·
AI avatar · Çoklu PC kontrolü · API pazaryeri
