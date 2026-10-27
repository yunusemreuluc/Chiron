'use client';

import { useEffect, useState } from 'react';
import { fetchData } from '@/services/apiClient';

// Ambient bağlam — Chiron'un "kullanıcı şu an ne yapıyor" farkındalığı.
//
// Aynı veriyi `get_context` aracı modele veriyor (actions/ambient_context.py).
// Burada arayüze getirilmesinin sebebi DÜRÜSTLÜK: Chiron'un neyi bildiği
// görünür olmalı. Gizli bir araçta kalsaydı kullanıcı, asistanın bağlamı
// bildiğini ancak deneyerek keşfederdi.
//
// WebSocket DEĞİL, yoklama: bağlam olay değil DURUM. Her pencere değişiminde
// soket üzerinden olay yağdırmak (kullanıcı alt+tab yaparken saniyede birkaç
// kez) hem gereksiz hem de arayüzü titretirdi. 4 saniye, "canlı" hissettirmeye
// yetiyor ve okuma maliyeti 0.03 ms.
const REFRESH_MS = 4000;

export interface AmbientContext {
  /** Aktif pencerenin başlığı (program adı sonundan atılmış olarak). */
  windowTitle: string;
  /** İnsan tarafından okunan program adı — "Google Chrome", "Visual Studio Code". */
  app: string;
  /** Klavye/fareye en son dokunulalı geçen saniye. */
  idleSeconds: number;
  /** Kullanıcı masasında değil (varsayılan eşik 90 sn). */
  away: boolean;
}

export function useAmbientContext(): AmbientContext | null {
  const [context, setContext] = useState<AmbientContext | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      const data = await fetchData<Record<string, unknown>>('/api/system/context');
      if (cancelled) return;

      // Backend hiçbir şey okuyamadıysa (ya da hiç cevap vermediyse) arayüzde de
      // HİÇBİR ŞEY gösterme — bir önceki bağlamı ekranda bırakmak, Chiron'un artık
      // sahip olmadığı bir farkındalığı varmış gibi gösterirdi.
      const app = typeof data?.app === 'string' ? data.app : '';
      const windowTitle = typeof data?.window_title === 'string' ? data.window_title : '';
      if (!app && !windowTitle) {
        setContext(null);
        return;
      }

      setContext({
        windowTitle,
        app,
        idleSeconds: typeof data?.idle_seconds === 'number' ? data.idle_seconds : 0,
        away: Boolean(data?.away),
      });
    };

    void load();
    const timer = window.setInterval(() => void load(), REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return context;
}
