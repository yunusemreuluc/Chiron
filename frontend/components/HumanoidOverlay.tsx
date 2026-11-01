'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { request } from '@/services/apiClient';
import { playMaterialize } from '@/services/sfxPlayer';
import { useConversationStore } from '@/stores/conversationStore';
import { useHumanoidStore } from '@/stores/humanoidStore';

// İnsan görünümünün HTML katmanı (sahne: three/HumanoidBust.tsx):
//   • H tuşu aç/kapa, Esc kapatır — şıklatmanın klavye karşılığı.
//   • Geçişte sentez sesi (services/sfxPlayer.ts playMaterialize).
//   • Altta kısa bir duyuru ("İnsan görünümü açılıyor"), ardından sönük bir ipucu.
// Bayrağın sahibi backend (core/web_ui.py); burada önce yerel olarak çevrilip
// sonra backend'e bildiriliyor — backend kapalıysa yerel değer geçerli kalıyor.

const CAPTION_MS = { open: 2600, close: 1600 };

function setHumanoid(next: boolean) {
  useHumanoidStore.getState().setActive(next);
  void request('/api/voice/humanoid', { method: 'POST', body: JSON.stringify({ value: next }) });
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}

export function HumanoidOverlay() {
  const active = useHumanoidStore((state) => state.active);
  const [caption, setCaption] = useState<'open' | 'close' | null>(null);
  const previous = useRef(active);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.altKey || event.metaKey || isTyping(event.target)) return;
      const current = useHumanoidStore.getState().active;
      if (event.key === 'Escape' && current) setHumanoid(false);
      else if (event.key === 'h' || event.key === 'H') setHumanoid(!current);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    // Yalnızca gerçek geçişler ses/duyuru alıyor (StrictMode'un çift çalıştırması değil).
    if (previous.current === active) return;
    previous.current = active;
    const kind = active ? 'open' : 'close';
    // Uzak modda PC hoparlörü susuyor — geçiş sesi de susmalı.
    if (!useConversationStore.getState().remote) playMaterialize(active);
    setCaption(kind);
    const timer = setTimeout(() => setCaption(null), CAPTION_MS[kind]);
    return () => clearTimeout(timer);
  }, [active]);

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-10 z-40 flex justify-center">
      <AnimatePresence mode="wait">
        {caption ? (
          <motion.div
            key={caption}
            initial={{ opacity: 0, y: 12, filter: 'blur(6px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: -6, filter: 'blur(4px)' }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            className="flex items-center gap-3 rounded-full border border-sky-300/20 bg-black/45 px-5 py-2.5 backdrop-blur-md"
          >
            <span className="flex h-3.5 items-end gap-[3px]" aria-hidden>
              {[0.55, 1, 0.7, 0.4].map((h, i) => (
                <motion.span
                  key={i}
                  className="w-[3px] rounded-full bg-sky-300"
                  animate={{ height: [`${h * 40}%`, `${h * 100}%`, `${h * 40}%`] }}
                  transition={{ duration: 0.7, repeat: Infinity, delay: i * 0.12 }}
                />
              ))}
            </span>
            <span className="font-mono text-[12px] tracking-[0.28em] text-sky-100 uppercase">
              {caption === 'open' ? 'İnsan görünümü açılıyor' : 'Çekirdeğe dönülüyor'}
            </span>
          </motion.div>
        ) : active ? (
          <motion.div
            key="hint"
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.4 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.2 }}
            className="font-mono text-[10px] tracking-[0.32em] text-sky-200/80 uppercase"
          >
            çift şıklat · H · Esc — çıkış
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
