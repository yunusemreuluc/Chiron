// Backend'e giden HER isteğin tek geçtiği yer.
//
// Beş servis dosyası (voice, vision, settings, modules, sfx) aynı üç şeyi
// ayrı ayrı yazıyordu: taban adres, {success, message, data} zarfı ve
// backend kapalıyken arayüzü çökertmeyen try/catch. Üçü de burada.
//
// İki çalışma biçimi var ve taban adres buna göre değişiyor:
//   • Masaüstü uygulaması — arayüz backend'in kendisinden (8000) sunuluyor,
//     istekler aynı kaynağa gider, taban boş string.
//   • `npm run dev` — arayüz 3000'de, backend 8000'de; mutlak adres gerekir
//     (CORS'ta 3000 zaten izinli, bkz. backend/core/config.py).
const DEV_BACKEND_ORIGIN = 'http://localhost:8000';

export function apiBase(): string {
  if (typeof window === 'undefined') return DEV_BACKEND_ORIGIN;
  return window.location.port === '3000' ? DEV_BACKEND_ORIGIN : '';
}

// Adres sayfanın kendi kaynağından türetiliyor (2026-09-15): önceden
// `ws://localhost:8000/ws` sabitti ve arayüz başka bir adresten (telefon,
// Tailscale HTTPS) açıldığında soket hiç bağlanamıyordu. `npm run dev`'de arayüz
// 3000'de, backend 8000'de — orada mutlak adres şart (bkz. services/apiClient.ts).
export function websocketUrl(): string {
  if (typeof window === 'undefined' || window.location.port === '3000') {
    return 'ws://localhost:8000/ws';
  }
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}/ws`;
}

/** Backend'in her uçta döndürdüğü zarf (bkz. backend/api/*.py). */
export interface ApiResult<T = Record<string, unknown>> {
  success: boolean;
  message: string;
  data?: T;
}

export async function request<T = Record<string, unknown>>(
  path: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${apiBase()}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    });
    return (await response.json()) as ApiResult<T>;
  } catch {
    // Backend kapalı — arayüz çökmemeli, kullanıcıya dürüst bir mesaj dönmeli.
    return { success: false, message: 'Chiron çalışmıyor.' };
  }
}

export const post = <T = Record<string, unknown>>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) });

/**
 * Yalnızca `data` ile ilgilenen okuma uçları için. Başarısızlıkta `null` —
 * çağıran taraf "veri yok" ile "hata" arasında ayrım yapmıyorsa ikisi de
 * aynı şeye çıkar: gösterilecek bir şey yok, uydurma da yok.
 */
export async function fetchData<T>(path: string): Promise<T | null> {
  const result = await request<T>(path);
  return result.success && result.data ? result.data : null;
}
