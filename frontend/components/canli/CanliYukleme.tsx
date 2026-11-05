'use client';

import { useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { LuRefreshCw, LuTriangleAlert, LuX, LuZap } from 'react-icons/lu';
import { fetchData } from '@/services/apiClient';
import { useLiveReloadStore, type CodeReload } from '@/stores/liveReloadStore';

// Canlı yükleme göstergesi (2026-11-04, kullanıcı isteği: "yeniden başlatmadan değişiklikler
// çalışma anında uygulansın"). İki iş:
//   1. Arayüz yeniden derlenince sayfayı yeniler — ama kullanıcının elindeki işi bozmadan: açık
//      bir pencere (role=dialog) ya da içi dolu bir yazı alanı varken bekler, "Şimdi yenile" sunar.
//      WebSocket olayı kaçarsa (derleme sırasında kopma) 30 sn'de bir /api/canli sürümüne bakar.
//   2. Backend'e uygulanan kod yamalarını kısa süre gösterir; yeniden başlatma isteyen değişiklik
//      kapatılana kadar kalır (Bilinen-Tuzaklar § Arayüzde dürüstlük — "uygulandı" yalanı yok).

const SAFE_CHECK_MS = 1000;
const VERSION_POLL_MS = 30_000;
const TOAST_MS = 4500;

function busyReason(): string | null {
  if (document.querySelector('[role="dialog"]')) return 'Açık pencere kapanınca yenilenecek';
  // Odaktan çıkmış taslak da korunur (Komuta kutusuna yazıp başka yere tıklamak).
  for (const area of Array.from(document.querySelectorAll('textarea'))) {
    if (area.value.trim()) return 'Yazdığın metin gönderilince yenilenecek';
  }
  const el = document.activeElement as HTMLInputElement | HTMLElement | null;
  if (el && el.tagName === 'INPUT' && (el as HTMLInputElement).value?.trim())
    return 'Yazdığın metin gönderilince yenilenecek';
  if (el?.isContentEditable && el.textContent?.trim()) return 'Yazdığın metin gönderilince yenilenecek';
  return null;
}

function useUiAutoReload() {
  const pending = useLiveReloadStore((s) => s.uiPending);
  const markUiUpdated = useLiveReloadStore((s) => s.markUiUpdated);
  const loadedVersion = useRef<number | null>(null);

  // Yedek yol: olay kaçtıysa sürüm karşılaştırması.
  useEffect(() => {
    let alive = true;
    const check = () =>
      fetchData<{ ui_version: number }>('/api/canli').then((data) => {
        if (!alive || !data) return;
        if (loadedVersion.current === null) loadedVersion.current = data.ui_version;
        else if (data.ui_version && data.ui_version !== loadedVersion.current) markUiUpdated();
      });
    void check();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') void check();
    }, VERSION_POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [markUiUpdated]);

  useEffect(() => {
    if (!pending) return;
    const id = setInterval(() => {
      if (!busyReason()) window.location.reload();
    }, SAFE_CHECK_MS);
    return () => clearInterval(id);
  }, [pending]);
}

function ReloadToast({ r }: { r: CodeReload }) {
  const dismiss = useLiveReloadStore((s) => s.dismiss);
  const sticky = r.restart.length > 0 || !!r.error;
  useEffect(() => {
    if (sticky) return;
    const id = setTimeout(() => dismiss(r.at, r.module), TOAST_MS);
    return () => clearTimeout(id);
  }, [sticky, r.at, r.module, dismiss]);

  const short = r.module.split('.').slice(-2).join('.');
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 6, scale: 0.98 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className={`canli-toast ${sticky ? 'is-warn' : 'is-ok'}`}
      role="status"
    >
      <span className="canli-toast__icon">{sticky ? <LuTriangleAlert size={13} /> : <LuZap size={13} />}</span>
      <div className="canli-toast__body">
        <strong>
          {r.error
            ? 'Kod uygulanamadı'
            : sticky
              ? 'Yeniden başlatma gerekebilir'
              : r.applied.length
                ? 'Kod canlı uygulandı'
                : 'Sorun giderildi'}
        </strong>
        <span className="canli-toast__mod">{short}</span>
        {r.applied.length > 0 && !r.error && (
          <span className="canli-toast__line">
            {r.applied.slice(0, 3).join(', ')}
            {r.applied.length > 3 ? ` +${r.applied.length - 3}` : ''}
          </span>
        )}
        {r.error && <span className="canli-toast__line is-err">{r.error}</span>}
        {r.restart.length > 0 && (
          <span className="canli-toast__line is-warn">Yeniden başlatma ister: {r.restart.slice(0, 2).join('; ')}</span>
        )}
      </div>
      <button type="button" className="canli-toast__close" onClick={() => dismiss(r.at, r.module)} aria-label="Kapat">
        <LuX size={12} />
      </button>
    </motion.div>
  );
}

export function CanliYukleme() {
  useUiAutoReload();
  const pending = useLiveReloadStore((s) => s.uiPending);
  const reloads = useLiveReloadStore((s) => s.reloads);

  return (
    <div className="canli-stack" aria-live="polite">
      <AnimatePresence initial={false}>
        {pending && <PendingUi key="ui" />}
        {reloads.map((r) => (
          <ReloadToast key={`${r.module}-${r.at}`} r={r} />
        ))}
      </AnimatePresence>
    </div>
  );
}

function PendingUi() {
  // Neden beklediğini her saniye yeniden okur (pencere kapanınca metin kendiliğinden kalkar).
  const reasonRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const id = setInterval(() => {
      if (reasonRef.current) reasonRef.current.textContent = busyReason() ?? 'Yenileniyor…';
    }, 500);
    return () => clearInterval(id);
  }, []);
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className="canli-toast is-info"
      role="status"
    >
      <span className="canli-toast__icon">
        <LuRefreshCw size={13} />
      </span>
      <div className="canli-toast__body">
        <strong>Yeni arayüz hazır</strong>
        <span ref={reasonRef} className="canli-toast__line">
          Yenileniyor…
        </span>
      </div>
      <button type="button" className="pano-btn is-primary" onClick={() => window.location.reload()}>
        Şimdi yenile
      </button>
    </motion.div>
  );
}
