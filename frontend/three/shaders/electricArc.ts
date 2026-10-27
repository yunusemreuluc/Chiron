// CHIRON Electric Arcs — ince, katkılı-harmanlanmış (additive) tüp geometrisi
// üzerinde uçlara doğru solan, titreşen bir ışıma. vUv.x tüpün uzunluğu boyunca
// 0→1 gider; sin(π·x) iki ucu da sıfırlarken ortada en parlak noktayı verir.
export const ELECTRIC_ARC_VERTEX_SHADER = /* glsl */ `
  varying vec2 vUv;

  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const ELECTRIC_ARC_FRAGMENT_SHADER = /* glsl */ `
  uniform vec3 uColor;
  uniform float uTime;
  uniform float uIntensity;
  uniform float uSeed;
  varying vec2 vUv;

  void main() {
    float edgeFade = sin(3.14159265 * clamp(vUv.x, 0.0, 1.0));
    float flicker = 0.6 + 0.4 * sin(uTime * 26.0 + uSeed * 12.9898);
    float glow = edgeFade * uIntensity * flicker * 1.8;
    gl_FragColor = vec4(uColor * glow, glow);
  }
`;
