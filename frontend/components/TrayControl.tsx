'use client';

import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { LuMoonStar } from 'react-icons/lu';
import { minimizeToTray } from '@/services/settingsApi';
import { playSfx } from '@/services/sfxPlayer';

// CHIRON — "tepsiye al" kontrolü.
//
// Kullanıcı isteğiyle (2026-07-30) ayarlar panelinden ÇIKARILDI. Orada dört
// bölüm aşağıda, "Windows" başlığının altında gömülü bir düğmeydi: pencereyi
// gizlemek gibi sık ve tek hamlelik bir eylem için üç tıklama (ray → ayarlar →
// kaydır → düğme) gerekiyordu.
//
// NEDEN SAĞ ÜST: sol üst Chiron imzası (BrandBadge), sol kenar modül rayı
// (Sidebar), sol orta modül paneli (LeftPanel), sağ alt sohbet (AssistantDock).
// Sağ üst, her masaüstü uygulamasında pencere kontrollerinin bulunduğu köşe —
// "pencereyi gizle" oraya ait. Düğüm odak kartı da bu köşedeydi; çakışmasın
// diye o bir sıra aşağı indi (bkz. NodeFocusCard.tsx).
//
// NEDEN AY+YILDIZ İKONU: eylem "küçült" değil, "Chiron'u arka plana uyut".
// Klasik küçültme çizgisi (LuMinimize2) pencere yönetimi diliyle konuşuyor;
// ay ise sistemin durumuyla. Aynı zamanda çekirdeğe tıklayınca girilen uyku
// moduyla (SleepVeil) aynı dili paylaşıyor: biri sahneyi uyutuyor, bu
// pencereyi.
const NOTICE_TIMEOUT_MS = 3600;

export function TrayControl() {
  const [isHovered, setIsHovered] = useState(false);
  const [notice, setNotice] = useState('');
  const noticeTimer = useRef<number | undefined>(undefined);

  // Zamanlayıcı bileşen sökülürken temizleniyor: aksi hâlde sökülmüş bir
  // bileşende setState çağrılırdı.
  useEffect(() => () => window.clearTimeout(noticeTimer.current), []);

  const sendToTray = async () => {
    const result = await minimizeToTray();
    if (result.success) {
      playSfx('hud');
      return;
    }
    // Tepsi yalnızca masaüstü penceresinde çalışıyor (bkz. desktop.py
    // TrayController). Tarayıcıda geliştirme modunda bu uç "asistan bağlı
    // değil" diyor — sessizce yutmak yerine söyleniyor.
    playSfx('error');
    setNotice(result.message);
    window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setNotice(''), NOTICE_TIMEOUT_MS);
  };

  const label = notice || 'Tepsiye al';

  // Konumlandırma AppShell'deki sağ kolona ait (2026-07-30) — panel yığını
  // büyüdükçe her bileşenin kendini mutlak konumlamaya çalışması çakışma
  // üretiyordu.
  return (
    <div className="flex items-center gap-2.5">
      {/* Etiket düğmenin SOLUNDA açılıyor (Sidebar'da sağında) — sağ kenardaki
          bir öğenin ipucu ekran dışına taşmasın diye. */}
      <span
        className={`node-label-card text-foreground pointer-events-none px-2.5 py-1.5 text-[11px] font-medium tracking-[0.06em] whitespace-nowrap transition-all duration-200 ${
          isHovered || notice ? 'translate-x-0 opacity-100' : 'translate-x-1 opacity-0'
        }`}
      >
        {label}
      </span>

      <motion.button
        type="button"
        aria-label="Tepsiye al"
        onClick={() => void sendToTray()}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        whileTap={{ scale: 0.94 }}
        // Notes/Tasarim-Kurallari.md § Animasyon — "Everything moves. Nothing feels
        // static." Çok yavaş bir nefes: köşede duran ölü bir ikon değil.
        animate={{ opacity: [0.82, 1, 0.82] }}
        transition={{ duration: 5.5, repeat: Infinity, ease: 'easeInOut' }}
        className="glass-panel text-foreground-secondary hover:text-primary hover:border-primary/40 flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-full transition-colors duration-200"
        style={{ borderRadius: 999 }}
      >
        <LuMoonStar size={16} strokeWidth={1.6} />
      </motion.button>
    </div>
  );
}
