'use client';

import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  LuCheck,
  LuMessageSquare,
  LuMic,
  LuMicOff,
  LuSmartphone,
  LuTrash2,
  LuX,
} from 'react-icons/lu';
import { useConversationStore } from '@/stores/conversationStore';
import { resetSession, setMuted } from '@/services/voiceApi';
import { setRemoteModeLocal } from '@/services/remoteApi';
import { playSfx } from '@/services/sfxPlayer';
import { GlassPanel } from './GlassPanel';
import { VoicePanelContent } from './VoicePanelContent';
import { VoiceWaveform } from './VoiceWaveform';

// Silme onayının açık kalma süresi. Kullanıcı ikinci kez basmazsa düğme
// kendiliğinden normale dönüyor — ekranda "silmeye hazır" bir düğme asılı
// kalmamalı.
const CONFIRM_TIMEOUT_MS = 3200;

// Kullanıcı isteğiyle (2026-07-29): mikrofon düğmesi sol panelden kaldırıldı,
// sohbet sağ alt köşede kendi dock'una taşındı. Gerekçe yerleşimsel: sol panel
// modül gezinmesi için; asistanla KONUŞMAK sürekli erişilebilir olmalı ve
// gezinmeye bağlı olmamalı — bu yüzden sabit, her zaman görünen bir dock.
//
// Dock kapalıyken sadece iki yuvarlak düğme (mikrofon + mesaj); mesaja basınca
// üstünde sohbet kartı açılıyor. 3D sahne mümkün olduğunca açık kalsın diye
// kart yalnızca istendiğinde var oluyor.
export function AssistantDock() {
  const [isChatOpen, setIsChatOpen] = useState(false);
  const muted = useConversationStore((state) => state.muted);
  const remote = useConversationStore((state) => state.remote);
  const lines = useConversationStore((state) => state.lines);
  const connected = useConversationStore((state) => state.connected);
  const clearLines = useConversationStore((state) => state.clear);

  // Kullanıcı isteğiyle (2026-07-30): dock'taki "Duraklat" yerine "Sohbeti sil".
  // İKİ ADIMLI: ilk tıklama düğmeyi silmeye hazırlıyor, ikincisi siliyor.
  // Tek tıklamayla silinen bir geçmişin geri dönüşü yok — mikrofonun yanındaki
  // 40px'lik bir hedefte bu kabul edilemez bir risk.
  const [isArmed, setIsArmed] = useState(false);
  const armTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(armTimer.current), []);

  const handleClear = () => {
    if (!isArmed) {
      setIsArmed(true);
      window.clearTimeout(armTimer.current);
      armTimer.current = window.setTimeout(() => setIsArmed(false), CONFIRM_TIMEOUT_MS);
      return;
    }
    window.clearTimeout(armTimer.current);
    setIsArmed(false);
    // İki taraf birlikte temizleniyor: arayüzdeki satırlar VE Gemini Live'ın
    // sohbet bağlamı (backend/api/voice.py → /reset). Yalnızca ekranı silmek
    // aldatıcı olurdu — Chiron konuşulanları hatırlamaya devam ederdi.
    clearLines();
    void resetSession();
    playSfx('hud');
  };

  const lastLine = lines[lines.length - 1];

  return (
    <div className="pointer-events-none absolute right-7 bottom-7 z-30 flex flex-col items-end gap-3">
      <AnimatePresence>
        {isChatOpen && (
          <motion.div
            initial={{ opacity: 0, y: 16, filter: 'blur(6px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, y: 16, filter: 'blur(6px)' }}
            transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
            className="pointer-events-auto w-[320px]"
          >
            <GlassPanel variant="card" className="flex flex-col p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <span className="border-border-subtle flex h-7 w-7 items-center justify-center rounded-[9px] border bg-white/[0.04]">
                    <LuMessageSquare size={13} strokeWidth={1.7} className="text-primary" />
                  </span>
                  <span className="flex flex-col gap-1">
                    <span className="label-micro">Sohbet</span>
                    <span className="text-foreground text-[13px] leading-none font-medium">
                      Chiron
                    </span>
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setIsChatOpen(false)}
                  aria-label="Sohbeti kapat"
                  className="text-foreground-disabled hover:text-foreground -m-1 rounded-full p-1.5 transition-colors duration-200 hover:bg-white/[0.06]"
                >
                  <LuX size={13} strokeWidth={1.8} />
                </button>
              </div>

              <hr className="hairline my-4" />

              <VoicePanelContent />
            </GlassPanel>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Dock'un kendisi: her zaman görünen, sabit yükseklikte cam çubuk. */}
      <GlassPanel className="pointer-events-auto flex items-center gap-1.5 px-2.5 py-2">
        {/* Uzak mod (2026-09-15): telefondan yazılınca PC hoparlörü ve mikrofonu
            kapanıyor. Eve dönen kullanıcı Chiron'un neden sustuğunu burada görmeli
            — gizli bir durum "Chiron bozuldu" gibi okunurdu. Tek dokunuşla çıkış;
            PC'den yazmak da uzak modu kendiliğinden kapatıyor. */}
        {remote && (
          <>
            <DockButton
              label="Uzak mod — PC sessiz. Kapat"
              icon={LuSmartphone}
              active
              warning={false}
              onClick={() => void setRemoteModeLocal(false)}
            />
            <span className="bg-border-subtle mx-0.5 h-5 w-px" />
          </>
        )}
        <DockButton
          label={muted ? 'Mikrofonu aç' : 'Mikrofonu kapat'}
          icon={muted ? LuMicOff : LuMic}
          active={!muted}
          warning={muted}
          onClick={() => void setMuted(!muted)}
        />
        {/* Dalga formu mikrofon düğmesinin hemen yanında: "duyuyor mu" sorusunun
            cevabı, o soruyu soran düğmenin dibinde olmalı. */}
        <VoiceWaveform muted={muted} />
        <DockButton
          label={isArmed ? 'Emin misin?' : 'Sohbeti sil'}
          icon={isArmed ? LuCheck : LuTrash2}
          active={false}
          warning={isArmed}
          // Hazır durumdayken etiket fareyi beklemeden görünüyor: kırmızı bir
          // onay ikonu tek başına "ne olacağını" söylemiyor.
          showLabel={isArmed}
          disabled={lines.length === 0}
          onClick={handleClear}
        />

        <span className="bg-border-subtle mx-0.5 h-5 w-px" />

        <button
          type="button"
          onClick={() => setIsChatOpen((open) => !open)}
          aria-label="Sohbet"
          className={`ease-out-quint relative flex h-10 items-center gap-2 rounded-[14px] px-3 transition-all duration-200 ${
            isChatOpen
              ? 'text-primary bg-white/[0.07] shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_0_18px_rgba(127,178,255,0.18)]'
              : 'text-foreground-secondary hover:text-foreground hover:bg-white/[0.05]'
          }`}
        >
          <LuMessageSquare size={17} strokeWidth={1.7} />
          <span className="max-w-[132px] truncate text-[11px] font-medium">
            {/* Kapalıyken son satırı gösteriyor: dock aynı zamanda "yeni bir şey
                oldu mu" göstergesi olsun, kullanıcı açmadan da haberdar olsun. */}
            {isChatOpen
              ? 'Sohbet'
              : lastLine
                ? lastLine.text
                : connected
                  ? 'Chiron hazır'
                  : 'Bağlanıyor'}
          </span>
        </button>
      </GlassPanel>
    </div>
  );
}

function DockButton({
  label,
  icon: Icon,
  active,
  warning,
  showLabel = false,
  disabled = false,
  onClick,
}: {
  label: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  active: boolean;
  warning: boolean;
  /** Etiketi fareyi beklemeden gösterir (onay gibi kendini anlatması gereken durumlar). */
  showLabel?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={`ease-out-quint relative flex h-10 w-10 items-center justify-center rounded-[14px] transition-all duration-200 disabled:pointer-events-none disabled:opacity-35 ${
        warning
          ? 'bg-[#ff8f8f]/10 text-[#ff8f8f]'
          : active
            ? 'text-primary hover:bg-white/[0.05]'
            : 'text-foreground-secondary hover:text-foreground hover:bg-white/[0.05]'
      }`}
    >
      <Icon size={17} strokeWidth={1.7} />
      <span
        className={`node-label-card text-foreground pointer-events-none absolute bottom-full left-1/2 z-30 mb-2.5 -translate-x-1/2 px-2.5 py-1.5 text-[11px] font-medium whitespace-nowrap transition-all duration-200 ${
          isHovered || showLabel ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
        }`}
      >
        {label}
      </span>
    </button>
  );
}
