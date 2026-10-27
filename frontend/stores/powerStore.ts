import { create } from 'zustand';

// CHIRON — uyku/uyanıklık.
//
// Kullanıcı isteğiyle (2026-07-30): sahnenin ortasındaki çekirdek tıklanabilir
// ve tıklayınca Chiron "kapanıyor" — ortam karanlığa bürünüyor, çekirdek sönük
// bir nefese düşüyor (bkz. three/EnergyCore.tsx, components/SleepVeil.tsx).
//
// UYGULAMA KAPANMIYOR, uyuyor. Bu bilinçli bir karar: çekirdek ekrandaki en
// büyük tıklama hedefi, yanlışlıkla tıklanması kaçınılmaz. Gerçekten kapatsaydı
// bir kazanın bedeli "oturumu kaybetmek" olurdu; uyku modunda bedel "bir kez
// daha tıklamak". Pencereyi gerçekten gizlemek isteyen sağ üstteki tepsi
// düğmesini kullanıyor (components/TrayControl.tsx), kapatmak isteyen pencereyi
// kapatıyor — ikisi de niyeti açıkça belli olan, ayrı hedefler.
export type PowerState = 'awake' | 'asleep';

interface PowerStore {
  powerState: PowerState;
  toggle: () => void;
  wake: () => void;
}

/**
 * Uykuda sahnenin çevre öğelerine (yörünge düğümleri, bağlantı ağı)
 * uygulanan çarpan.
 *
 * SIFIR DEĞİL: ağ tamamen kaybolursa uyuyan sistem "kapanmış" görünüyor. Çok
 * soluk bir iskeletin kalması, yapının hâlâ orada durduğunu — sadece
 * dinlendiğini — söylüyor. Değer perdenin (SleepVeil) karartmasıyla BİRLİKTE
 * çalışıyor, o yüzden tek başına bakıldığında olduğundan yüksek görünür.
 */
export const SLEEP_DIM = 0.14;

export const usePowerStore = create<PowerStore>((set) => ({
  powerState: 'awake',
  toggle: () => set((state) => ({ powerState: state.powerState === 'awake' ? 'asleep' : 'awake' })),
  wake: () => set({ powerState: 'awake' }),
}));
