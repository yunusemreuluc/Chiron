'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { LuSettings, LuUsers } from 'react-icons/lu';
import type { IconType } from 'react-icons';
import { useNavigationStore, type ModuleId } from '@/stores/navigationStore';
import { GlassPanel } from './GlassPanel';

// Kullanıcı isteği (2026-10-29): "yan barı kaldır, ayarlar ve ajanlar kısmı tek kalsın".
// Tam boy ikon rayı (Hafıza, Otomasyon, Tarayıcı, Bildirimler, Profil) gitti — boş ya da
// kullanılmayan girişlerdi. Kalan iki düğme sol altta küçük bir cam çubukta: sağ alttaki
// sohbet dock'unun (AssistantDock) aynası, sahne iki yandan dengeli kalıyor.
const ITEMS: { id: ModuleId; label: string; icon: IconType }[] = [
  { id: 'agents', label: 'Ajanlar', icon: LuUsers },
  { id: 'settings', label: 'Ayarlar', icon: LuSettings },
];

function NavButton({
  label,
  icon: Icon,
  isActive,
  onClick,
}: {
  label: string;
  icon: IconType;
  isActive: boolean;
  onClick: () => void;
}) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <div className="relative flex items-center">
      {/* Aktiflik: düğmenin ALTINDA kayan ince hat — dock'un dilinde, layoutId ile iki
          düğme arasında sıçramadan akar. */}
      {isActive && (
        <motion.span
          layoutId="nav-active-indicator"
          className="bg-primary absolute -bottom-[7px] left-1/2 h-[2px] w-5 -translate-x-1/2 rounded-full"
          style={{ boxShadow: '0 0 10px var(--color-primary)' }}
          transition={{ type: 'spring', stiffness: 420, damping: 34 }}
        />
      )}
      <button
        type="button"
        aria-label={label}
        aria-current={isActive ? 'true' : undefined}
        onClick={onClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={`ease-out-quint flex h-10 w-10 items-center justify-center rounded-[14px] transition-all duration-200 hover:scale-[1.08] active:scale-95 ${
          isActive
            ? 'text-primary bg-white/[0.07] shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_0_18px_rgba(127,178,255,0.18)]'
            : 'text-foreground-secondary hover:text-foreground hover:bg-white/[0.05]'
        }`}
      >
        <Icon size={18} strokeWidth={1.6} />
      </button>
      <span
        className={`node-label-card text-foreground pointer-events-none absolute bottom-full left-1/2 z-30 mb-2.5 -translate-x-1/2 px-2.5 py-1.5 text-[11px] font-medium whitespace-nowrap transition-all duration-200 ${
          isHovered ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        }`}
      >
        {label}
      </span>
    </div>
  );
}

export function Sidebar() {
  const activeModule = useNavigationStore((state) => state.activeModule);
  const toggleModule = useNavigationStore((state) => state.toggleModule);

  return (
    <GlassPanel as="nav" className="flex items-center gap-1.5 px-2.5 py-2">
      {ITEMS.map(({ id, label, icon }) => (
        <NavButton
          key={id}
          label={label}
          icon={icon}
          isActive={id === activeModule}
          onClick={() => toggleModule(id)}
        />
      ))}
    </GlassPanel>
  );
}
