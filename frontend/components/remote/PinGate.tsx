'use client';

import { useEffect, useRef, useState } from 'react';
import { motion, useAnimationControls } from 'framer-motion';
import { LuLockKeyhole } from 'react-icons/lu';
import { fetchRemoteSession, loginWithPin } from '@/services/remoteApi';
import { useRemoteStore } from '@/stores/remoteStore';
import { RemoteCore } from './RemoteCore';

// Telefonun kapısı. PIN'in kendisi hiçbir yerde saklanmıyor — başarılı girişte
// backend HttpOnly bir oturum çerezi veriyor (bkz. backend/core/remote_auth.py),
// sayfa JS'i onu göremiyor bile.
//
// Tek gizli input + görsel noktalar: altı ayrı kutu, mobil klavyelerde odak
// atlaması ve yapıştırma sorunları demek. Noktalara dokununca aynı input
// odaklanıyor; sayısal klavye `inputMode` ile açılıyor.

const MIN_DIGITS = 6;
const MAX_DIGITS = 12;

export function PinGate() {
  const setGate = useRemoteStore((state) => state.setGate);
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [pinSet, setPinSet] = useState(true);
  const [lockedSeconds, setLockedSeconds] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const shake = useAnimationControls();

  useEffect(() => {
    void fetchRemoteSession().then((session) => {
      if (!session) return;
      setPinSet(session.pinSet);
      setLockedSeconds(session.lockedSeconds);
    });
  }, []);

  // Kilit geri sayımı — mesaj sabit bir "60 sn" olarak donup kalmasın.
  useEffect(() => {
    if (lockedSeconds <= 0) return;
    const timer = window.setTimeout(() => setLockedSeconds((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [lockedSeconds]);

  const submit = async () => {
    if (pin.length < MIN_DIGITS || busy || lockedSeconds > 0) return;
    setBusy(true);
    setError('');
    const result = await loginWithPin(pin);
    setBusy(false);
    if (result.success) {
      setGate('open');
      return;
    }
    setPin('');
    setError(result.message);
    const match = /(\d+)\s*sn/.exec(result.message);
    if (match && result.message.includes('kilit')) setLockedSeconds(Number(match[1]));
    void shake.start({
      x: [0, -10, 9, -6, 4, 0],
      transition: { duration: 0.42, ease: [0.22, 1, 0.36, 1] },
    });
    inputRef.current?.focus();
  };

  const slots = Math.max(MIN_DIGITS, Math.min(MAX_DIGITS, pin.length));
  const locked = lockedSeconds > 0;

  return (
    <motion.section
      key="gate"
      initial={{ opacity: 0, y: 18, filter: 'blur(8px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      exit={{ opacity: 0, y: -12, filter: 'blur(8px)' }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="remote-safe-top remote-safe-bottom relative z-10 flex flex-1 flex-col items-center justify-center px-8"
    >
      <RemoteCore state="listening" size={128} />

      <div className="mt-7 flex flex-col items-center gap-2.5">
        <span className="label-micro">Uzaktan erişim</span>
        <h1 className="text-foreground text-[26px] leading-none font-semibold tracking-[-0.02em]">
          Chiron
        </h1>
        <p className="text-foreground-secondary max-w-[260px] text-center text-[13px] leading-relaxed">
          {pinSet
            ? 'PC’ne bağlanmak için PIN’ini gir.'
            : 'Henüz PIN belirlenmemiş. PC’de Ayarlar → Uzaktan erişim bölümünden belirle.'}
        </p>
      </div>

      <motion.button
        type="button"
        animate={shake}
        onClick={() => inputRef.current?.focus()}
        aria-label="PIN gir"
        className="relative mt-9 flex h-12 items-center justify-center gap-3.5 px-4"
      >
        {Array.from({ length: slots }, (_, index) => {
          const filled = index < pin.length;
          return (
            <motion.span
              key={index}
              layout
              animate={{ scale: filled ? 1 : 0.82 }}
              transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
              className={`h-3 w-3 rounded-full border transition-colors duration-200 ${
                filled ? 'border-primary bg-primary' : 'border-border-strong bg-white/[0.03]'
              }`}
              style={filled ? { boxShadow: 'var(--glow-primary-sm)' } : undefined}
            />
          );
        })}
        <input
          ref={inputRef}
          value={pin}
          onChange={(event) => {
            setError('');
            setPin(event.target.value.replace(/\D/g, '').slice(0, MAX_DIGITS));
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') void submit();
          }}
          type="password"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete="current-password"
          enterKeyHint="go"
          autoFocus
          disabled={!pinSet || locked}
          aria-label="PIN"
          className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
        />
      </motion.button>

      <p
        className={`mt-3 min-h-[18px] text-center text-[12px] transition-colors duration-200 ${
          error || locked ? 'text-[#ff8f8f]' : 'text-foreground-disabled'
        }`}
      >
        {locked ? `Çok fazla hatalı deneme · ${lockedSeconds} sn` : error}
      </p>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={pin.length < MIN_DIGITS || busy || locked || !pinSet}
        className="ease-out-quint border-primary/35 text-primary mt-6 flex h-12 w-full max-w-[280px] items-center justify-center gap-2 rounded-full border bg-[linear-gradient(180deg,rgba(127,178,255,0.18),rgba(127,178,255,0.06))] text-[14px] font-medium shadow-[inset_0_1px_0_rgba(255,255,255,0.1),0_0_28px_rgba(127,178,255,0.16)] transition-all duration-300 active:scale-[0.98] disabled:border-[var(--border-subtle)] disabled:bg-white/[0.03] disabled:text-[var(--foreground-disabled)] disabled:shadow-none"
      >
        <LuLockKeyhole size={16} strokeWidth={1.8} />
        {busy ? 'Doğrulanıyor' : 'Kilidi aç'}
      </button>
    </motion.section>
  );
}
