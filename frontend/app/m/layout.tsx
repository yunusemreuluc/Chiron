import type { Metadata, Viewport } from 'next';

// Telefon arayüzü (uzaktan erişim, 2026-09-15). Ana ekrana eklenince tarayıcı
// çerçevesi olmadan, kendi uygulaması gibi açılıyor — manifest ve Apple
// meta'ları bunun için. Bkz. Notes/Uzaktan-Erisim.md.
export const metadata: Metadata = {
  title: 'Chiron',
  description: 'Chiron — PC’ne dışarıdan ulaş',
  manifest: '/m/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    title: 'Chiron',
    statusBarStyle: 'black-translucent',
  },
  icons: {
    icon: [{ url: '/m/icons/chiron-192.png', sizes: '192x192', type: 'image/png' }],
    apple: [{ url: '/m/icons/apple-touch-icon.png', sizes: '180x180' }],
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  // Çentik/ada altına kadar çizilsin; boşluklar CSS'te env(safe-area-inset-*).
  viewportFit: 'cover',
  themeColor: '#05070c',
  // Klavye açılınca yerleşim daralsın, yazı kutusu klavyenin altında kalmasın.
  interactiveWidget: 'resizes-content',
};

export default function RemoteLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
