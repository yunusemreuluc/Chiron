---
tags: [chiron, arac]
---

# Nesne Tanıma — actions/object_recognition.py

Bağlı: [[Home]] · [[Arac-Tanimlari]] · [[Webcam]] · [[OCR]] · [[Arayuz]] · [[Bellek-ve-Config]]

Kamera görüntüsündeki nesneleri **yerel** olarak tanır. Gemini'ye gitmez, yani
günlük kotayı hiç harcamaz — vision-ağır özellikleri art arda denerken 429'a
takılmamanın sebebi bu.

## Model: YOLO-World

`yolov8s-worldv2.pt` — "açık kelime dağarcıklı" (open-vocabulary) bir model:
yeniden eğitilmeden, çalışma anında **metinle** yeni sınıflar öğretilebiliyor.
`DEFAULT_VOCABULARY` ev/ofis eşyalarından oluşan ~55 İngilizce kavram tutuyor;
görüntülenirken `_DISPLAY_NAMES` ile Türkçeye çevriliyor (İngilizce kavramlarla
CLIP tabanlı sınıflandırıcı daha güvenilir çalışıyor).

**Ağır zincir bilerek tembel yükleniyor.** `ultralytics` modül seviyesinde import
EDİLMİYOR — torch + ultralytics + matplotlib zinciri açılışta **273 MB** tutuyordu
ve `main.py` bu modülü araç kaydı için her açılışta import ettiğinden, kullanıcı
nesne tanımayı hiç çalıştırmasa bile bu bedel ödeniyordu. Paketin kurulu olup
olmadığı `importlib.util.find_spec` ile bakılıyor (dosya sisteminde arar, modülü
çalıştırmaz); gerçek import ilk tespitte `_get_model` içinde.

## Öğrenme

`learn_object(name, description)` → Gemini vision'dan nesnenin zengin bir
betimlemesi alınıp `memory.json`'daki `known_objects` altına yazılıyor
([[Bellek-ve-Config]]). Sonraki `recognize_objects` çağrılarında bu isimler
YOLO-World'ün arama dağarcığına ekleniyor. Yani "öğrenme" model eğitimi değil,
hafıza + dağarcık genişletmesi.

## Çıktı sözleşmesi

`detect_objects_in_jpeg()` → `[{label, display_name, confidence, box}]`.
`box` **normalize** `[x1, y1, x2, y2]` (0..1) — 2026-07-30'da eklendi, o güne
kadar yalnızca etiket dönüyordu ve arayüzde çerçeve çizmek mümkün değildi.
Normalize olması bilinçli: arayüz kareyi kendi kart genişliğinde ölçekliyor,
piksel koordinatı orada işe yaramazdı. [[OCR]] aynı sözleşmeyi paylaşıyor, bu
sayede Vision paneli ikisini de tek çizim koduyla gösteriyor.

Aynı etiketten yalnızca en yüksek güvenli olan tutuluyor. Fonksiyon **asla
exception fırlatmaz** — ultralytics/PIL yoksa ya da hata olursa boş liste döner.

## Arayüz bağlantısı

Sonuçlar `vision_detections` WebSocket olayıyla Vision paneline akıyor
([[Arayuz]]). İki kaynak var: kullanıcı panelden "Nesneler" düğmesine bastığında
(`source: "panel"`) ve Chiron kendi aracını çağırdığında (`source: "assistant"`) —
Chiron bir şey gördüğünde kullanıcı da görsün diye.

Tool: `recognize_objects`, `learn_object` ([[Arac-Tanimlari]]).
