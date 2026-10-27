'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { usePowerStore } from '@/stores/powerStore';
import { playSfx } from '@/services/sfxPlayer';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';

// CHIRON uyku perdesi — çekirdeğe tıklanınca "ortam karanlığa bürünüyor"
// (kullanıcı isteği, 2026-07-30).
//
// NEDEN DÜZ SİYAH DEĞİL: tam opak bir perde sahneyi kapatır ve uygulama çökmüş
// gibi görünür. Bunun yerine MERKEZİ AÇIK bir radyal gradyan: kenarlar dibe
// iniyor, ortada çekirdeğin sönük nefesi görünmeye devam ediyor. Chiron kapanmış
// değil, uyuyor — ve uyuduğu görülüyor.
//
// Perde tüm ekranı kaplıyor ve her yere tıklamak uyandırıyor: uyuyan bir
// sistemde kullanıcıyı 3D sahnedeki bir küreyi nişan almaya zorlamak, ödülü
// olmayan bir beceri sınavı olurdu.
const FADE_IN_S = 1.1;
const FADE_OUT_S = 0.55;
const HINT_DELAY_S = 1.4;

export function SleepVeil() {
  const isAsleep = usePowerStore((state) => state.powerState === 'asleep');
  const wake = usePowerStore((state) => state.wake);
  const reducedMotion = usePrefersReducedMotion();

  return (
    <AnimatePresence>
      {isAsleep && (
        <motion.button
          type="button"
          aria-label="Chiron'u uyandır"
          onClick={() => {
            wake();
            playSfx('hud');
          }}
          initial={{ opacity: 0 }}
          animate={{
            opacity: 1,
            transition: { duration: reducedMotion ? 0.15 : FADE_IN_S, ease: 'easeInOut' },
          }}
          // Uyanma, uyumaktan HIZLI: sisteme geri dönmek beklemek gibi
          // hissettirmemeli. Uyumak yavaş ve sinematik, uyanmak anında.
          exit={{
            opacity: 0,
            transition: { duration: reducedMotion ? 0.1 : FADE_OUT_S, ease: 'easeOut' },
          }}
          // z-40: HUD (z-30) ve vinyetin (z-10) üstünde, açılış perdesinin
          // (BootOverlay, z-50) altında.
          className="fixed inset-0 z-40 cursor-pointer"
          style={{
            // Merkez bilerek şeffaf — çekirdek görünmeye devam ediyor.
            background:
              'radial-gradient(circle at 50% 50%, rgba(2,4,9,0) 7%, rgba(2,4,9,0.62) 34%, rgba(2,4,9,0.9) 72%, rgba(2,4,9,0.97) 100%)',
          }}
        >
          <motion.span
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: reducedMotion ? 0.15 : 0.7,
              delay: reducedMotion ? 0 : HINT_DELAY_S,
              ease: [0.22, 1, 0.36, 1],
            }}
            className="label-micro absolute bottom-[16%] left-1/2 -translate-x-1/2 whitespace-nowrap"
          >
            Uyandırmak için dokun
          </motion.span>
        </motion.button>
      )}
    </AnimatePresence>
  );
}
