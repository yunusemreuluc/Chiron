// Ofis yerleşimi — masaların zemindeki konumları (x, z).
//
// Şef (Claude) ortada, yükseltilmiş platformda; diğerleri onun çevresinde bir
// halka. İzometrik kamera (+x,+y,+z) köşesinden baktığı için halkanın "önü"
// +x+z yönü — en sık iş alan masalar (Sol, Alt ajanlar) oraya, kameraya yakın.
const RING_RADIUS = 5.4;

const RING_ORDER = ['sol', 'subagents', 'astra', 'opencode', 'bunny', 'gemini'];

export const CHIEF_ID = 'claude';

export function deskPosition(id: string): [number, number, number] {
  if (id === CHIEF_ID) return [0, 0, 0];
  const index = RING_ORDER.indexOf(id);
  const slot = index === -1 ? RING_ORDER.length : index;
  // 45° = kameraya bakan yön; masalar oradan iki yana açılıyor.
  const angle = Math.PI / 4 + ((slot % 2 === 0 ? 1 : -1) * Math.ceil(slot / 2) * Math.PI) / 3;
  return [Math.cos(angle) * RING_RADIUS, 0, Math.sin(angle) * RING_RADIUS];
}

export const STATUS_COLOR = {
  calisiyor: null, // masanın kendi rengi
  onay_bekliyor: '#ffb020',
  hata: '#ff5d6c',
  bitti: '#7ee0b5',
} as const;
