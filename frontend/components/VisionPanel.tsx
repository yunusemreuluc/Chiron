'use client';

import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { LuCamera, LuCameraOff, LuCopy, LuScanEye, LuScanLine, LuTextSelect } from 'react-icons/lu';
import { useNodeFocusStore } from '@/stores/nodeFocusStore';
import {
  useVisionStore,
  type Detection,
  type TextLine,
  type VisionMode,
} from '@/stores/visionStore';
import {
  fetchVisionAvailable,
  requestDetection,
  requestOcr,
  setWebcamEnabled,
} from '@/services/visionApi';
import { playSfx } from '@/services/sfxPlayer';
import { GlassPanel } from './GlassPanel';

// CHIRON Vision paneli — Notes/Tasarim-Kurallari.md § Panel yerleşimi (Vision / Camera / Object
// Detection). Kullanıcı isteğiyle (2026-07-30) sıfırdan yazıldı.
//
// Backend zaten kameranın karelerini `webcam_frame` olayıyla yayınlıyordu ama
// arayüzde tüketen yoktu; YOLO-World de çalışıyordu ama sonuçları hiçbir yere
// akmıyordu. Bu panel o iki akışı görünür kılıyor.
//
// TASARIM KARARI — çerçeveler kareyle AYNI kutunun içinde, yüzde cinsinden
// konumlanıyor. Tespit koordinatları normalize geldiği için (bkz.
// actions/object_recognition.py) kart genişliği değişse de kutular kaymıyor;
// canvas'a çizmek yerine DOM kullanmak burada hem daha az kod hem de etiketleri
// bedavaya getiriyor.

// Tespitlerin "taze" sayıldığı süre.
//
// Buradaki gerçek gerilim şu: tarama TEK bir kare üzerinde yapılıyor, ama
// görüntü akmaya devam ediyor. Yani çerçeveler çizildiği andan itibaren
// gerçeklikten uzaklaşmaya başlıyor. Kareyi dondurmak kamerayı bozuk gösterirdi;
// çözüm çerçevelerin ömrünü kısa tutmak — 6 saniye sonra soluyorlar, yani panel
// "şu an böyle" demeyi bırakıp "az önce böyleydi" demeye geçiyor.
const DETECTION_TTL_MS = 6_000;
// Kaç tespit gösterilecek. YOLO-World geniş bir dağarcıkla çalışıyor ve düşük
// güvenli çok sayıda etiket dönebiliyor; panel bir liste değil, bir HUD.
const MAX_VISIBLE = 6;

// Panelin bağlı olduğu yörünge düğümü (bkz. three/nodeData.ts). Kullanıcı
// isteğiyle (2026-07-31): panel artık HER ZAMAN durmuyor — kamera açıkken ya da
// sahnedeki "Görme" düğümüne tıklanınca geliyor. Kapalı kamerayla sürekli duran
// siyah bir 16:9 kutu, sağ kolonun yarısını hiçbir şey söylemeden yiyordu.
const VISION_NODE_ID = 'vision';

// Ses döngüsü arayüzden SONRA ayağa kalkabiliyor (desktop.py onu ayrı bir
// thread'de başlatıyor). Tek seferlik sorup "yok" demek, panelin o oturum
// boyunca devre dışı kalmasına yol açıyordu — olumlu cevap gelene kadar
// tekrar soruluyor.
const AVAILABILITY_RETRY_MS = 4000;

// Tarama isteği gitti ama sonuç hiç gelmezse (ör. ses döngüsü öldü) düğme
// sonsuza kadar kilitli kalmasın.
const SCAN_TIMEOUT_MS = 25_000;

/**
 * `stamp` damgalı verinin `ttlMs` sonra eskimiş sayılıp sayılmadığı.
 *
 * Neden bu şekilde: effect gövdesinde senkron `setState` yasak
 * (react-hooks/set-state-in-effect) — "önce tazeye çek, sonra zamanlayıcı kur"
 * yaklaşımı bu yüzden çalışmıyor. Burada state HANGİ damganın eskidiğini
 * tutuyor; yeni bir tarama geldiğinde damga değiştiği için karşılaştırma
 * kendiliğinden "taze"ye dönüyor ve setState yalnızca zamanlayıcının
 * geri çağırmasında oluyor.
 */
function useIsStale(stamp: number | null, ttlMs: number): boolean {
  const [staleStamp, setStaleStamp] = useState<number | null>(null);

  useEffect(() => {
    if (stamp === null) return;
    const timer = window.setTimeout(() => setStaleStamp(stamp), ttlMs);
    return () => window.clearTimeout(timer);
  }, [stamp, ttlMs]);

  return stamp !== null && staleStamp === stamp;
}

export function VisionPanel() {
  const webcamActive = useVisionStore((state) => state.webcamActive);
  const frame = useVisionStore((state) => state.frame);
  const detections = useVisionStore((state) => state.detections);
  const textLines = useVisionStore((state) => state.textLines);
  const mode = useVisionStore((state) => state.mode);
  const detectionSource = useVisionStore((state) => state.detectionSource);
  const detectedAt = useVisionStore((state) => state.detectedAt);
  const hasScanned = useVisionStore((state) => state.hasScanned);
  const isScanning = useVisionStore((state) => state.isScanning);
  const setScanning = useVisionStore((state) => state.setScanning);

  const focusedNodeId = useNodeFocusStore((state) => state.focusedNodeId);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [notice, setNotice] = useState('');
  const detectionsFresh = !useIsStale(detectedAt, DETECTION_TTL_MS);

  // Görü bu pencerede var mı? (Arayüz tek başına da açılabiliyor —
  // desktop.py --sadece-arayuz. O durumda kamera diye bir şey yok.)
  // Olumlu cevap gelene kadar yeniden soruluyor; bkz. AVAILABILITY_RETRY_MS.
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const probe = () => {
      void fetchVisionAvailable().then((value) => {
        if (cancelled) return;
        setAvailable(value);
        if (!value) timer = window.setTimeout(probe, AVAILABILITY_RETRY_MS);
      });
    };
    probe();

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, []);

  // Takılı kalmış "taranıyor" durumunu çöz. setState yalnızca zamanlayıcının
  // geri çağırmasında — effect gövdesinde değil (react-hooks/set-state-in-effect).
  useEffect(() => {
    if (!isScanning) return;
    const timer = window.setTimeout(() => setScanning(false), SCAN_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [isScanning, setScanning]);

  const toggleCamera = async () => {
    const next = !webcamActive;
    const result = await setWebcamEnabled(next);
    if (result.success) {
      playSfx('hud');
      setNotice('');
    } else {
      playSfx('error');
      setNotice(result.message);
    }
  };

  // İki iş de aynı yolu izliyor: istek gönder, sonuç WebSocket'ten gelsin.
  const run = async (request: () => Promise<{ success: boolean; message: string }>) => {
    setScanning(true);
    const result = await request();
    if (!result.success) {
      setScanning(false);
      playSfx('error');
      setNotice(result.message);
    }
  };

  const visible = detections.slice(0, MAX_VISIBLE);
  const isOpen = webcamActive || focusedNodeId === VISION_NODE_ID;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0, x: 20, filter: 'blur(6px)' }}
          animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, x: 20, filter: 'blur(6px)' }}
          transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
          className="w-full"
        >
          <VisionCard
            webcamActive={webcamActive}
            frame={frame}
            visible={visible}
            textLines={textLines}
            mode={mode}
            detectionSource={detectionSource}
            hasScanned={hasScanned}
            isScanning={isScanning}
            detectionsFresh={detectionsFresh}
            available={available}
            notice={notice}
            onToggleCamera={() => void toggleCamera()}
            onScan={() => void run(requestDetection)}
            onReadText={() => void run(requestOcr)}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

interface VisionCardProps {
  webcamActive: boolean;
  frame: string | null;
  visible: Detection[];
  textLines: TextLine[];
  mode: VisionMode | null;
  detectionSource: string | null;
  hasScanned: boolean;
  isScanning: boolean;
  detectionsFresh: boolean;
  /** Sesli asistan bağlı mı — yalnızca boş kare mesajında kullanılıyor.
   *  Düğmeleri KİLİTLEMİYOR (bkz. aşağıdaki eylem düğmeleri notu). */
  available: boolean | null;
  notice: string;
  onToggleCamera: () => void;
  onScan: () => void;
  onReadText: () => void;
}

function VisionCard({
  webcamActive,
  frame,
  visible,
  textLines,
  mode,
  detectionSource,
  hasScanned,
  isScanning,
  detectionsFresh,
  available,
  notice,
  onToggleCamera,
  onScan,
  onReadText,
}: VisionCardProps) {
  return (
    <GlassPanel variant="card" className="flex w-full flex-col p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="border-border-subtle flex h-7 w-7 items-center justify-center rounded-[9px] border bg-white/[0.04]">
            <LuScanEye size={13} strokeWidth={1.7} className="text-primary" />
          </span>
          <span className="flex flex-col gap-1">
            <span className="label-micro">Görü</span>
            <span className="text-foreground text-[13px] leading-none font-medium">Kamera</span>
          </span>
        </div>

        <IconToggle
          label={webcamActive ? 'Kamerayı kapat' : 'Kamerayı aç'}
          icon={webcamActive ? LuCamera : LuCameraOff}
          active={webcamActive}
          onClick={onToggleCamera}
        />
      </div>

      {/* ── Görüntü alanı ── 16:9 sabit: kare gelip gittikçe kartın yüksekliği
          zıplamasın. */}
      <div className="border-border-subtle relative mt-3.5 aspect-video w-full overflow-hidden rounded-[12px] border bg-black/45">
        {frame ? (
          // eslint-disable-next-line @next/next/no-img-element -- canlı base64 kare akışı; next/image burada anlamsız
          <img src={frame} alt="Kamera görüntüsü" className="h-full w-full object-cover" />
        ) : (
          <EmptyFrame active={webcamActive} available={available} />
        )}

        {/* Çerçeveler — kare varken ve sonuç tazeyken. Nesne mi metin mi
            çizileceğini `mode` belirliyor: ikisi üst üste çizilirse kare
            okunmaz hâle geliyordu. */}
        {frame && detectionsFresh && (
          <div className="pointer-events-none absolute inset-0">
            {mode === 'objects' &&
              visible.map(
                (detection) =>
                  detection.box && (
                    <BoxOverlay
                      key={detection.label}
                      box={detection.box}
                      label={detection.displayName}
                    />
                  ),
              )}
            {mode === 'text' &&
              textLines.map(
                (line, index) =>
                  line.box && <BoxOverlay key={`${index}-${line.text}`} box={line.box} />,
              )}
          </div>
        )}

        {/* Tarama sırasında geçen bir tarama hattı — beklemenin görünür karşılığı. */}
        <AnimatePresence>
          {isScanning && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="pointer-events-none absolute inset-0"
            >
              <motion.span
                className="absolute inset-x-0 h-[2px]"
                style={{
                  background:
                    'linear-gradient(90deg, transparent, var(--color-primary), transparent)',
                  boxShadow: '0 0 12px var(--color-primary)',
                }}
                animate={{ top: ['4%', '96%', '4%'] }}
                transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Tara ──
          Kullanıcı isteğiyle (2026-07-31) YALNIZCA tarama sürerken kilitli.
          Önceden `available === false` ile de kilitleniyordu; ses döngüsü
          arayüzden sonra ayağa kalktığında bu bayrak "false"ta takılı kalıyor ve
          düğme hiç açılmıyordu. Artık her zaman basılabiliyor: kamera kapalıysa
          backend onu kendisi açıp tarıyor (bkz. ChironLive._on_vision_detect_ui),
          gerçekten bir sorun varsa da aşağıdaki mesaj söylüyor. */}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <ActionButton
          icon={LuScanLine}
          label={isScanning ? '...' : 'Nesneler'}
          disabled={isScanning}
          onClick={onScan}
        />
        <ActionButton
          icon={LuTextSelect}
          label={isScanning ? '...' : 'Yazıyı oku'}
          disabled={isScanning}
          onClick={onReadText}
        />
      </div>

      {/* ── Sonuçlar ── Panel her zaman EN SON çalışan işin sonucunu gösteriyor. */}
      {hasScanned && (
        <div className="mt-3.5 flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-2">
            <span className="label-micro">{mode === 'text' ? 'Okunan' : 'Tespit'}</span>
            {detectionSource === 'assistant' && (
              <span className="label-micro text-primary/70">Chiron baktı</span>
            )}
          </div>

          <div
            className={`transition-opacity duration-700 ${
              detectionsFresh ? 'opacity-100' : 'opacity-45'
            }`}
          >
            {mode === 'text' ? (
              <TextResult lines={textLines} />
            ) : visible.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {visible.map((detection) => (
                  <span
                    key={detection.label}
                    className="border-border-subtle text-foreground-secondary flex items-center gap-1.5 rounded-full border bg-white/[0.04] px-2.5 py-1 text-[11px]"
                  >
                    {detection.displayName}
                    <span className="numeric text-foreground-disabled text-[10px]">
                      {Math.round(detection.confidence * 100)}%
                    </span>
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-foreground-disabled text-[11px]">
                Tanıdığım bir nesne bulunamadı.
              </p>
            )}
          </div>
        </div>
      )}

      {notice && <p className="mt-3 text-[11px] text-[#ff8f8f]">{notice}</p>}

      {/* OCR ve yüz tanıma henüz yok — panelin bunları varmış gibi göstermemesi
          için hiçbir yerde yer almıyorlar (bkz. Docs/CHIRON_UI_ROADMAP.md). */}
    </GlassPanel>
  );
}

function EmptyFrame({ active, available }: { active: boolean; available: boolean | null }) {
  const message =
    available === false
      ? 'Sesli asistan bu pencerede çalışmıyor'
      : active
        ? 'Görüntü bekleniyor...'
        : 'Kamera kapalı';

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2">
      {/* Kamera açıkken nefes alan bir işaret: "bekliyor" ile "ölü" farkı. */}
      <motion.span
        animate={active ? { opacity: [0.35, 0.75, 0.35] } : { opacity: 0.3 }}
        transition={active ? { duration: 2.2, repeat: Infinity, ease: 'easeInOut' } : undefined}
      >
        <LuCameraOff size={18} strokeWidth={1.5} className="text-foreground-disabled" />
      </motion.span>
      <span className="label-micro">{message}</span>
    </div>
  );
}

/** Kare üzerindeki çerçeve. Nesne tespiti ve OCR aynı kutu sözleşmesini
 *  paylaştığı için tek bileşen ikisine de hizmet ediyor; fark yalnızca
 *  etiketin olup olmaması (OCR'da metnin kendisi zaten aşağıda okunuyor,
 *  kutunun üstünde tekrar etmek kareyi doldururdu). */
function BoxOverlay({ box, label }: { box: [number, number, number, number]; label?: string }) {
  const [x1, y1, x2, y2] = box;
  const left = Math.min(x1, x2) * 100;
  const top = Math.min(y1, y2) * 100;
  const width = Math.abs(x2 - x1) * 100;
  const height = Math.abs(y2 - y1) * 100;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className="absolute"
      style={{
        left: `${left}%`,
        top: `${top}%`,
        width: `${width}%`,
        height: `${height}%`,
        border: '1px solid rgba(127, 178, 255, 0.75)',
        borderRadius: 4,
        boxShadow: '0 0 10px rgba(127, 178, 255, 0.28), inset 0 0 10px rgba(127, 178, 255, 0.12)',
      }}
    >
      {/* Etiket kutunun ÜSTÜNDE duruyor; kutu karenin üst kenarına yakınsa
          altına geçiyor (yukarıda yer yok, kırpılırdı).
          Yatayda: kutu karenin sağ yarısındaysa etiket kutunun SAĞ kenarına
          yapışıp sola doğru büyüyor — sola yapışsaydı uzun etiketler (ör.
          "dizüstü bilgisayar") karenin dışına taşıp kırpılıyordu. */}
      {label && (
        <span
          className="text-foreground absolute max-w-[130px] truncate rounded-[4px] px-1.5 py-0.5 text-[9px] font-medium"
          style={{
            bottom: top < 14 ? 'auto' : '100%',
            top: top < 14 ? '100%' : 'auto',
            marginBottom: top < 14 ? 0 : 3,
            marginTop: top < 14 ? 3 : 0,
            left: left > 50 ? 'auto' : 0,
            right: left > 50 ? 0 : 'auto',
            background: 'rgba(9, 12, 19, 0.86)',
            border: '1px solid rgba(127, 178, 255, 0.3)',
          }}
        >
          {label}
        </span>
      )}
    </motion.div>
  );
}

/** Okunan metin — satırlar birleşik gösteriliyor ve kopyalanabiliyor.
 *  Kopyalama bilinçli: bir yazıyı okutmanın en yaygın sebebi onu kullanmak. */
function TextResult({ lines }: { lines: TextLine[] }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1800);
    return () => window.clearTimeout(timer);
  }, [copied]);

  if (lines.length === 0) {
    return <p className="text-foreground-disabled text-[11px]">Okuyabildiğim bir yazı yok.</p>;
  }

  const text = lines.map((line) => line.text).join(' ');

  return (
    <div className="flex flex-col gap-2">
      <p className="text-foreground max-h-24 overflow-y-auto text-[11px] leading-relaxed break-words">
        {text}
      </p>
      <div className="flex items-center justify-between gap-2">
        <span className="numeric text-foreground-disabled text-[10px]">{lines.length} satır</span>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard.writeText(text).then(() => setCopied(true));
          }}
          className="border-border-subtle text-foreground-secondary hover:text-primary hover:border-primary/40 flex items-center gap-1.5 rounded-full border bg-white/[0.04] px-2.5 py-1 text-[10px] transition-all duration-200"
        >
          <LuCopy size={10} strokeWidth={1.8} />
          {copied ? 'Kopyalandı' : 'Kopyala'}
        </button>
      </div>
    </div>
  );
}

function ActionButton({
  icon: Icon,
  label,
  disabled,
  onClick,
}: {
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="border-border-subtle text-foreground-secondary hover:text-primary hover:border-primary/40 flex items-center justify-center gap-1.5 rounded-full border bg-white/[0.04] px-2 py-2 text-[11px] font-medium transition-all duration-200 disabled:opacity-40 disabled:hover:border-[var(--border-subtle)] disabled:hover:text-[var(--foreground-secondary)]"
    >
      <Icon size={12} strokeWidth={1.8} />
      {label}
    </button>
  );
}

function IconToggle({
  label,
  icon: Icon,
  active,
  onClick,
}: {
  label: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] border transition-all duration-200 ${
        active
          ? 'border-primary/40 text-primary bg-primary/10'
          : 'border-border-subtle text-foreground-secondary hover:text-foreground bg-white/[0.04]'
      }`}
      style={active ? { boxShadow: 'var(--glow-primary-sm)' } : undefined}
    >
      <Icon size={13} strokeWidth={1.7} />
    </button>
  );
}
