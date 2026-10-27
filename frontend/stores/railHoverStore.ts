import { create } from 'zustand';

// Sol raydaki hangi düğmenin üzerinde durulduğu.
//
// NEDEN PAYLAŞILAN DURUM: rayın hover etiketi ile sol üstteki CHIRON imzası
// AYNI yerde çiziliyor ve üst üste biniyordu (ölçüldü: ilk düğmede 19×9 px,
// imzaya ambient bağlam satırı eklenince 37×30 px). İkisi de kendi bileşeninde
// yaşadığı için hiçbiri diğerinin varlığını bilmiyordu.
//
// Denenmeyen çözümler ve neden: imzayı sağa itmek "Otomasyon" gibi daha uzun
// etiketlerde yine çakışıyor; aşağı itmek ikinci düğmenin etiketine denk
// geliyor; rayın üstüne boşluk koymak ise rayın başında koca bir delik bırakıyor.
//
// Seçilen yol bir KAÇAMAK DEĞİL, kasıtlı bir etkileşim: raya yaklaşınca imza
// geri çekiliyor, etiket öne çıkıyor. Aynı anda iki şeyin dikkat istemesi
// yerine, o an bakılan şey kazanıyor.
interface RailHoverStore {
  /** Üzerinde durulan düğmenin etiketi; hiçbiri değilse null. */
  hoveredLabel: string | null;
  setHoveredLabel: (label: string | null) => void;
}

export const useRailHoverStore = create<RailHoverStore>((set) => ({
  hoveredLabel: null,
  setHoveredLabel: (hoveredLabel) => set({ hoveredLabel }),
}));
