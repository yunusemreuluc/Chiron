import { create } from 'zustand';

// Notes/Tasarim-Kurallari.md § Enerji çekirdeği — tüm 3D sahne (EnergyCore,
// EnergyTendrils) ve 2D HUD bu tek durumu okuyor.
// ileride backend'in `energy_state` WebSocket olayı bu store'u besleyecek —
// şimdilik frontend/hooks/useDemoAIStateCycle.ts geçici bir demo döngüsüyle besliyor.
//
// Beş tepki (2026-07-31, Notes/Arayuz.md § Beş tepki): kural Ses / Düşünme / Görü /
// Otomasyon / Hafıza istiyordu, üçü çalışıyordu. `automation` ve `memory`
// buradan eklendi; hangi aracın hangisini tetiklediği core/web_ui.py
// `state_for_tool` içinde.
export type AIState =
  'idle' | 'listening' | 'thinking' | 'speaking' | 'vision' | 'automation' | 'memory';

// BrandBadge.tsx (canlı durum metni) ve NodeFocusCard.tsx (odak kartı alt başlığı)
// aynı etiketleri paylaşıyor — tek yerde tutuluyor.
export const AI_STATE_LABELS: Record<AIState, string> = {
  idle: 'Boşta',
  listening: 'Dinliyor',
  thinking: 'Düşünüyor',
  speaking: 'Konuşuyor',
  vision: 'Görüyor',
  // "Otomasyon" değil "Uyguluyor": etiket Chiron'un NE YAPTIĞINI söylüyor,
  // özelliğin adını değil — diğer dördü de öyle.
  automation: 'Uyguluyor',
  memory: 'Hatırlıyor',
};

interface AIStateStore {
  aiState: AIState;
  setAIState: (state: AIState) => void;
}

export const useAIStateStore = create<AIStateStore>((set) => ({
  aiState: 'idle',
  setAIState: (aiState) => set({ aiState }),
}));

// "AI düşünürken: Orbit yavaşlasın."
export function getOrbitSpeedMultiplier(state: AIState): number {
  if (state === 'thinking') return 0.4;
  if (state === 'speaking') return 1.25;
  // Otomasyon sistemin en hareketli hâli: Chiron dışarıya iş yaptırıyor, sahne
  // de onunla birlikte hızlanıyor. Hafıza tam tersi — içe dönük, neredeyse
  // düşünmek kadar yavaş ama durmuyor.
  if (state === 'automation') return 1.5;
  if (state === 'memory') return 0.5;
  return 1;
}
