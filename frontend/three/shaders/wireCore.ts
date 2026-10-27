// CHIRON Energy Core — TEL KAFES sürümü (2026-08-06).
//
// Köşe (vertex) shader'ı dolu küredekiyle AYNI kalıyor (ENERGY_CORE_VERTEX_SHADER):
// simplex gürültüsü kafesin kendisini dalgalandırıyor, yani çizgiler donmuş bir
// telden değil akan bir alandan geçiyor gibi kıvranıyor. Değişen tek şey ışık
// modeli — ve o tamamen değişmek zorundaydı:
//
// Dolu kürede ışık YÜZEYDEN geliyordu, fresnel kenarı cismin SINIRINI çiziyordu.
// Tel kafeste yüzey diye bir şey yok; ışık ÇİZGİDEN geliyor. Aynı taban çarpanla
// (0.2) çizildiğinde kafes zeminde kayboluyordu.
export const WIRE_CORE_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColorA;
  uniform vec3 uColorB;
  uniform vec3 uRimColor;
  uniform float uIntensity;
  uniform float uOpacity;
  varying vec3 vNormal;
  varying vec3 vViewPosition;
  varying float vNoise;

  void main() {
    vec3 viewDir = normalize(vViewPosition);
    float ndv = dot(normalize(vNormal), viewDir);

    // Silüet: kafesin kenara doğru kıvrılan çizgileri. Dolu küredeki fresnel ile
    // aynı hesap, farklı anlam — burada "cismin sınırı" değil, çizginin bakışa
    // göre EĞİMİ. Kenara yakın çizgiler parlıyor, tam karşıya bakanlar sönük
    // kalıyor; hologram hissini taşıyan şey bu fark.
    float silhouette = pow(1.0 - abs(ndv), 2.2);

    // Arkada kalan yarı. Kafes DoubleSide çiziliyor (yoksa arka çizgiler kesilir
    // ve cisim bir kafes değil bir kase gibi görünür). Ama arkadakiler öndekiyle
    // aynı parlaklıkta çizilseydi derinlik ölür, orb bir tel yumağına dönerdi —
    // bilerek soluklar.
    float backness = smoothstep(0.0, -0.55, ndv);

    vec3 base = mix(uColorA, uColorB, smoothstep(-1.0, 1.0, vNoise));

    // Kenar tonu payı 0.45 — dolu küredeki 0.75'ten DÜŞÜK, ölçüp düşürüldü.
    // Dolu kürede fresnel yalnızca ince bir silüet şeridini boyuyordu; kafeste
    // çizgilerin ÇOĞU eğik olduğu için aynı pay tüm orb'u platin beyaza yıkadı
    // ve buz mavisi/kehribar/mor ayrımı kayboldu (2026-08-06, ilk çekimde
    // yakalandı). Renk burada bilgi taşıyor, solmasına izin verilemez.
    vec3 tinted = mix(base, uRimColor, silhouette * 0.45);

    // Taban 0.34 — dolu küredeki 0.2'den yüksek (ışık artık yüzeyden değil
    // çizgiden geliyor), ama frenli: additive harmanlama + bloom
    // (PostProcessing.tsx) üst üste binerken beyaza kırpılma riski kafeste dolu
    // küreden DAHA büyük, çünkü üst üste düşen çizgiler birbirini topluyor.
    vec3 glow = tinted * (0.34 + silhouette * 0.85) * uIntensity;

    gl_FragColor = vec4(glow, uOpacity * mix(1.0, 0.3, backness));
  }
`;
