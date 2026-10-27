import type { NextConfig } from 'next';

// Kullanıcı isteğiyle (2026-07-29) — Chiron artık tarayıcıda değil, kendi masaüstü
// penceresinde açılıyor (bkz. kökteki desktop.py). Bunun için arayüz STATİK olarak
// dışa aktarılıyor: `next build` → frontend/out/ altında saf HTML/CSS/JS.
//
// Neden statik export: masaüstü sürümünde çalışma zamanında Node sunucusu olmasın.
// Uygulama açılışı tek bir Python süreci (FastAPI + pencere) — arayüzü backend
// doğrudan dosya olarak sunuyor (bkz. backend/main.py). Bu mümkün, çünkü uygulama
// tek sayfa ve tamamen istemci taraflı ('use client'); sunucu tarafı veri çekme,
// route handler veya middleware kullanmıyor.
//
// `npm run dev` bundan etkilenmez — geliştirme akışı aynı.
//
// `trailingSlash` (2026-09-15, telefon arayüzü): ikinci sayfa `/m` eklendi.
// Onsuz export `out/m.html` üretiyor ve FastAPI'nin StaticFiles'ı `/m/`'i
// `m/index.html` olarak arıyor — bulamayıp 404 dönüyor. Bununla `out/m/index.html`.
const nextConfig: NextConfig = {
  output: 'export',
  trailingSlash: true,
};

export default nextConfig;
