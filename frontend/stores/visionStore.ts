import { create } from 'zustand';

// CHIRON — görü (vision) durumu.
//
// Kullanıcı isteğiyle (2026-07-30) Vision paneli yapıldı. Backend zaten
// kameranın karelerini yayınlıyordu (`webcam_frame`, ~8 FPS, bkz. core/web_ui.py)
// ama arayüzde bunu tüketen hiçbir şey yoktu — kamera görünmüyordu.
//
// Kareler burada TUTULUYOR ama geçmişi tutulmuyor: yalnızca son kare. Video
// akışında eski kareler işe yaramaz ve saniyede 8 base64 JPEG biriktirmek
// belleği hızla şişirirdi.

export interface Detection {
  label: string;
  displayName: string;
  confidence: number;
  /** Normalize [x1, y1, x2, y2] (0..1) — kart genişliğinden bağımsız. */
  box: [number, number, number, number] | null;
}

/** Okunan bir metin satırı (yerel EasyOCR, bkz. actions/ocr.py). */
export interface TextLine {
  text: string;
  confidence: number;
  /** Nesne tespitiyle AYNI sözleşme: normalize [x1, y1, x2, y2]. */
  box: [number, number, number, number] | null;
}

/** Sonucun kaynağı: kullanıcı düğmeye bastı mı, Chiron kendi mi baktı. */
export type DetectionSource = 'panel' | 'assistant';

/**
 * Panelde en son ÇALIŞAN iş. Nesne tespiti ve metin okuma ayrı eylemler ve
 * ikisinin sonucunu (hem çipler hem metin, hem iki tür kutu) aynı anda
 * göstermek küçük bir kartı okunmaz hâle getiriyordu — panel her zaman en son
 * yapılan işi gösteriyor.
 */
export type VisionMode = 'objects' | 'text';

interface VisionStore {
  /** Kamera cihazı açık mı (backend'in bildirdiği gerçek durum). */
  webcamActive: boolean;
  /** Son kare, hazır `data:` URL olarak. Kare yoksa null. */
  frame: string | null;
  detections: Detection[];
  textLines: TextLine[];
  /** En son hangi iş çalıştı — panel onun sonucunu gösteriyor. */
  mode: VisionMode | null;
  detectionSource: DetectionSource | null;
  /**
   * Son taramanın zamanı (ms). Tespitlerin "tazeliği" bundan TÜRETİLİYOR, ayrı
   * bir bayrak tutulmuyor — her yeni tarama yeni bir damga demek, panel de
   * karşılaştırarak eskimişi anlıyor (bkz. VisionPanel useIsStale).
   */
  detectedAt: number | null;
  /** Hiç tarama yapıldı mı — "sonuç yok" ile "henüz taranmadı"yı ayırmak için. */
  hasScanned: boolean;
  /** Tarama isteği gönderildi, sonuç bekleniyor. */
  isScanning: boolean;

  setWebcamActive: (active: boolean) => void;
  setFrame: (jpegBase64: string) => void;
  setDetections: (detections: Detection[], source: DetectionSource) => void;
  setTextLines: (lines: TextLine[], source: DetectionSource) => void;
  setScanning: (scanning: boolean) => void;
}

export const useVisionStore = create<VisionStore>((set) => ({
  webcamActive: false,
  frame: null,
  detections: [],
  textLines: [],
  mode: null,
  detectionSource: null,
  detectedAt: null,
  hasScanned: false,
  isScanning: false,

  setWebcamActive: (webcamActive) =>
    set((state) => ({
      webcamActive,
      // Kamera kapanınca son kare de gitmeli: donmuş bir görüntünün altında
      // "kamera kapalı" yazması, kullanıcıya kameranın hâlâ açık olduğunu
      // düşündürür.
      frame: webcamActive ? state.frame : null,
    })),

  setFrame: (jpegBase64) => set({ frame: `data:image/jpeg;base64,${jpegBase64}` }),

  setDetections: (detections, detectionSource) =>
    set({
      detections,
      mode: 'objects',
      detectionSource,
      // Damga backend'in `at` alanından DEĞİL, yerel saatten: tazelik hesabı
      // yerel saatle yapılıyor ve iki saat arasındaki fark (aynı makinede küçük
      // olsa bile) kıyaslamayı bozardı.
      detectedAt: Date.now(),
      hasScanned: true,
      isScanning: false,
    }),

  setTextLines: (textLines, detectionSource) =>
    set({
      textLines,
      mode: 'text',
      detectionSource,
      detectedAt: Date.now(),
      hasScanned: true,
      isScanning: false,
    }),

  setScanning: (isScanning) => set({ isScanning }),
}));
