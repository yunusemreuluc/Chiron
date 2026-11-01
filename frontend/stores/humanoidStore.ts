import { create } from 'zustand';

// İnsan görünümü (2026-11-01, kullanıcı isteği): çift parmak şıklatması ya da
// H tuşu, çekirdeği parçacıklardan oluşan bir büste çeviriyor
// (three/HumanoidBust.tsx). Tek kaynak backend'deki bayrak (core/web_ui.py
// `humanoid`, assistant_status anlık görüntüsünde geliyor); buradaki değer onun
// aynası. Backend yoksa (geliştirme) H tuşu yerel olarak çeviriyor.
interface HumanoidStore {
  active: boolean;
  setActive: (active: boolean) => void;
}

export const useHumanoidStore = create<HumanoidStore>((set) => ({
  active: false,
  setActive: (active) => set({ active }),
}));

/**
 * Dönüşümün anlık ilerlemesi 0..1 — HumanoidBust her karede yazıyor; çekirdek ve
 * tendriller sönmek için okuyor. Store'da değil düz nesnede: kare başına bir
 * zustand set() bütün aboneleri boşuna uyandırırdı.
 */
export const humanoidProgress = { value: 0 };

/** Çekirdeğin görünürlüğü: dönüşümün ilk üçte birinde sürüye çözülüp kayboluyor. */
export function corePresence(): number {
  const t = Math.min(1, Math.max(0, humanoidProgress.value / 0.35));
  return 1 - t * t * (3 - 2 * t);
}
