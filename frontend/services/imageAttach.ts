// Sohbete görsel eki — Komuta ve ana ekrandaki Chiron sohbeti ortak kullanır (2026-11-04).
// Sınırlar backend/core/sohbet.py ile aynı (MAX_IMAGES, MAX_IMAGE_BYTES, _image_ext).

export interface Attachment {
  key: string;
  name: string;
  dataUrl: string;
}

export const MAX_IMAGES = 4;
export const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
export const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];

export function readDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

/** Dosyaları süzer ve okur. Döner: eklenebilenler + (varsa) kullanıcıya gösterilecek hata. */
export async function toAttachments(files: Iterable<File>, room: number): Promise<{ items: Attachment[]; error: string }> {
  const picked = [...files].filter((f) => f.type.startsWith('image/'));
  let error = picked.length > room ? `Bir mesaja en fazla ${MAX_IMAGES} görsel eklenir.` : '';
  const items: Attachment[] = [];
  for (const f of picked.slice(0, Math.max(0, room))) {
    if (!IMAGE_TYPES.includes(f.type)) {
      error = 'Yalnız PNG, JPEG, GIF ya da WebP.';
      continue;
    }
    if (f.size > MAX_IMAGE_BYTES) {
      error = `${f.name || 'Görsel'} 8 MB'tan büyük.`;
      continue;
    }
    items.push({ key: `${Date.now()}-${Math.random()}`, name: f.name || 'yapıştırılan görsel', dataUrl: await readDataUrl(f) });
  }
  return { items, error };
}
