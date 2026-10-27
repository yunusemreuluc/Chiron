'use client';

import { useEffect, useRef, useState } from 'react';
import { LuLogOut, LuVolume2, LuVolumeX } from 'react-icons/lu';
import { AI_STATE_LABELS, useAIStateStore } from '@/stores/aiStateStore';
import { useConversationStore } from '@/stores/conversationStore';
import { useRemoteStore } from '@/stores/remoteStore';
import { logoutRemote, setRemoteMode } from '@/services/remoteApi';
import { RemoteCore } from './RemoteCore';

const CONFIRM_TIMEOUT_MS = 3200;

/**
 * Durum satırı. Sıra önemli: her koşul bir öncekinin DOĞRU olduğunu varsayıyor.
 * "Dinliyor" yalnızca gerçekten komut kabul edilebiliyorken yazıyor — telefona
 * "hazır" deyip yazılanı sessizce kaybetmek en kötü hata olurdu.
 */
function useStatusLine(): { text: string; tone: 'ok' | 'wait' | 'off' } {
  const connected = useConversationStore((state) => state.connected);
  const ready = useConversationStore((state) => state.ready);
  const paused = useConversationStore((state) => state.paused);
  const running = useRemoteStore((state) => state.assistantRunning);
  const aiState = useAIStateStore((state) => state.aiState);

  if (!connected) return { text: 'PC’ye ulaşılamıyor', tone: 'off' };
  if (running === false) return { text: 'Sesli asistan kapalı', tone: 'off' };
  if (paused) return { text: 'Duraklatıldı', tone: 'wait' };
  if (!ready) return { text: 'Bağlanıyor', tone: 'wait' };
  return { text: AI_STATE_LABELS[aiState === 'idle' ? 'listening' : aiState], tone: 'ok' };
}

const TONE_DOT: Record<'ok' | 'wait' | 'off', string> = {
  ok: 'bg-primary shadow-[0_0_8px_rgba(127,178,255,0.7)]',
  wait: 'bg-[#e0a355] shadow-[0_0_8px_rgba(224,163,85,0.6)]',
  off: 'bg-[#ff8f8f]/80',
};

export function RemoteHeader() {
  const aiState = useAIStateStore((state) => state.aiState);
  const connected = useConversationStore((state) => state.connected);
  const remote = useConversationStore((state) => state.remote);
  const setGate = useRemoteStore((state) => state.setGate);
  const status = useStatusLine();

  const [isArmed, setIsArmed] = useState(false);
  const armTimer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(armTimer.current), []);

  // Çıkış iki adımlı: başparmağın yanlışlıkla değdiği 40px'lik bir hedef,
  // dışarıdayken PIN'i yeniden girmek zorunda bırakmamalı.
  const handleLogout = async () => {
    if (!isArmed) {
      setIsArmed(true);
      window.clearTimeout(armTimer.current);
      armTimer.current = window.setTimeout(() => setIsArmed(false), CONFIRM_TIMEOUT_MS);
      return;
    }
    window.clearTimeout(armTimer.current);
    await logoutRemote();
    setGate('locked');
  };

  return (
    <header className="remote-safe-top relative z-20 flex items-center gap-3 px-4 pb-3">
      <RemoteCore state={aiState} size={42} online={connected} />

      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <span className="text-foreground text-[16px] leading-none font-semibold tracking-[-0.01em]">
          Chiron
        </span>
        <span className="text-foreground-secondary flex items-center gap-1.5 text-[12px] leading-none">
          <span
            className={`h-1.5 w-1.5 shrink-0 rounded-full transition-all duration-500 ${TONE_DOT[status.tone]}`}
          />
          <span className="truncate">{status.text}</span>
        </span>
      </div>

      {/* PC hoparlörü. Uzak modda kapalı — telefondan yazınca kendiliğinden
          kapanıyor (backend/api/voice.py). Açmak, evdeki birine Chiron'u
          duyurmak istendiğinde işe yarıyor. */}
      <button
        type="button"
        onClick={() => void setRemoteMode(!remote)}
        disabled={!connected}
        aria-pressed={!remote}
        className={`ease-out-quint flex h-10 items-center gap-2 rounded-full border px-3.5 text-[12px] font-medium transition-all duration-300 active:scale-[0.97] disabled:opacity-40 ${
          remote
            ? 'border-border-subtle text-foreground-secondary bg-white/[0.04]'
            : 'border-[#e0a355]/40 bg-[#e0a355]/10 text-[#e0a355]'
        }`}
      >
        {remote ? <LuVolumeX size={15} strokeWidth={1.8} /> : <LuVolume2 size={15} strokeWidth={1.8} />}
        {remote ? 'PC sessiz' : 'PC sesli'}
      </button>

      <button
        type="button"
        onClick={() => void handleLogout()}
        aria-label={isArmed ? 'Çıkışı onayla' : 'Çıkış yap'}
        className={`ease-out-quint flex h-10 items-center justify-center gap-1.5 rounded-full border transition-all duration-300 active:scale-[0.97] ${
          isArmed
            ? 'border-[#ff8f8f]/40 bg-[#ff8f8f]/10 px-3.5 text-[12px] font-medium text-[#ff8f8f]'
            : 'border-border-subtle text-foreground-secondary w-10 bg-white/[0.04]'
        }`}
      >
        <LuLogOut size={15} strokeWidth={1.8} />
        {isArmed && 'Çık?'}
      </button>
    </header>
  );
}
