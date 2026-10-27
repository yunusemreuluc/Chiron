'use client';

import { useEffect, useState } from 'react';
import { fetchMemory, type MemorySnapshot } from '@/services/modulesApi';

// Hafıza modülü — kullanıcı isteğiyle (2026-07-30) backend'e bağlandı. Önceden
// "Henüz görüntülenecek bir hafıza girdisi yok." diyen dürüst ama boş bir
// metindi; oysa memory/memory.json gerçek veri tutuyordu ve arayüze hiç
// akmıyordu.
//
// SALT OKUNUR (bkz. backend/api/memory.py): silme işlemi Chiron'a söylenerek
// yapılıyor, çünkü `delete_memory` aracı iki adımlı onay istiyor. Panele bir
// çöp kutusu koymak o onayı atlatan ikinci bir yol açardı.

export function MemoryPanelContent() {
  const [snapshot, setSnapshot] = useState<MemorySnapshot | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchMemory().then((data) => {
      if (cancelled) return;
      if (data) setSnapshot(data);
      else setFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) {
    return (
      <p className="text-foreground-secondary text-xs">Hafıza okunamadı — Chiron çalışıyor mu?</p>
    );
  }
  if (!snapshot) {
    return <p className="text-foreground-disabled text-xs">Hafıza okunuyor...</p>;
  }
  if (snapshot.total === 0) {
    return (
      <p className="text-foreground-secondary text-xs leading-relaxed">
        Hafıza boş. Chiron sana dair bir şey öğrendiğinde (ya da ona &ldquo;bunu hatırla&rdquo;
        dediğinde) burada birikmeye başlar.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-2">
        <span className="label-micro">Toplam</span>
        <span className="numeric text-foreground-secondary text-[11px]">
          {snapshot.total} kayıt
        </span>
      </div>

      {snapshot.categories.map((category) => (
        <div key={category.id} className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-2">
            <span className="label-micro">{category.label}</span>
            <span className="numeric text-foreground-disabled text-[10px]">{category.count}</span>
          </div>

          <ul className="flex flex-col gap-1.5">
            {category.entries.map((entry) => (
              <li
                key={entry.key}
                className="border-border-subtle rounded-[10px] border bg-white/[0.03] px-2.5 py-2"
              >
                <span className="text-foreground-secondary block text-[10px] tracking-[0.04em] uppercase">
                  {entry.label}
                </span>
                {/* break-words: hafızada uzun tek kelimeler (URL, telefon) olabiliyor
                    ve kartı taşırıyorlardı. */}
                <span className="text-foreground mt-0.5 block text-[11px] leading-snug break-words">
                  {entry.text}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
