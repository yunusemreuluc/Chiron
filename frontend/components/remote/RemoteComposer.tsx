'use client';

import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { LuArrowUp, LuPlay } from 'react-icons/lu';
import { useConversationStore } from '@/stores/conversationStore';
import { useRemoteStore } from '@/stores/remoteStore';
import { sendRemoteText } from '@/services/remoteApi';
import { setPaused } from '@/services/voiceApi';
import { REMOTE_PROMPTS } from './remotePrompts';

// Telefonun yazı kutusu. 16px yazı bilerek: iOS Safari 16px'ten küçük bir
// girişe odaklanınca sayfayı yakınlaştırıyor ve geri almıyor.

const MAX_TEXTAREA_PX = 132;

export interface RemoteComposerHandle {
  send: (text: string) => void;
}

export const RemoteComposer = forwardRef<RemoteComposerHandle>(function RemoteComposer(_, ref) {
  const connected = useConversationStore((state) => state.connected);
  const ready = useConversationStore((state) => state.ready);
  const paused = useConversationStore((state) => state.paused);
  const running = useRemoteStore((state) => state.assistantRunning);
  const setGate = useRemoteStore((state) => state.setGate);

  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Duraklatılmış Chiron metni SESSİZCE yutuyor (main.py _on_text_command) —
  // yazma kutusunu açık bırakmak, kaybolacak bir mesaj yazdırmak olurdu.
  const canSend = connected && ready && running !== false && !paused;
  const placeholder = !connected
    ? 'PC’ye ulaşılamıyor'
    : running === false
      ? 'Sesli asistan PC’de kapalı'
      : paused
        ? 'Chiron duraklatılmış'
        : ready
          ? 'Chiron’a yaz…'
          : 'Chiron bağlanıyor…';

  const hasConversation = useConversationStore((state) =>
    state.lines.some((line) => line.kind === 'user' || line.kind === 'chiron'),
  );
  const showChips = canSend && hasConversation && !draft && !sending;

  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = '0px';
    el.style.height = `${Math.min(MAX_TEXTAREA_PX, el.scrollHeight)}px`;
  }, [draft]);

  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || sending || !canSend) return;
    setSending(true);
    setError('');
    const result = await sendRemoteText(text);
    setSending(false);
    if (result.unauthorized) {
      setGate('locked');
      return;
    }
    if (result.success) {
      setDraft('');
    } else {
      setDraft(text); // yazılanı kaybettirme
      setError(result.message);
    }
  };

  useImperativeHandle(ref, () => ({ send: (text: string) => void send(text) }));

  return (
    <div className="remote-safe-bottom relative z-20 px-3 pt-2">
      <AnimatePresence>
        {error && (
          <motion.p
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="px-3 pb-2 text-[12px] text-[#ff8f8f]"
          >
            {error}
          </motion.p>
        )}
      </AnimatePresence>

      {/* Sohbet başladıktan sonra hazır istemler burada, tek satır çip olarak:
          karşılama ekranındaki kartlar kaybolunca "ekranda ne var" tekrar
          yazdırılmasın. Yazmaya başlayınca çekiliyor — yer klavyenin. */}
      <AnimatePresence initial={false}>
        {showChips && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="remote-scroll -mx-3 flex gap-2 overflow-x-auto px-3 pb-2.5">
              {REMOTE_PROMPTS.map((prompt) => (
                <button
                  key={prompt.title}
                  type="button"
                  onClick={() => void send(prompt.text)}
                  className="ease-out-quint border-border-subtle text-foreground-secondary shrink-0 rounded-full border bg-white/[0.04] px-3.5 py-2 text-[12.5px] whitespace-nowrap transition-all duration-300 active:scale-[0.97] active:bg-white/[0.07]"
                >
                  {prompt.title}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {paused && connected ? (
        <button
          type="button"
          onClick={() => void setPaused(false)}
          className="ease-out-quint border-primary/35 text-primary flex h-[52px] w-full items-center justify-center gap-2 rounded-[26px] border bg-[rgba(127,178,255,0.1)] text-[14px] font-medium transition-all duration-300 active:scale-[0.98]"
        >
          <LuPlay size={15} strokeWidth={1.9} />
          Chiron’u devam ettir
        </button>
      ) : (
        <div className="glass-panel flex items-end gap-2 p-1.5 pl-4">
          <textarea
            ref={textareaRef}
            value={draft}
            rows={1}
            onChange={(event) => {
              setDraft(event.target.value);
              if (error) setError('');
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void send(draft);
              }
            }}
            placeholder={placeholder}
            disabled={!canSend}
            enterKeyHint="send"
            className="text-foreground placeholder:text-foreground-disabled remote-scroll min-h-[40px] flex-1 resize-none bg-transparent py-2.5 text-[16px] leading-[22px] outline-none disabled:opacity-60"
            style={{ boxShadow: 'none' }}
          />
          <button
            type="button"
            onClick={() => void send(draft)}
            disabled={!draft.trim() || sending || !canSend}
            aria-label="Gönder"
            className="ease-out-quint bg-primary flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[#05070c] shadow-[0_0_20px_rgba(127,178,255,0.35)] transition-all duration-300 active:scale-[0.92] disabled:bg-white/[0.08] disabled:text-[var(--foreground-disabled)] disabled:shadow-none"
          >
            <LuArrowUp size={18} strokeWidth={2.2} />
          </button>
        </div>
      )}
    </div>
  );
});
