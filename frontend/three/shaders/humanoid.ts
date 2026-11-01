// CHIRON — İnsan görünümü, "Krom" biçimi (2026-11-02). Geometri: three/humanoidKrom.ts.
//
// Tek uniform (uMorph 0→1) hikâyeyi anlatıyor: çekirdekten bir parçacık sürüsü
// fışkırıyor, parçacıklar aşağıdan yukarı taramadaki yerlerine akıyor. Geri
// dönüşte aynı yol tersine işliyor.
//
// Aynı geometri iki kez çiziliyor: normal geçiş ve uHalo=1 ile 3.4 kat büyük, çok
// soluk bir parlama geçişi (ucuz bloom — sahnenin Bloom'u eşiğin altında kalan
// gümüşü yeterince ışıtmıyordu).
//
// Karışım AdditiveBlending, alfa asla negatif değil, nokta boyutu üst sınırlı —
// shaders/dustField.ts'deki iki arıza burada da kapalı.

export const HUMANOID_VERTEX_SHADER = /* glsl */ `
  attribute vec3 aSeed;
  attribute float aPart;
  attribute float aTint;
  attribute float aA;
  attribute float aDelay;

  uniform float uTime;
  uniform float uMorph;
  uniform float uSpeak;
  uniform float uListen;
  uniform float uYaw;
  uniform float uPitch;
  uniform float uBlink;
  uniform float uHalo;
  uniform float uPivotY;
  uniform float uEyeY;
  uniform float uSize;
  uniform float uMaxSize;
  uniform float uPixelRatio;
  uniform vec3 uC0;
  uniform vec3 uC1;
  uniform vec3 uC2;
  uniform vec3 uC3;

  varying vec3 vColor;
  varying float vAlpha;

  vec3 rotY(vec3 p, float a) { float c = cos(a), s = sin(a); return vec3(c*p.x + s*p.z, p.y, -s*p.x + c*p.z); }
  vec3 rotX(vec3 p, float a) { float c = cos(a), s = sin(a); return vec3(p.x, c*p.y - s*p.z, s*p.y + c*p.z); }
  bool isPart(float k) { return abs(aPart - k) < 0.5; }

  // Sürü: çekirdeğin çevresinde sarmal çizen, kuyruğu açılan bir şerit (tarama birimlerinde).
  vec3 swarm(vec3 s, float t) {
    float u = fract(s.x + t * 0.05);
    float ang = u * 6.2832 * 1.15 + t * 0.35 + s.y * 0.3;
    float r = 1.0 + 6.0 * u;
    vec3 p = vec3(cos(ang) * r, sin(ang * 0.8) * r * 0.45 - 0.5 + (u - 0.5) * 2.5, sin(ang) * r * 0.4);
    return p + (s - 0.5) * (0.25 + 2.2 * u * u);
  }

  void main() {
    vec3 p = position;
    float t = uTime;
    float glow = 1.0;

    // Çene: Chiron konuşurken ağzın altı aşağı iniyor.
    float jaw = smoothstep(0.42, 0.2, p.y) * smoothstep(-0.9, -0.2, p.y)
              * smoothstep(1.15, 0.5, abs(p.x)) * smoothstep(0.2, 1.0, p.z);
    p.y -= jaw * uSpeak * 0.16 * (0.45 + 0.55 * abs(sin(t * 8.5)));

    if (isPart(1.)) glow = 0.9 + uSpeak * 0.35 + uListen * 0.4;           // dikişler
    if (isPart(2.)) {                                                      // gözler
      p.y = uEyeY + (p.y - uEyeY) * (1.0 - 0.92 * uBlink);
      glow = 1.1 + 0.25 * sin(t * 2.1) + uSpeak * 0.6 * (0.5 + 0.5 * sin(t * 11.0)) + uListen * 0.5;
    }
    if (isPart(3.)) glow = 0.9 + 0.2 * sin(t * 1.6) + uSpeak * 0.6;       // göğüs çekirdeği

    // Kafa ve boyun imleci izliyor, omuzlar sabit.
    float w = smoothstep(-2.2, -0.9, position.y);
    vec3 q = p - vec3(0.0, uPivotY, 0.0);
    p = rotX(rotY(q, uYaw * w), uPitch * w) + vec3(0.0, uPivotY, 0.0);

    float progress = smoothstep(aDelay * 0.6, aDelay * 0.6 + 0.4, uMorph);
    vec3 src = swarm(aSeed, t) * smoothstep(0.0, 0.2, uMorph);
    vec3 pos = mix(src, p, progress) + vec3(-p.z, 0.0, p.x) * sin(progress * 3.14159) * 0.35;

    float k = clamp(aTint, 0.0, 3.0);
    vec3 col = k < 1.0 ? mix(uC0, uC1, k) : (k < 2.0 ? mix(uC1, uC2, k - 1.0) : mix(uC2, uC3, k - 2.0));
    vColor = col * (1.0 + 0.25 * uHalo);
    float twinkle = 0.8 + 0.2 * sin(t * (1.4 + aSeed.y * 3.0) + aSeed.x * 40.0);
    vAlpha = aA * mix(0.45, 1.0, progress) * twinkle * glow
           * smoothstep(0.0, 0.04, uMorph) * mix(1.0, 0.06, uHalo);

    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    float dist = max(-mv.z, 0.1);
    float size = uSize * uPixelRatio * (0.7 + aSeed.z * 0.6) * (10.0 / dist) * (glow > 1.25 ? 1.3 : 1.0);
    gl_PointSize = uHalo > 0.5 ? min(size * 3.4, uMaxSize * 3.4 * uPixelRatio) : min(size, uMaxSize * uPixelRatio);
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
