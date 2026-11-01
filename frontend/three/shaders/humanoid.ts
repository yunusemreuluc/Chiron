// CHIRON — İnsan görünümü shader'ları (2026-11-01).
//
// Tek bir uniform (uMorph 0→1) bütün hikâyeyi anlatıyor:
//   0.00–0.20  çekirdekten bir parçacık kuyruklu yıldızı fışkırıyor (sürü)
//   0.15–1.00  parçacıklar aşağıdan yukarı büstteki yerlerine akıyor
// Geri dönüşte aynı yol tersine işliyor: büst çözülüp çekirdeğe çekiliyor.
//
// Bellek: her şey GPU'da. CPU kare başına yalnızca birkaç uniform yazıyor
// (Notes/Bilinen-Tuzaklar.md § useFrame içinde asla bellek ayırma).
// Karışım AdditiveBlending, alfa asla negatif değil, nokta boyutu üst sınırlı —
// shaders/dustField.ts'deki iki arızanın ikisi de burada da kapalı.

export const HUMANOID_VERTEX_SHADER = /* glsl */ `
  attribute vec3 aSeed;
  attribute float aTint;
  attribute float aDelay;
  attribute float aKind;

  uniform float uTime;
  uniform float uMorph;
  uniform float uSpeak;
  uniform float uListen;
  uniform float uYaw;
  uniform float uPitch;
  uniform float uPivotY;
  uniform float uSize;
  uniform float uMaxSize;
  uniform float uPixelRatio;
  uniform vec3 uBlue;
  uniform vec3 uIce;
  uniform vec3 uEmber;
  uniform vec3 uGold;

  varying vec3 vColor;
  varying float vAlpha;

  const float TAU = 6.2831853;

  // Sürü: çekirdeğin çevresinde sarmal çizen, kuyruğu açılan bir parçacık şeridi.
  vec3 swarm(vec3 s, float t) {
    float u = fract(s.x + t * 0.05);
    float ang = u * TAU * 1.15 + t * 0.35 + s.y * 0.3;
    float r = 0.5 + 3.1 * u;
    vec3 p = vec3(cos(ang) * r, sin(ang * 0.8) * r * 0.45 - 0.3 + (u - 0.5) * 1.2, sin(ang) * r * 0.4);
    return p + (s - 0.5) * (0.12 + 1.1 * u * u);
  }

  vec3 rotateHead(vec3 p, float w) {
    vec3 q = p - vec3(0.0, uPivotY, 0.0);
    float cy = cos(uYaw * w), sy = sin(uYaw * w);
    q = vec3(cy * q.x + sy * q.z, q.y, -sy * q.x + cy * q.z);
    float cx = cos(uPitch * w), sx = sin(uPitch * w);
    q = vec3(q.x, cx * q.y - sx * q.z, sx * q.y + cx * q.z);
    return q + vec3(0.0, uPivotY, 0.0);
  }

  void main() {
    vec3 target = position;
    bool isHalo = aKind > 1.5;

    if (isHalo) {
      // Hale halkaları kafanın merkezinden dışa doğru nefes alıyor; konuşurken
      // dalga halkadan halkaya koşuyor.
      vec2 c = vec2(0.0, 1.65);
      float ring = aSeed.z;
      float pulse = 0.035 * sin(uTime * 1.3 - ring * 5.0)
                  + uSpeak * 0.09 * sin(uTime * 6.0 - ring * 8.0)
                  + uListen * 0.05;
      target.xy = c + (target.xy - c) * (1.0 + pulse);
    } else {
      // Canlılık: yüzey hiç durmuyor — hafif titreşim, konuşurken boyundan
      // tepeye yürüyen bir kontur dalgası, dinlerken mikrofona tepki.
      vec3 n = normalize(vec3(target.x, 0.0, target.z - 0.05) + 1e-4);
      float head = smoothstep(0.3, 1.0, target.y);
      float disp = 0.01 * sin(uTime * 1.7 + aSeed.z * TAU)
                 + uSpeak * 0.03 * sin(target.y * 9.0 - uTime * 7.0) * head
                 + uListen * 0.05 * (aSeed.y - 0.3) * head;
      target += n * disp;
    }

    // Kafa (ve hale) fareyi izliyor; göğüs sabit, boyun arada bükülüyor.
    float w = isHalo ? 1.0 : smoothstep(0.2, 0.85, position.y);
    target = rotateHead(target, w);

    float progress = smoothstep(aDelay * 0.65, aDelay * 0.65 + 0.35, uMorph);
    float emerge = smoothstep(0.0, 0.2, uMorph);
    vec3 src = swarm(aSeed, uTime) * emerge;
    // Yol düz değil: parçacıklar yerlerine giderken eksen etrafında kıvrılıyor.
    vec3 swirl = vec3(-target.z, 0.0, target.x) * sin(progress * 3.14159) * 0.6;
    vec3 p = mix(src, target, progress) + swirl;

    // Renk: mavi konturlar, yüzde ve damarlarda kor turuncusu, en parlak
    // noktalar buz beyazına kayıyor.
    float twinkle = 0.72 + 0.28 * sin(uTime * (1.4 + aSeed.y * 3.0) + aSeed.x * 40.0);
    vec3 base = mix(uBlue, uIce, aSeed.y * aSeed.y * 0.6);
    float ember = aTint * progress * (0.85 + 0.15 * sin(uTime * 2.2 + position.y * 6.0) + uSpeak * 0.35);
    vColor = mix(base, uEmber, clamp(ember, 0.0, 1.0));
    // Damarlar kendi renginde: turuncu + mavi toplamı pembeye kayıyordu.
    if (aKind > 0.5 && aKind < 1.5) vColor = mix(base, uGold, progress);

    // Arka yüz ve gövdenin alt ucu sönük: önden bakan konturlar okunuyor.
    float facing = smoothstep(-0.7, 0.6, position.z);
    float bottom = smoothstep(-2.7, -1.5, position.y);
    float alpha = isHalo ? (0.16 + uSpeak * 0.3 + uListen * 0.15) : (0.25 + 0.75 * facing) * bottom;
    if (aKind > 0.5 && aKind < 1.5) alpha = 0.7 * smoothstep(-1.1, -0.4, position.y);
    vAlpha = mix(0.55 * emerge, alpha, progress) * twinkle * smoothstep(0.0, 0.04, uMorph);

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    float dist = max(-mv.z, 0.1);
    float kindSize = aKind > 0.5 && aKind < 1.5 ? 1.15 : (isHalo ? 0.8 : 1.0);
    gl_PointSize = min(uSize * kindSize * (0.7 + aSeed.z * 0.6) * uPixelRatio * (10.0 / dist),
                       uMaxSize * uPixelRatio);
    gl_Position = projectionMatrix * mv;
  }
`;

export const HUMANOID_FRAGMENT_SHADER = /* glsl */ `
  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.0, d);
    gl_FragColor = vec4(vColor, a * a * vAlpha);
  }
`;

// ── Yüz çekirdeği: kafanın içinde yanan turuncu ışık (billboard sprite) ──
export const GLOW_VERTEX_SHADER = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const GLOW_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColor;
  uniform float uIntensity;
  uniform float uTime;
  varying vec2 vUv;
  void main() {
    vec2 c = vUv - 0.5;
    float d = length(c) * 2.0;
    // Yatay dalgalı bantlar: referanstaki yüzdeki kor çizgileri.
    float bands = 0.75 + 0.25 * sin(c.y * 60.0 + sin(c.x * 9.0 + uTime) * 2.0 - uTime * 1.5);
    float glow = pow(max(0.0, 1.0 - d), 2.6) * bands;
    gl_FragColor = vec4(uColor, glow * uIntensity);
  }
`;

// ── Dağlar ──
export const RANGE_VERTEX_SHADER = /* glsl */ `
  attribute vec3 aSeed;
  attribute float aTint;
  attribute float aDelay;

  uniform float uTime;
  uniform float uReveal;
  uniform float uSize;
  uniform float uMaxSize;
  uniform float uPixelRatio;
  uniform vec3 uBlue;
  uniform vec3 uEmber;

  varying vec3 vColor;
  varying float vAlpha;

  void main() {
    float progress = smoothstep(aDelay * 0.6, aDelay * 0.6 + 0.4, uReveal);
    vec3 p = position;
    // Dağlar yerden yükseliyor.
    p.y = mix(-4.6, p.y, progress);

    // Lav çizgileri boyunca akan ışık.
    float flow = 0.65 + 0.35 * sin(uTime * 1.2 - (position.x + position.z) * 0.6);
    float twinkle = 0.7 + 0.3 * sin(uTime * (0.8 + aSeed.y * 2.0) + aSeed.x * 50.0);
    vColor = mix(uBlue, uEmber, aTint) * (0.7 + 0.7 * aSeed.z);
    vAlpha = progress * twinkle * (aTint > 0.1 ? flow : 0.7) * (0.45 + 0.55 * aSeed.z);

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    float dist = max(-mv.z, 0.1);
    gl_PointSize = min(uSize * (0.6 + aSeed.y * 0.8) * uPixelRatio * (14.0 / dist) * (1.0 + aTint * 0.6),
                       uMaxSize * uPixelRatio);
    gl_Position = projectionMatrix * mv;
  }
`;
