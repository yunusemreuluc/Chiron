'use client';

import { useEffect, useState } from 'react';
import { AnimatePresence, motion, type Variants } from 'framer-motion';
import { useConversationStore } from '@/stores/conversationStore';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';

// CHIRON açılışı — "Ateşleme".
//
// Kullanıcı isteğiyle (2026-07-31) yeniden tasarlandı. Önceki sürüm siyah bir
// ekranda CHIRON yazısı ve dolan bir ilerleme çubuğuydu: bu bir YÜKLEME EKRANI
// dili ve CHIRON'un dünyasına ait değil (CLAUDE.md § PROJECT — "bir gösterge
// paneli DEĞİLDİR"). Sonrasındaki 3D kuruluş zaten iyiydi; sorun ondan
// öncesiydi.
//
// Yeni akış tek bir fikir üzerine kurulu: **enerji çekirdeği ateşleniyor.**
//
//   nokta → yanlara açılan enerji hattı → isim ışıktan çözülüyor → karanlık
//   MERKEZDEN delinip sahne doğuyor
//
// Son adım önemli: perde solup kaybolmuyor, ortasında büyüyen bir delikle
// açılıyor ve tam o noktada 3D çekirdek zaten belirmeye başlamış oluyor
// (three/EnergyCore.tsx REVEAL_DELAY = 1.5 sn). Böylece geçiş bir çapraz
// geçiş değil, nedensel bir devir teslim: çekirdek karanlığı kendisi açıyor.
//
// Zaman çizelgesinin tamamı ve diğer sahne gecikmeleri Notes/Arayuz.md'de.

const IGNITION_DELAY = 0.0; // nokta belirir
const SWEEP_DELAY = 0.28; // hat yanlara açılır
const WORD_DELAY = 0.62; // isim çözülür
const STATUS_DELAY = 1.05; // durum satırı

// Kullanıcı isteğiyle (2026-07-31, ikinci tur): isim daha uzun dursun ve
// çıkışı yavaşlasın — 1650 ms'de gidip 0.6 sn'de silinmesi "çok hızlı"
// bulundu. Artık ~1 sn daha duruyor, delinme de neredeyse iki katı sürede.
//
// Delinme sırasında çekirdeğin koronası (EnergyTendrils) belirmeye başlıyor:
// açılan delikten önce ısı yayan parçacıklar görünüyor, top (çekirdek) ondan
// SONRA geliyor. Sahnedeki gecikmeler buna göre kaydırıldı — üçü de aynı
// mount anını paylaştığı için birlikte değiştirilmeleri gerekiyor
// (bkz. Notes/Arayuz.md § Açılış sahnelemesi).
const WIPE_AT_MS = 2700; // karanlık delinmeye başlar
const WIPE_S = 1.1;

// prefers-reduced-motion: tek bir kısa sabit ekran, hareket yok.
const REDUCED_VISIBLE_MS = 400;

// Perdenin çıkışı variant olarak tanımlı: `--hole` bir CSS özel değişkeni ve
// satır içi bir nesnede hesaplanmış anahtar olarak yazılınca TypeScript
// framer-motion'ın hedef tipine oturtamıyor. Variant'lar bu anahtarları
// sorunsuz kabul ediyor.
const VEIL_VARIANTS: Variants = {
  // BAŞLANGIÇ NEGATİF, sıfır değil. Maskede deliğin kenarı 18% yumuşatılıyor;
  // `--hole: 0%` verilseydi gradyan `transparent 0% → siyah 18%` olur ve
  // merkezde kalıcı bir yumuşak delik kalırdı — sahne daha ilk kareden
  // görünüyordu. -25%'te siyah durak 0'ın gerisine düşüyor, perde tam opak.
  visible: { opacity: 1, '--hole': '-25%' },
  // Merkezde büyüyen delik — ışığın karanlığı yemesi.
  pierced: {
    '--hole': '145%',
    transition: { duration: WIPE_S, ease: [0.4, 0, 0.2, 1] },
  },
  // Hareket azaltılmışsa delik yok, düz solma.
  faded: { opacity: 0, transition: { duration: 0.15 } },
};

// İsmin KENDİ çıkışı. Delik tam merkezden açıldığı ve isim de merkezde durduğu
// için, maskeye bırakılırsa isim ~300 ms'de kesilip yok oluyordu — perde 1.1 sn
// boyunca açılsa bile izleyicinin baktığı şey aniden gidiyordu.
// Burada tersine dönüyor: geldiği gibi gidiyor (bulanıklaşarak ve harf aralığı
// açılarak), yani ışığa geri çözülüyor. AnimatePresence çıkış etiketini
// çocuklara yaydığı için `pierced` adı üstteki perdeyle eşleşiyor.
const WORD_VARIANTS: Variants = {
  hidden: { opacity: 0, filter: 'blur(14px)', letterSpacing: '0.78em' },
  visible: {
    opacity: 1,
    filter: 'blur(0px)',
    letterSpacing: '0.42em',
    transition: { duration: 0.6, delay: WORD_DELAY, ease: [0.22, 1, 0.36, 1] },
  },
  pierced: {
    opacity: 0,
    filter: 'blur(16px)',
    letterSpacing: '0.9em',
    transition: { duration: 0.8, ease: [0.4, 0, 0.2, 1] },
  },
};

// Durum satırı ve enerji hattı da kesilmeden, isimden biraz önce çekiliyor.
const SUPPORT_VARIANTS: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.4, delay: STATUS_DELAY } },
  pierced: { opacity: 0, transition: { duration: 0.45, ease: 'easeOut' } },
};

export function BootOverlay() {
  const reducedMotion = usePrefersReducedMotion();
  const [visible, setVisible] = useState(true);
  // Gerçek bağlantı durumu — uydurma bir "yükleniyor %" değil.
  const connected = useConversationStore((state) => state.connected);

  useEffect(() => {
    const duration = reducedMotion ? REDUCED_VISIBLE_MS : WIPE_AT_MS;
    const timer = setTimeout(() => setVisible(false), duration);
    return () => clearTimeout(timer);
  }, [reducedMotion]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          // İlk kareden itibaren opak: perde altındaki arayüzün bir an
          // görünmesini engellemek için var.
          variants={VEIL_VARIANTS}
          initial="visible"
          animate="visible"
          exit={reducedMotion ? 'faded' : 'pierced'}
          className="bg-background fixed inset-0 z-50 flex flex-col items-center justify-center"
          style={
            reducedMotion
              ? undefined
              : {
                  maskImage:
                    'radial-gradient(circle at 50% 50%, transparent var(--hole), #000 calc(var(--hole) + 18%))',
                  WebkitMaskImage:
                    'radial-gradient(circle at 50% 50%, transparent var(--hole), #000 calc(var(--hole) + 18%))',
                }
          }
        >
          {reducedMotion ? (
            <span className="text-foreground pl-[0.4em] text-4xl font-semibold tracking-[0.4em]">
              CHIRON
            </span>
          ) : (
            <>
              {/* ── Ateşleme + hat ──
                  Aynı eleman: önce bir nokta olarak parlıyor, sonra yanlara
                  açılıyor. İki ayrı eleman olsaydı biri diğerinin üstünde
                  belirir, "açılma" hissi kaybolurdu. */}
              <motion.span
                className="absolute h-px w-[min(420px,60vw)] origin-center"
                style={{
                  background:
                    'linear-gradient(90deg, transparent, var(--color-primary), transparent)',
                  boxShadow: '0 0 22px var(--color-primary)',
                }}
                initial={{ scaleX: 0, opacity: 0 }}
                animate={{
                  scaleX: [0, 0.012, 1],
                  opacity: [0, 1, 0.85],
                }}
                transition={{
                  duration: SWEEP_DELAY + 0.5,
                  delay: IGNITION_DELAY,
                  times: [0, 0.42, 1],
                  ease: [0.22, 1, 0.36, 1],
                }}
              />

              {/* Ateşleme parlaması — hattın doğduğu noktada tek bir nefes. */}
              <motion.span
                className="absolute h-24 w-24 rounded-full"
                style={{
                  background: 'radial-gradient(circle, rgba(127,178,255,0.55), transparent 70%)',
                }}
                initial={{ scale: 0.2, opacity: 0 }}
                animate={{ scale: [0.2, 1.6, 2.6], opacity: [0, 0.9, 0] }}
                transition={{ duration: 1.1, delay: IGNITION_DELAY, ease: 'easeOut' }}
              />

              {/* ── İsim ──
                  Solarak DEĞİL, çözülerek geliyor: bulanıklık dağılıyor ve harf
                  aralığı toplanıyor — ışıktan bir şeyin odaklanması gibi. */}
              <motion.span
                className="text-foreground relative pl-[0.42em] text-4xl font-semibold"
                variants={WORD_VARIANTS}
                initial="hidden"
                animate="visible"
              >
                CHIRON
              </motion.span>

              {/* Gerçek durum — sahte bir yüzde değil (bkz. Notes/Bilinen-Tuzaklar
                  § Arayüzde dürüstlük). Backend'e bağlanılmadıysa öyle diyor. */}
              <motion.span
                className="label-micro absolute top-[calc(50%+46px)]"
                variants={SUPPORT_VARIANTS}
                initial="hidden"
                animate="visible"
              >
                {connected ? 'Sistem hazır' : 'Bağlanıyor'}
              </motion.span>
            </>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
