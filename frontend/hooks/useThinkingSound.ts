'use client';

import { useEffect } from 'react';
import { useAIStateStore } from '@/stores/aiStateStore';
import { useConversationStore } from '@/stores/conversationStore';
import { usePowerStore } from '@/stores/powerStore';
import { setThinkingLoop } from '@/services/sfxPlayer';

// `SFX/Think.mp3` projede baştan beri duruyordu ama hiçbir yerden çalınmıyordu
// (bkz. Docs/CHIRON_UI_ROADMAP.md § Küçük artıklar). Kullanıcı isteğiyle
// (2026-07-30) bağlandı.
//
// Durum bazlı, olay bazlı DEĞİL: Chiron "düşünüyor" olduğu SÜRECE çalıyor. Her
// düşünme başlangıcında tek atış çalmak, arka arkaya araç çağrılarında sesin
// takır takır tekrar etmesine yol açardı.
export function useThinkingSound() {
  const isThinking = useAIStateStore((state) => state.aiState === 'thinking');
  const isAsleep = usePowerStore((state) => state.powerState === 'asleep');
  // Uzak mod (2026-09-15): kullanıcı evde değil, PC hoparlörü kapalı. Boş odada
  // saniyelerce süren bir düşünme döngüsü tam da uzak modun önlediği şey.
  const isRemote = useConversationStore((state) => state.remote);

  useEffect(() => {
    // Uykuda sahne karanlık ve sessiz — arka planda düşünme sesi devam etmesi
    // uyuyan bir sistemle çelişirdi.
    setThinkingLoop(isThinking && !isAsleep && !isRemote);
    return () => setThinkingLoop(false);
  }, [isThinking, isAsleep, isRemote]);
}
