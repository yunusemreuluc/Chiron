'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  LuBell,
  LuBrain,
  LuGlobe,
  LuSettings,
  LuUserRound,
  LuUsers,
  LuWorkflow,
} from 'react-icons/lu';
import type { IconType } from 'react-icons';
import { useNavigationStore, type ModuleId } from '@/stores/navigationStore';
import { useRailHoverStore } from '@/stores/railHoverStore';
import { GlassPanel } from './GlassPanel';

interface SidebarItem {
  id: ModuleId;
  label: string;
  icon: IconType;
}

// 'Ses' burada YOK — sohbet sağ alt köşedeki dock'a taşındı (AssistantDock.tsx).
const SIDEBAR_ITEMS: SidebarItem[] = [
  { id: 'memory', label: 'Hafıza', icon: LuBrain },
  { id: 'automation', label: 'Otomasyon', icon: LuWorkflow },
  { id: 'agents', label: 'Ajanlar', icon: LuUsers },
  { id: 'browser', label: 'Tarayıcı', icon: LuGlobe },
];

// Hover'da isim gösteren yuvarlak ikon düğmesi — hem modül ikonları hem alttaki
// bildirim/profil için ortak (Notes/Tasarim-Kurallari.md § Panel yerleşimi: "Icons only... No labels unless
// hovered").
//
// Aktiflik göstergesi (2026-07-28, "daha profesyonel"): önceki dolgu + geniş sarı
// gölge yerine artık rayın SOL KENARINDA kayan ince bir hat var. Framer Motion'ın
// `layoutId`'si sayesinde hat modüller arasında sıçramadan akıyor — Linear/Vercel
// sınıfı arayüzlerin sakin aktiflik dili. Dolgu ve ışıma korunuyor ama çok daha kısık.
function RailButton({
  label,
  icon: Icon,
  isActive = false,
  onClick,
}: {
  label: string;
  icon: IconType;
  isActive?: boolean;
  onClick?: () => void;
}) {
  const [isHovered, setIsHovered] = useState(false);

  // YAPI NOTU (2026-07-31): aktiflik hattı ve etiket balonu artık butonun DIŞINDA,
  // saran kutuda duruyor. Sebep hover büyümesi: ölçek butona uygulanıyor ve
  // ikisi de içeride kalsaydı onlar da büyürdü — `layoutId` ile animasyonlu hat
  // ölçeklenmiş bir kutuda ölçüldüğü için modül değişiminde yanlış konuma
  // akardı, etiket balonundaki yazı da 11px'ten oynardı. Saran kutu butonla
  // aynı geometride olduğu için `left-full` / `-left-[13px]` konumları aynen
  // geçerli kalıyor.
  return (
    <div className="relative flex items-center">
      {isActive && (
        <motion.span
          layoutId="rail-active-indicator"
          className="bg-primary absolute -left-[13px] h-5 w-[2px] rounded-full"
          style={{ boxShadow: '0 0 10px var(--color-primary)' }}
          transition={{ type: 'spring', stiffness: 420, damping: 34 }}
        />
      )}
      <button
        type="button"
        aria-label={label}
        aria-current={isActive ? 'true' : undefined}
        onClick={onClick}
        // Yerel durum etiketi gösteriyor, store ise AIRON imzasına "çekil"
        // diyor (bkz. stores/railHoverStore.ts) — ikisi aynı olayın iki ayrı
        // sonucu, o yüzden birlikte set ediliyor.
        onMouseEnter={() => {
          setIsHovered(true);
          useRailHoverStore.getState().setHoveredLabel(label);
        }}
        onMouseLeave={() => {
          setIsHovered(false);
          // Koşulsuz `null` YAZMA: bir düğmeden komşusuna geçerken tarayıcı
          // leave(A) ile enter(B) olaylarını bu sırayla göndermeyi garanti
          // etmiyor. leave(A) sonra gelirse, kullanıcı B'nin üstündeyken imza
          // geri parlar ve etiketin altında kalırdı. Yalnızca hâlâ BİZ
          // yazılıysak temizliyoruz.
          const store = useRailHoverStore.getState();
          if (store.hoveredLabel === label) store.setHoveredLabel(null);
        }}
        // Notes/Tasarim-Kurallari.md § Panel yerleşimi — "hover'da hafifçe büyür".
        // 1.08: 40px'lik bir düğmede ~3px, yani hissedilen ama ölçülmesi zor bir
        // fark. Daha fazlası rayı zıplatıyor, daha azı fark edilmiyor.
        // `active:scale-95` bastırma geri bildirimi: büyüme varsa basmanın da
        // karşılığı olmalı, yoksa düğme hover'da canlı, tıklamada ölü hissediyor.
        className={`ease-out-quint flex h-10 w-10 items-center justify-center rounded-[14px] transition-all duration-200 hover:scale-[1.08] active:scale-95 ${
          isActive
            ? 'text-primary bg-white/[0.07] shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_0_18px_rgba(127,178,255,0.18)]'
            : 'text-foreground-secondary hover:text-foreground hover:bg-white/[0.05]'
        }`}
      >
        <Icon size={19} strokeWidth={1.6} />
      </button>
      <span
        className={`node-label-card text-foreground pointer-events-none absolute left-full z-30 ml-3.5 px-2.5 py-1.5 text-[11px] font-medium tracking-[0.06em] whitespace-nowrap transition-all duration-200 ${
          isHovered ? 'translate-x-0 opacity-100' : '-translate-x-1 opacity-0'
        }`}
      >
        {label}
      </span>
    </div>
  );
}

// Kullanıcı isteğiyle (2026-07-28) — üst panel kaldırıldığı için bildirim ve profil
// buraya, rayın en altına taşındı.
export function Sidebar() {
  const activeModule = useNavigationStore((state) => state.activeModule);
  const toggleModule = useNavigationStore((state) => state.toggleModule);
  const [isBellOpen, setIsBellOpen] = useState(false);

  return (
    <GlassPanel as="nav" className="flex h-full flex-col items-center gap-1.5 px-3 py-4">
      {SIDEBAR_ITEMS.map(({ id, label, icon: Icon }) => (
        <RailButton
          key={id}
          label={label}
          icon={Icon}
          isActive={id === activeModule}
          onClick={() => toggleModule(id)}
        />
      ))}

      <div className="mt-auto flex w-full flex-col items-center gap-2">
        {/* Ayraç: modüller (birincil gezinme) ile ayarlar/bildirim/hesap (ikincil)
            arasında görsel bir sınır — ikisi aynı listeymiş gibi okunmasın diye. */}
        <hr className="hairline mb-1 w-6" />
        <RailButton
          label="Ayarlar"
          icon={LuSettings}
          isActive={activeModule === 'settings'}
          onClick={() => toggleModule('settings')}
        />
        <div className="relative">
          <RailButton
            label="Bildirimler"
            icon={LuBell}
            onClick={() => setIsBellOpen((value) => !value)}
          />
          {isBellOpen && (
            <div className="node-label-card text-foreground-secondary absolute bottom-0 left-full z-30 ml-3.5 w-52 px-3 py-2.5 text-[11px] leading-relaxed">
              Henüz bir bildirim yok.
            </div>
          )}
        </div>
        <button
          type="button"
          title="Kullanıcı"
          aria-label="Kullanıcı"
          className="border-border-subtle text-foreground-secondary hover:border-border-strong hover:text-foreground ease-out-quint flex h-9 w-9 items-center justify-center rounded-full border bg-white/[0.04] transition-all duration-200 hover:scale-[1.08] active:scale-95"
        >
          <LuUserRound size={15} strokeWidth={1.6} />
        </button>
      </div>
    </GlassPanel>
  );
}
