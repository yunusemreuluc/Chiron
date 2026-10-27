'use client';

import { useEffect, useLayoutEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useAIStateStore } from '@/stores/aiStateStore';
import { useConversationStore, type LogLine } from '@/stores/conversationStore';
import { useRemoteStore } from '@/stores/remoteStore';
import { REMOTE_PROMPTS } from './remotePrompts';
import { RemoteCore } from './RemoteCore';

// Telefondaki sohbet akışı. Masaüstündeki ConversationLog 320px'lik bir kartın
// içinde 12px metin; telefonda asıl ekran bu, okunurluk öncelikli: 15px metin,
// kullanıcı sağda, Chiron solda cam kartta.

// Araç adı → "şu an ne yapıyor". Yalnızca uzaktan anlamlı olanlar; listede
// olmayan araç genel "Çalışıyor" etiketine düşüyor (uydurma bir açıklama yok).
const TASK_LABELS: Record<string, string> = {
  analyze_screen: 'Ekrana bakıyor',
  intervene_screen: 'Ekranda işlem yapıyor',
  sys_info: 'Sistemi kontrol ediyor',
  get_context: 'Ne açık diye bakıyor',
  get_notifications: 'Bildirimleri okuyor',
  get_daily_activity: 'Günün kaydına bakıyor',
  shell_run: 'Komut çalıştırıyor',
  open_app: 'Uygulama açıyor',
  search_files: 'Dosya arıyor',
  summarize_file: 'Dosyayı okuyor',
  manage_files: 'Dosyaları düzenliyor',
  start_watch: 'İzleme kuruyor',
  stop_watch: 'İzlemeyi durduruyor',
  control_power: 'Güç komutu hazırlıyor',
  recognize_objects: 'Kameraya bakıyor',
  read_text: 'Kameradaki yazıyı okuyor',
  browser_control: 'Tarayıcıyı kullanıyor',
  get_weather: 'Hava durumuna bakıyor',
};

const PIN_THRESHOLD_PX = 96;
// Chiron'un balonu: sol üst köşe kısa — mesajın "nereden geldiğini" gösteren kuyruk.
const BUBBLE_RADIUS = '6px 20px 20px 20px';

function formatTime(at: number): string {
  return new Date(at * 1000).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
}

export function RemoteConversation({ onPrompt }: { onPrompt: (text: string) => void }) {
  const lines = useConversationStore((state) => state.lines);
  const connected = useConversationStore((state) => state.connected);
  const aiState = useAIStateStore((state) => state.aiState);
  const activeTask = useRemoteStore((state) => state.activeTask);

  const containerRef = useRef<HTMLDivElement>(null);
  // "Dipte miydi" bilgisi kaydırma olayında, içerik değişmeden ÖNCE yazılıyor
  // (bkz. Notes/Bilinen-Tuzaklar.md § Kaydırma konumunu içerik eklendikten
  // SONRA ölçme).
  const isPinned = useRef(true);
  const hasJumped = useRef(false);

  const busy = connected && (activeTask !== null || aiState === 'thinking' || aiState === 'speaking');

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    if (!hasJumped.current && lines.length > 0) {
      hasJumped.current = true;
      container.scrollTop = container.scrollHeight;
      return;
    }
    const sentByUser = lines[lines.length - 1]?.kind === 'user';
    if (sentByUser || isPinned.current) {
      container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
      isPinned.current = true;
    }
  }, [lines, busy]);

  // Klavye açılınca görünür alan daralıyor; dipteyken dipte kalınsın.
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const handleResize = () => {
      const container = containerRef.current;
      if (container && isPinned.current) container.scrollTop = container.scrollHeight;
    };
    viewport.addEventListener('resize', handleResize);
    return () => viewport.removeEventListener('resize', handleResize);
  }, []);

  // Geçmişte yalnızca sistem satırları varken ("Chiron hazır.") de karşılama
  // ekranı: gerçek kullanımda geçmiş hiç boş gelmiyor, `lines.length === 0`
  // koşulu hazır istemleri telefonda hiç göstermiyordu (görsel testte yakalandı).
  const hasConversation = lines.some((line) => line.kind === 'user' || line.kind === 'chiron');
  if (!hasConversation && !busy) {
    return <EmptyState connected={connected} onPrompt={onPrompt} />;
  }

  return (
    <div
      ref={containerRef}
      onScroll={() => {
        const c = containerRef.current;
        if (c) isPinned.current = c.scrollHeight - c.scrollTop - c.clientHeight < PIN_THRESHOLD_PX;
      }}
      className="remote-scroll relative z-10 flex flex-1 flex-col gap-3 overflow-y-auto px-4 pt-2 pb-4"
      style={{
        // Üst kenarda içerik başlığın altına sert bir çizgiyle girmesin.
        maskImage: 'linear-gradient(180deg, transparent 0, #000 18px)',
        WebkitMaskImage: 'linear-gradient(180deg, transparent 0, #000 18px)',
      }}
    >
      <AnimatePresence initial={false}>
        {lines.map((line) => (
          <MessageRow key={line.id} line={line} />
        ))}
        {busy && (
          <motion.div
            key="busy"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="flex justify-start"
          >
            <BusyIndicator label={activeTask ? (TASK_LABELS[activeTask.name] ?? 'Çalışıyor') : null} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function MessageRow({ line }: { line: LogLine }) {
  const enter = {
    initial: { opacity: 0, y: 10, filter: 'blur(4px)' },
    animate: { opacity: 1, y: 0, filter: 'blur(0px)' },
    transition: { duration: 0.36, ease: [0.22, 1, 0.36, 1] as const },
  };

  if (line.kind === 'system' || line.kind === 'error') {
    const error = line.kind === 'error';
    return (
      <motion.div {...enter} className="flex justify-center py-1">
        <span
          className={`max-w-[88%] rounded-full border px-3 py-1.5 text-center text-[11.5px] leading-snug ${
            error
              ? 'border-[#ff8f8f]/25 bg-[#ff8f8f]/[0.07] text-[#ff8f8f]'
              : 'border-border-subtle text-foreground-disabled bg-white/[0.025]'
          }`}
        >
          {line.text}
        </span>
      </motion.div>
    );
  }

  if (line.kind === 'user') {
    return (
      <motion.div {...enter} className="flex flex-col items-end gap-1 pl-12">
        <p className="text-foreground rounded-[20px] rounded-br-[6px] border border-white/[0.09] bg-white/[0.075] px-4 py-2.5 text-[15px] leading-relaxed break-words whitespace-pre-wrap shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
          {line.text}
        </p>
        <time className="numeric text-foreground-disabled pr-1 text-[10px]">{formatTime(line.at)}</time>
      </motion.div>
    );
  }

  return (
    <motion.div {...enter} className="flex flex-col items-start gap-1 pr-8">
      {/* Köşe yarıçapı satır içi: `.surface-card` katmansız CSS olduğu için
          Tailwind'in `rounded-*` sınıflarını eziyor (utilities bir @layer içinde). */}
      <div className="surface-card px-4 pt-3 pb-3.5" style={{ borderRadius: BUBBLE_RADIUS }}>
        {/* Renk satır içi: `.label-micro` da katmansız, `text-primary` onu ezemiyor. */}
        <span
          className="label-micro mb-2 flex items-center gap-1.5"
          style={{ color: 'rgba(127, 178, 255, 0.8)' }}
        >
          <span className="bg-primary h-1 w-1 rounded-full shadow-[0_0_6px_rgba(127,178,255,0.8)]" />
          {/* Kadın seste satır "Daphne:" ile geliyor (bkz. app_config.assistant_name). */}
          {line.raw.split(':')[0].trim() || 'Chiron'}
        </span>
        <p className="text-foreground text-[15px] leading-relaxed break-words whitespace-pre-wrap">
          {line.text}
        </p>
      </div>
      <time className="numeric text-foreground-disabled pl-1 text-[10px]">{formatTime(line.at)}</time>
    </motion.div>
  );
}

function BusyIndicator({ label }: { label: string | null }) {
  return (
    <div
      className="surface-card relative flex h-10 items-center gap-2.5 overflow-hidden px-4"
      style={{ borderRadius: BUBBLE_RADIUS }}
    >
      {/* Işık süpürmesi — "bir şey oluyor", dönen bir spinner'dan daha sakin. */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0 w-1/2 bg-[linear-gradient(90deg,transparent,rgba(127,178,255,0.12),transparent)]"
        style={{ animation: 'remote-shimmer 1.8s var(--ease-standard) infinite' }}
      />
      <span className="flex items-center gap-1">
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="bg-primary h-1.5 w-1.5 rounded-full"
            style={{ animation: `remote-dot 1.2s var(--ease-standard) ${index * 0.16}s infinite` }}
          />
        ))}
      </span>
      {label && <span className="text-foreground-secondary text-[12.5px]">{label}</span>}
    </div>
  );
}

function EmptyState({ connected, onPrompt }: { connected: boolean; onPrompt: (text: string) => void }) {
  const aiState = useAIStateStore((state) => state.aiState);
  return (
    <div className="remote-scroll relative z-10 flex flex-1 flex-col items-center overflow-y-auto px-5 pt-6 pb-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      >
        <RemoteCore state={aiState} size={148} online={connected} />
      </motion.div>
      <h2 className="text-foreground mt-6 text-center text-[21px] leading-tight font-semibold tracking-[-0.02em]">
        PC’n bir mesaj uzağında
      </h2>
      <p className="text-foreground-secondary mt-2 max-w-[290px] text-center text-[13.5px] leading-relaxed">
        Chiron ekrana bakar, durumu kontrol eder ve cevabı buraya yazar. PC hoparlörü sessiz kalır.
      </p>

      <div className="mt-7 grid w-full max-w-[420px] grid-cols-2 gap-2.5">
        {REMOTE_PROMPTS.map((prompt, index) => (
          <motion.button
            key={prompt.title}
            type="button"
            disabled={!connected}
            onClick={() => onPrompt(prompt.text)}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.15 + index * 0.06, ease: [0.22, 1, 0.36, 1] }}
            className="ease-out-quint border-border-subtle flex min-h-[76px] flex-col items-start justify-between gap-2 rounded-[18px] border bg-white/[0.035] p-3.5 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] transition-all duration-300 active:scale-[0.98] active:bg-white/[0.06] disabled:opacity-40"
          >
            <span className="text-foreground text-[13.5px] leading-tight font-medium">{prompt.title}</span>
            <span className="text-foreground-disabled text-[11px] leading-tight">{prompt.hint}</span>
          </motion.button>
        ))}
      </div>
    </div>
  );
}
