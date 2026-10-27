'use client';

import { useEffect, useState } from 'react';
import { LuSend } from 'react-icons/lu';
import { useConversationStore } from '@/stores/conversationStore';
import { fetchVoiceStatus, sendTextCommand } from '@/services/voiceApi';
import { ConversationLog } from './ConversationLog';

// Sesli asistanın (main.py → ChironLive) sohbet arayüzü. Sağ alttaki dock'un
// içinde yaşıyor (bkz. AssistantDock.tsx); komutlar backend/api/voice.py
// üzerinden ChironLive'a gidiyor.
//
// YAZI KUTUSU ÖNEMLİ: mikrofon arızalıyken bile Chiron'la konuşmayı mümkün kılıyor —
// Live oturumu `response_modalities=["AUDIO"]` olduğu için cevap SESLİ geliyor.
export function VoicePanelContent() {
  const connected = useConversationStore((state) => state.connected);
  const ready = useConversationStore((state) => state.ready);
  const setStatus = useConversationStore((state) => state.setStatus);
  const [assistantRunning, setAssistantRunning] = useState<boolean | null>(null);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  // Asistan bu süreçte çalışıyor mu, ve canlı oturumu kuruldu mu?
  // (Arayüz tek başına da açılabiliyor — desktop.py --sadece-arayuz.)
  // Açılışta bir kez soruluyor; sonrasında durum WebSocket'ten (assistant_status)
  // geliyor — oturum birkaç saniye sonra kurulduğunda kutu kendiliğinden açılsın.
  useEffect(() => {
    let cancelled = false;
    void fetchVoiceStatus().then((status) => {
      if (cancelled) return;
      setAssistantRunning(status.connected);
      setStatus({ ready: status.ready });
    });
    return () => {
      cancelled = true;
    };
  }, [connected, setStatus]);

  const canSend = assistantRunning !== false && ready;
  const placeholder =
    assistantRunning === false
      ? 'Chiron çalışmıyor'
      : ready
        ? 'Chiron’a yaz...'
        : 'Chiron bağlanıyor...';

  const submit = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    setError('');
    const result = await sendTextCommand(text);
    setSending(false);
    if (result.success) {
      setDraft('');
    } else {
      setError(result.message);
    }
  };

  return (
    <div className="flex flex-col gap-3.5">
      <ConversationLog />

      <div className="flex items-center gap-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder={placeholder}
          disabled={!canSend}
          className="border-border-subtle text-foreground placeholder:text-foreground-disabled focus-visible:border-primary/50 min-w-0 flex-1 rounded-full border bg-white/[0.04] px-3.5 py-2 text-xs transition-colors duration-200 disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!draft.trim() || sending || !canSend}
          aria-label="Gönder"
          className="border-border-subtle text-foreground-secondary hover:text-primary hover:border-primary/40 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border bg-white/[0.04] transition-all duration-200 disabled:opacity-40 disabled:hover:border-[var(--border-subtle)]"
        >
          <LuSend size={13} strokeWidth={1.8} />
        </button>
      </div>

      {error && <p className="text-[11px] text-[#ff8f8f]">{error}</p>}

      {assistantRunning === false && (
        <p className="text-foreground-secondary text-[11px] leading-relaxed">
          Sesli asistan bu pencerede çalışmıyor. Masaüstündeki <strong>Chiron 3D</strong> kısayoluyla
          açarsan ses, araçlar ve sohbet burada olur.
        </p>
      )}
    </div>
  );
}
