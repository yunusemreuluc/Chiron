// CHIRON — atmosfer tozu. drei'nin <Sparkles> bileşeninin yerini aldı (2026-07-29).
//
// NEDEN KENDİ SHADER'IMIZ: drei'nin Sparkles fragment shader'ı alfayı
//     strength = 0.05 / distanceToCenter - 0.1
// diye hesaplıyor; karenin köşelerinde distanceToCenter ≈ 0.707 olduğu için bu
// değer NEGATİF oluyor. Normal 8-bit hedefte negatif alfa kırpılır ve kimse fark
// etmez — ama post-processing zinciri (EffectComposer) HDR/half-float hedef
// kullandığı için kırpılmıyor: karışım denklemi sahneden renk ÇIKARIYOR, yani
// ortası parlak, kendisi kapkara dev bir kare beliriyordu.
//
// İkinci sorun: gl_PointSize mesafeye bölünüyor ve parçacık kutusu kameranın
// bulunduğu derinliğe kadar uzanıyordu; bir parçacık kameranın yanından geçince
// nokta boyutu patlıyordu.
//
// Buradaki çözüm ikisini birden kapatıyor:
//   1) AdditiveBlending + alfa asla negatif değil  → karartma imkânsız
//   2) gl_PointSize üst sınırlı + kameraya yaklaşan parçacık sönümleniyor
export const DUST_FIELD_VERTEX_SHADER = /* glsl */ `
  attribute vec3 aSeed;
  uniform float uTime;
  uniform float uSpeed;
  uniform float uSize;
  uniform float uMaxSize;
  uniform float uPixelRatio;
  varying float vFade;

  const float TAU = 6.2831853;

  void main() {
    // Her parçacık kendi fazında, birbirinden bağımsız süzülüyor.
    vec3 drift = vec3(
      sin(uTime * uSpeed + aSeed.x * TAU),
      cos(uTime * uSpeed * 0.8 + aSeed.y * TAU),
      sin(uTime * uSpeed * 0.6 + aSeed.z * TAU)
    );
    vec4 mvPosition = modelViewMatrix * vec4(position + drift * 0.6, 1.0);

    float distance = max(-mvPosition.z, 0.1);
    // ÜST SINIR: mesafe sıfıra giderken boyut sonsuza gitmesin.
    gl_PointSize = min(uSize * uPixelRatio * (22.0 / distance), uMaxSize * uPixelRatio);
    // Kameraya çok yaklaşan parçacık tamamen sönüyor — yakın plandaki dev bir
    // leke, uzaklıktaki bir toz zerresinden çok daha rahatsız edici.
    vFade = smoothstep(1.5, 5.0, distance);

    gl_Position = projectionMatrix * mvPosition;
  }
`;

export const DUST_FIELD_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying float vFade;

  void main() {
    float dist = length(gl_PointCoord - 0.5);
    if (dist > 0.5) discard;

    // Yumuşak yuvarlak zerre. Kare köşeleri discard ile atıldığı ve alfa hiçbir
    // zaman negatif olamadığı için arkaplanı karartması mümkün değil.
    float strength = smoothstep(0.5, 0.0, dist);
    gl_FragColor = vec4(uColor, strength * strength * uOpacity * vFade);
  }
`;
