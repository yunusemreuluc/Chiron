// CHIRON Energy Tendrils — çekirdek yüzeyinden dışarı doğru sürüklenen, sönümlenen
// ince enerji parçacıkları. Her parçacık kendi yönünde (aDirection) sabit bir
// döngüyle (aOffset ile kaydırılmış) merkezden dışarı akıyor — GPU'da, CPU'da
// her kare pozisyon güncellemeden (ucuz).
export const ENERGY_TENDRILS_VERTEX_SHADER = /* glsl */ `
  attribute vec3 aDirection;
  attribute float aOffset;
  uniform float uTime;
  uniform float uSpeed;
  uniform float uCoreRadius;
  uniform float uMaxDistance;
  uniform float uPointSize;
  varying float vProgress;

  void main() {
    float cycle = fract(uTime * uSpeed + aOffset);
    vProgress = cycle;

    vec3 pos = aDirection * (uCoreRadius + cycle * uMaxDistance);
    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);

    gl_PointSize = uPointSize * (1.0 - cycle * 0.6) * (30.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

export const ENERGY_TENDRILS_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColor;
  varying float vProgress;

  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float dist = length(uv);
    if (dist > 0.5) discard;

    float shape = smoothstep(0.5, 0.0, dist);
    float fadeIn = smoothstep(0.0, 0.12, vProgress);
    float fadeOut = smoothstep(1.0, 0.55, vProgress);
    float alpha = shape * fadeIn * fadeOut;

    gl_FragColor = vec4(uColor, alpha);
  }
`;
