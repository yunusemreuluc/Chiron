import { create } from 'zustand';
import { fetchOrbitExtras, type OrbitExtras } from '@/services/gozetimApi';

// Yörünge ekleri (2026-11-04) — bağlam halkası, arka plan işleri, dev sunucular, kaçak süreç, bekleyen onay.
// backend/core/gozetim.py orbit_view; sahne açıkken 5 sn'de bir. İki sahne (ana + Gözetim) aynı store'u okur,
// yoklayıcı tek: abone sayısı sıfıra inince durur.

const POLL_MS = 5000;

interface OrbitStore {
  extras: OrbitExtras | null;
  set: (extras: OrbitExtras) => void;
}

export const useOrbitStore = create<OrbitStore>((set) => ({
  extras: null,
  set: (extras) => set({ extras }),
}));

let users = 0;
let timer: ReturnType<typeof setInterval> | null = null;

function tick() {
  if (typeof document !== 'undefined' && document.hidden) return;
  void fetchOrbitExtras().then((e) => e && useOrbitStore.getState().set(e));
}

/** Sahne bileşenleri mount olunca çağırır; dönen fonksiyon bırakır. */
export function holdOrbitPoll(): () => void {
  users += 1;
  if (!timer) {
    tick();
    timer = setInterval(tick, POLL_MS);
  }
  return () => {
    users -= 1;
    if (users <= 0 && timer) {
      clearInterval(timer);
      timer = null;
      users = 0;
    }
  };
}
