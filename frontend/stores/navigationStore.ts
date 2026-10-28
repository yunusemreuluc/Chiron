import { create } from 'zustand';

// Notes/Tasarim-Kurallari.md § Durum yönetimi — ayrı store'lar, tek yerde toplamıyoruz.
// Sidebar (ikon rayı) ve LeftPanel hangi modülün seçili olduğunu burada paylaşıyor.
//
// 'voice' kullanıcı isteğiyle (2026-07-29) bu listeden ÇIKARILDI: sohbet artık
// sağ alt köşedeki kendi dock'unda (bkz. components/AssistantDock.tsx).
// 'settings' ise Tkinter penceresinden taşınan ayarlar paneli.
// 2026-10-29: Hafıza, Otomasyon, Tarayıcı modülleri kullanıcı isteğiyle kaldırıldı.
export type ModuleId = 'agents' | 'settings';

interface NavigationState {
  activeModule: ModuleId | null;
  toggleModule: (id: ModuleId) => void;
}

export const useNavigationStore = create<NavigationState>((set) => ({
  activeModule: null,
  toggleModule: (id) => set((state) => ({ activeModule: state.activeModule === id ? null : id })),
}));
