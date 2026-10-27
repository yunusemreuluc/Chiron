---
tags: [chiron, tasarim]
---

# Tasarım Kuralları

Bağlı: [[Home]] · [[Arayuz]] · [[Bilinen-Tuzaklar]]

Bu kurallar 2026-07-31'e kadar `CLAUDE.md` içindeydi. O dosya yalın bir karar
kitabına indirilince buraya taşındılar — silinmediler, yer değiştirdiler.
`CLAUDE.md`'nin ilk kuralı zaten "önce kasayı oku", dolayısıyla hâlâ okunuyorlar.

Kod yorumlarındaki `CLAUDE.md § ...` atıfları bu nota bakar.

## Arayüz stili

**Gerekli:** glassmorphism, saydam paneller, yuvarlatılmış köşeler, yüzen
bileşenler, premium boşluk, yumuşak gölgeler, derinlik, hareket, yumuşak
geçişler, hacimsel ışık.

**Kaçınılacak:** Bootstrap, Material UI görünümü, düz (flat) tasarım, kutu kutu
yerleşim, keskin köşeler, Windows tarzı, jenerik gösterge paneli.

## Animasyon

Her şey hareket eder, hiçbir şey durağan hissettirmez: süzülme, nabız, ışıma,
solma, dönme, parçacıklar, parallax, hover animasyonları.

**Asla lineer hareket yok — her zaman easing.** Geçiş eğrileri
`app/globals.css` içinde tek yerde (`--ease-out-quint`, `--ease-standard`).

## Hareket (fare)

Fare hareketi derinlik, perspektif ve parallax yaratır. Paneller *hafifçe* tepki
verir — abartı yok. Kamera takibi `three/CameraRig.tsx`'te, panellerinki
`hooks/useMouseParallax.ts`'te (React state değil, doğrudan DOM transform —
mousemove başına render olmasın diye).

## Enerji çekirdeği

CHIRON'un merkezi canlıdır. Sürekli nefes alır, yavaşça döner, parçacık yayar,
ışımasını değiştirir, kullanıcı etkinliğine tepki verir. **Asla durağan olmaz.**

Tepki vermesi gereken beş şey: Ses, Düşünme, Görü, **Otomasyon**, **Hafıza**.
Beşi de çalışıyor (2026-07-31) — hangi rengin/hareketin neyi anlattığı ve
hangi aracın hangi durumu tetiklediği [[Arayuz]] § Durum renkleri içinde.

Çekirdeğin **formu** 2026-08-06'da dolu plazma küreden **tel kafes hologramına**
geçti; yukarıdaki kural değişmedi, yalnızca neyin nefes aldığı değişti. Katmanlar
ve gerekçeleri [[Arayuz]] § Tel kafes çekirdek.

## Renk

Doğruluk kaynağı **`frontend/app/globals.css`**. Buraya kopyalanmıyor: bir
zamanlar `CLAUDE.md` içinde bir kopyası vardı ve sessizce bayatladı (dosya
"asla rastgele renk kullanma" derken kimsenin kullanmadığı üç rengi
listeliyordu). Tek kaynak kuralı bu yüzden var.

Paletin *neden* öyle olduğu ve konuşma durumundaki yeşil için [[Arayuz]].

## Panel yerleşimi

Hangi panelin nerede olduğu ve **neden orada olduğu** [[Arayuz]] içinde — üst
çubuğun neden kaldırıldığı, Vision panelinin neden koşullu olduğu, Ses'in neden
sol raydan dock'a taşındığı hep orada.

Özet kurallar:

- **Sol ray:** sadece ikonlar, minimal, saydam, hover'da hafifçe büyür
  (1.08 — bkz. [[Arayuz]] § Sol ray), hover olmadıkça etiket yok
- **Sol panel:** gereksiz düğme yok
- **Sağ panel:** her zaman cam
- **Alt panel:** asla kalabalık yapma

## Durum yönetimi

Zustand. Prop drilling yok. **Ayrı store'lar** — tek bir dev store'da
toplanmıyor: `aiStateStore`, `nodeFocusStore`, `navigationStore`,
`conversationStore`, `visionStore`, `timelineStore`, `micStore`, `powerStore`.

Kare başına değişen veri (düğüm konumları, mikrofon seviyesi) store'a
YAZILMAZ — her karede bir React güncellemesi demek olurdu. Bkz.
`three/nodeData.ts` içindeki konum yayını.

## Bileşen adları

Kod tabanındaki gerçek adlar — paralel isim uydurma:

`EnergyCore.tsx` · `Sidebar.tsx` · `VisionPanel.tsx` · `OrbitNodes.tsx` (çoğul,
tek bileşen hepsini render eder) · `Timeline.tsx` · `GlassPanel.tsx` (iki
varyant: `panel` ve `card`) · `EnergyTendrils.tsx` / `DustField.tsx` (parçacık
sistemleri) · `TelemetryCard.tsx` · `SleepVeil.tsx` · `TrayControl.tsx`

Her bileşenin tek sorumluluğu vardır. Devasa dosya yok.

## Kod stili

Sadece TypeScript. Fonksiyonel bileşenler. Kod tekrarı yok. Karmaşık mantığı
belgele.

## Duyarlılık

Önce masaüstü: 1920 / 1600 / 1440 / 1366. Dördü de ölçüldü, sıfır taşma —
ölçüm tablosu [[Arayuz]] içinde.
