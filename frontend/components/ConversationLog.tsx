'use client';

import { useEffect, useRef } from 'react';
import { useConversationStore, type LogKind } from '@/stores/conversationStore';

// Konuşma satırlarının görsel dili. Renk paletin tek vurgu kuralına uyuyor
// (bkz. app/globals.css): Chiron buz mavisi, kullanıcı nötr platin, sistem
// sönük, hata ise tek kırmızımsı istisna — hatanın fark edilmesi gerekiyor.
const KIND_STYLE: Record<LogKind, { label: string; className: string }> = {
  chiron: { label: 'Chiron', className: 'text-primary' }, // Daphne satırında etiket ham önekten
  user: { label: 'Siz', className: 'text-foreground' },
  system: { label: 'Sistem', className: 'text-foreground-secondary' },
  error: { label: 'Hata', className: 'text-[#ff8f8f]' },
};

// "Alttayım" sayılmak için alta olan azami mesafe. Bir satır payı: kullanıcı
// son mesajı görüyorsa yeni gelen de gösterilmeli.
const PIN_THRESHOLD_PX = 80;

export function ConversationLog() {
  const lines = useConversationStore((state) => state.lines);
  const bottomRef = useRef<HTMLDivElement>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  // Sohbet paneli her açıldığında bu bileşen yeniden mount ediliyor (dock'taki
  // AnimatePresence içinde), yani bu ref her açılışta sıfırlanıyor — tam da
  // istediğimiz şey.
  const hasJumpedToLatest = useRef(false);

  // Kullanıcı listenin DİBİNDE mi — kaydırma olayında, yani YENİ MESAJ
  // GELMEDEN ÖNCE ölçülüyor.
  //
  // BURASI ÖNCEDEN HATALIYDI (kullanıcı bildirdi, 2026-08-01): mesafe efektin
  // içinde, yani yeni satır DOM'a girdikten SONRA ölçülüyordu. O anda ölçülen
  // şey "kullanıcı alta ne kadar yakındı" değil, tam olarak YENİ EKLENEN
  // İÇERİĞİN YÜKSEKLİĞİ oluyordu. Kısa bir satır (~40px) eşiği geçtiği için
  // kaydırma çalışıyor, uzun bir cevap 80px'i aştığı için ÇALIŞMIYORDU —
  // panel `max-h-56` (224px) olduğundan bu çok kolay oluyor. Sonuç: uzun
  // mesajlar ekranın altında kalıyordu.
  const isPinnedToBottom = useRef(true);

  const handleScroll = () => {
    const container = containerRef.current;
    if (!container) return;
    isPinnedToBottom.current =
      container.scrollHeight - container.scrollTop - container.clientHeight < PIN_THRESHOLD_PX;
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // AÇILIŞTA: doğrudan en alta atla (kullanıcı isteği, 2026-07-31).
    // Buradaki hata şuydu: "yalnızca zaten alttaysan kaydır" kuralı ilk
    // açılışta ASLA sağlanmıyordu — panel yeni mount edildiğinde scrollTop
    // 0, yani alta olan mesafe tüm liste boyu kadar. Sonuç: sohbet her açılışta
    // en eski mesajdan başlıyordu.
    // `scrollTop` doğrudan atanıyor, scrollIntoView değil: animasyonsuz olmalı,
    // açılışta listenin kayarak inmesi gereksiz bir gösteri.
    if (!hasJumpedToLatest.current) {
      hasJumpedToLatest.current = true;
      container.scrollTop = container.scrollHeight;
      return;
    }

    // Kullanıcının KENDİ mesajı her zaman alta çeker — mesajı gönderen kişi
    // onu görmek ister, yukarıda bir şey okuyor olsa bile. Her sohbet
    // uygulamasının davranışı bu.
    const sentByUser = lines[lines.length - 1]?.kind === 'user';

    if (sentByUser || isPinnedToBottom.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
      isPinnedToBottom.current = true;
    }
  }, [lines]);

  if (lines.length === 0) {
    return (
      <p className="text-foreground-secondary text-xs leading-relaxed">
        Konuşma burada görünecek. Mikrofonun çalışmıyorsa aşağıya yazabilirsin — Chiron sana sesli
        cevap verir.
      </p>
    );
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex max-h-56 flex-col gap-2.5 overflow-y-auto pr-1"
    >
      {lines.map((line) => {
        const style = KIND_STYLE[line.kind];
        return (
          <div key={line.id} className="flex flex-col gap-0.5">
            <span className="label-micro">
              {line.kind === 'chiron' ? line.raw.split(':')[0].trim() || style.label : style.label}
            </span>
            <span className={`text-xs leading-relaxed ${style.className}`}>{line.text}</span>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
