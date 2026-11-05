'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { LuImagePlus, LuSend, LuX } from 'react-icons/lu';
import { useConversationStore } from '@/stores/conversationStore';
import { fetchVoiceStatus, sendTextCommand } from '@/services/voiceApi';
import { IMAGE_TYPES, MAX_IMAGES, toAttachments, type Attachment } from '@/services/imageAttach';
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
  // Görsel ekleri (2026-11-04): düğme, Ctrl+V, sürükle-bırak. Gemini Live görseli aynı turda görür;
  // Chiron işi PC'ye verirse görseller Komuta'daki işe de eklenir (actions/pc_isi.py).
  const [images, setImages] = useState<Attachment[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const addFiles = async (files: Iterable<File>) => {
    const { items, error: problem } = await toAttachments(files, MAX_IMAGES - images.length);
    setError(problem);
    if (items.length) setImages((prev) => [...prev, ...items].slice(0, MAX_IMAGES));
  };

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
    if ((!text && !images.length) || sending) return;
    setSending(true);
    setError('');
    const result = await sendTextCommand(
      text,
      images.map((img) => img.dataUrl),
    );
    setSending(false);
    if (result.success) {
      setDraft('');
      setImages([]);
    } else {
      setError(result.message);
    }
  };

  return (
    <div className="flex flex-col gap-3.5">
      <ConversationLog />

      <div
        className={`flex flex-col gap-2 rounded-[22px] transition-shadow duration-200 ${
          dragging
            ? 'shadow-[0_0_0_2px_rgba(127,178,255,0.55),0_0_28px_-6px_rgba(127,178,255,0.5)]'
            : ''
        }`}
        onDragOver={(event) => {
          if (!canSend || ![...event.dataTransfer.types].includes('Files')) return;
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (canSend) void addFiles(event.dataTransfer.files);
        }}
      >
        {images.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1" aria-label="Eklenen görseller">
            <AnimatePresence initial={false}>
              {images.map((img) => (
                <motion.figure
                  key={img.key}
                  initial={{ opacity: 0, scale: 0.85 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.85 }}
                  transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                  className="group border-primary/25 relative m-0 h-14 w-14 overflow-hidden rounded-xl border bg-white/[0.04] shadow-[0_6px_18px_-10px_rgba(0,0,0,0.8)]"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element -- yerel data URL önizlemesi */}
                  <img
                    src={img.dataUrl}
                    alt={img.name}
                    className="block h-full w-full object-cover"
                  />
                  <button
                    type="button"
                    onClick={() => setImages((prev) => prev.filter((x) => x.key !== img.key))}
                    aria-label={`${img.name} kaldır`}
                    disabled={sending}
                    className="text-foreground absolute top-1 right-1 grid h-[18px] w-[18px] place-items-center rounded-full border border-white/20 bg-black/75 opacity-0 transition-opacity duration-200 group-hover:opacity-100 focus-visible:opacity-100"
                  >
                    <LuX size={10} strokeWidth={2.6} />
                  </button>
                </motion.figure>
              ))}
            </AnimatePresence>
          </div>
        )}
        <div className="flex items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept={IMAGE_TYPES.join(',')}
            multiple
            hidden
            onChange={(event) => {
              if (event.target.files) void addFiles(event.target.files);
              event.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={!canSend || sending || images.length >= MAX_IMAGES}
            aria-label="Görsel ekle"
            title="Görsel ekle (yapıştır ya da sürükle de olur)"
            className="border-border-subtle text-foreground-secondary hover:text-primary hover:border-primary/40 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border bg-white/[0.04] transition-all duration-200 disabled:opacity-40 disabled:hover:border-[var(--border-subtle)]"
          >
            <LuImagePlus size={14} strokeWidth={1.8} />
          </button>
          <input
            value={draft}
            onPaste={(event) => {
              const files = [...event.clipboardData.files].filter((f) =>
                f.type.startsWith('image/'),
              );
              if (!files.length) return;
              event.preventDefault();
              void addFiles(files);
            }}
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
            disabled={(!draft.trim() && !images.length) || sending || !canSend}
            aria-label="Gönder"
            className="border-border-subtle text-foreground-secondary hover:text-primary hover:border-primary/40 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border bg-white/[0.04] transition-all duration-200 disabled:opacity-40 disabled:hover:border-[var(--border-subtle)]"
          >
            <LuSend size={13} strokeWidth={1.8} />
          </button>
        </div>
      </div>

      {error && <p className="text-[11px] text-[#ff8f8f]">{error}</p>}

      {assistantRunning === false && (
        <p className="text-foreground-secondary text-[11px] leading-relaxed">
          Sesli asistan bu pencerede çalışmıyor. Masaüstündeki <strong>Chiron 3D</strong>{' '}
          kısayoluyla açarsan ses, araçlar ve sohbet burada olur.
        </p>
      )}
    </div>
  );
}
