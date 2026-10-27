'use client';

import { useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { STATE_PALETTE } from '@/three/coreColors';
import { useAIStateStore } from '@/stores/aiStateStore';
import { useConversationStore } from '@/stores/conversationStore';
import { useRemoteStore } from '@/stores/remoteStore';
import { fetchRemoteSession } from '@/services/remoteApi';
import { useRemoteConnection } from '@/hooks/useRemoteConnection';
import { PinGate } from './PinGate';
import { RemoteComposer, type RemoteComposerHandle } from './RemoteComposer';
import { RemoteConversation } from './RemoteConversation';
import { RemoteCore } from './RemoteCore';
import { RemoteHeader } from './RemoteHeader';

// Telefon arayüzünün kabuğu (app/m). Üç hâl: oturum soruluyor → PIN kapısı →
// sohbet. Evden uzaktayken PC'yi sorgulamak için (Notes/Uzaktan-Erisim.md).
export function RemoteShell() {
  const gate = useRemoteStore((state) => state.gate);
  const setGate = useRemoteStore((state) => state.setGate);
  const composerRef = useRef<RemoteComposerHandle>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchRemoteSession().then((session) => {
      if (cancelled) return;
      // Backend'e hiç ulaşılamadıysa kapıyı göster: oradaki istek de başarısız
      // olur ve kullanıcı en azından nerede takıldığını görür.
      setGate(session?.authenticated ? 'open' : 'locked');
    });
    return () => {
      cancelled = true;
    };
  }, [setGate]);

  useRemoteConnection(gate === 'open');

  return (
    <main className="remote-root bg-background relative flex flex-col overflow-hidden">
      <Backdrop />
      <AnimatePresence mode="wait">
        {gate === 'checking' && (
          <motion.div
            key="checking"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, filter: 'blur(8px)' }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            className="relative z-10 flex flex-1 items-center justify-center"
          >
            <RemoteCore state="thinking" size={112} />
          </motion.div>
        )}
        {gate === 'locked' && <PinGate key="locked" />}
        {gate === 'open' && (
          <motion.div
            key="open"
            initial={{ opacity: 0, filter: 'blur(8px)' }}
            animate={{ opacity: 1, filter: 'blur(0px)' }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="relative z-10 flex min-h-0 flex-1 flex-col"
          >
            <RemoteHeader />
            <RemoteConversation onPrompt={(text) => composerRef.current?.send(text)} />
            <RemoteComposer ref={composerRef} />
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}

/**
 * Zemin — masaüstündeki yıldız alanı ve ufuk parıltısının sakin karşılığı.
 * Üstteki ışık Chiron'un durum rengini alıyor: telefon cepten çıkarıldığında
 * "konuşuyor mu, iş mi yapıyor" daha metni okumadan görünsün.
 */
function Backdrop() {
  const aiState = useAIStateStore((state) => state.aiState);
  const connected = useConversationStore((state) => state.connected);
  const tone = connected ? STATE_PALETTE[aiState].bodyLight : '#28374d';

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute -top-[30vh] left-1/2 h-[70vh] w-[140vw] -translate-x-1/2 rounded-full"
        style={{
          backgroundColor: tone,
          opacity: 0.13,
          filter: 'blur(90px)',
          transition: 'background-color 1200ms var(--ease-standard)',
        }}
      />
      <div
        className="absolute -bottom-[25vh] left-1/2 h-[45vh] w-[120vw] -translate-x-1/2 rounded-full"
        style={{ backgroundColor: '#3f6db8', opacity: 0.07, filter: 'blur(80px)' }}
      />
      {/* İnce ızgara — HUD dokusu; neredeyse görünmez, cam yüzeylere derinlik veriyor. */}
      <div
        className="absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.9) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.9) 1px, transparent 1px)',
          backgroundSize: '44px 44px',
          maskImage: 'radial-gradient(ellipse at 50% 20%, #000 0%, transparent 70%)',
          WebkitMaskImage: 'radial-gradient(ellipse at 50% 20%, #000 0%, transparent 70%)',
        }}
      />
    </div>
  );
}
