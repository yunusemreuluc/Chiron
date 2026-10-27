'use client';

import { AnimatePresence, motion } from 'framer-motion';
import {
  LuBrain,
  LuGlobe,
  LuSettings,
  LuUsers,
  LuWorkflow,
  LuX,
} from 'react-icons/lu';
import type { IconType } from 'react-icons';
import { useNavigationStore, type ModuleId } from '@/stores/navigationStore';
import { AutomationPanelContent } from './AutomationPanelContent';
import { GlassPanel } from './GlassPanel';
import { MemoryPanelContent } from './MemoryPanelContent';
import { SettingsPanelContent } from './SettingsPanelContent';

interface ModuleContent {
  title: string;
  icon: IconType;
  /** Kendi içeriği olan modüller bunu kullanmıyor; yalnızca boş durum metni. */
  description: string;
  content?: React.ComponentType;
}

// Sol panel. Notes/Tasarim-Kurallari.md § Panel yerleşimi: "no unnecessary buttons" — aksiyon butonu
// yok, sadece durum.
//
// 2026-07-30'da Hafıza ve Otomasyon gerçek veriye bağlandı (backend/api/memory.py,
// backend/api/automation.py). Ajanlar ve Tarayıcı hâlâ dürüst boş durum
// gösteriyor: ikisinin de arkasında gösterilecek bir veri YOK — çoklu ajan
// sistemi planlama aşamasında, tarayıcı tarafı ise oturum durumu tutmuyor
// (yalnızca URL açıp arama yapıyor). Sahte veri üretmek yerine bunu söylüyorlar.
//
// 2026-10-02: Ajanlar artık burada değil — tam ekran Ajan Ofisi açılıyor
// (components/office/OfficeView.tsx). Kayıt aşağıda yalnız tip bütünlüğü için.
const MODULE_CONTENT: Record<ModuleId, ModuleContent> = {
  memory: {
    title: 'Hafıza',
    icon: LuBrain,
    description: '',
    content: MemoryPanelContent,
  },
  automation: {
    title: 'Otomasyon',
    icon: LuWorkflow,
    description: '',
    content: AutomationPanelContent,
  },
  agents: {
    title: 'Ajanlar',
    icon: LuUsers,
    description: '',
  },
  browser: {
    title: 'Tarayıcı',
    icon: LuGlobe,
    description:
      'Chiron tarayıcıda adres açıp arama yapabiliyor ama bir oturum durumu tutmuyor — burada gösterilecek bir şey yok. Sayfa içi etkileşim eklenince burası da dolacak.',
  },
  settings: {
    title: 'Ayarlar',
    icon: LuSettings,
    description: '',
    content: SettingsPanelContent,
  },
};

export function LeftPanel() {
  const activeModule = useNavigationStore((state) => state.activeModule);
  const toggleModule = useNavigationStore((state) => state.toggleModule);
  // Ajanlar sol panel değil, tam ekran ofis (OfficeView) — burada çizilmez.
  const content = activeModule && activeModule !== 'agents' ? MODULE_CONTENT[activeModule] : null;

  return (
    <AnimatePresence>
      {content && activeModule && (
        <motion.div
          key={activeModule}
          initial={{ opacity: 0, x: -20, filter: 'blur(6px)' }}
          animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, x: -20, filter: 'blur(6px)' }}
          // Hız + yumuşama: paneller "açılmıyor", odağa giriyor (ease-out-quint).
          transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
          className="absolute top-28 left-[104px] z-30 w-[286px]"
        >
          {/* NodeFocusCard ile aynı kart dili: mikro üst etiket + başlık, ince
              ayraç, uzun içerikte panel taşmasın diye kaydırılabilir gövde. */}
          <GlassPanel variant="card" className="flex max-h-[calc(100dvh-160px)] flex-col p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <span className="border-border-subtle flex h-7 w-7 items-center justify-center rounded-[9px] border bg-white/[0.04]">
                  <content.icon size={14} strokeWidth={1.7} className="text-primary" />
                </span>
                <span className="flex flex-col gap-1">
                  <span className="label-micro">Modül</span>
                  <span className="text-foreground text-[13px] leading-none font-medium">
                    {content.title}
                  </span>
                </span>
              </div>
              <button
                type="button"
                onClick={() => toggleModule(activeModule)}
                className="text-foreground-disabled hover:text-foreground -m-1 rounded-full p-1.5 transition-colors duration-200 hover:bg-white/[0.06]"
                aria-label="Paneli kapat"
              >
                <LuX size={13} strokeWidth={1.8} />
              </button>
            </div>

            <hr className="hairline my-4" />

            <div className="min-h-0 overflow-y-auto pr-0.5">
              {content.content ? (
                <content.content />
              ) : (
                <p className="text-foreground-secondary text-xs leading-relaxed">
                  {content.description}
                </p>
              )}
            </div>
          </GlassPanel>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
