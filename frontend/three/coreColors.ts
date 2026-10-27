import type { AIState } from '@/stores/aiStateStore';

// CHIRON — çekirdeğin durum paleti (yalnızca renk verisi).
//
// Bu dosya 2026-09-15'te palette.ts'ten ayrıldı ve bilerek `three` import
// ETMİYOR: telefon arayüzü (components/remote) aynı renkleri kullanıyor ama
// WebGL çizmiyor. Renkler palette.ts'te kalsaydı, oradaki THREE.Color önbelleği
// yüzünden telefona ~400 KB'lık Three.js paketi de inerdi. Tek kaynak kuralı
// bozulmadı — palette.ts buradan yeniden dışa aktarıyor.
//
// TEK KAYNAK OLMASI ŞART: çekirdek (EnergyCore), onu saran parçacık koronası
// (EnergyTendrils) ve elektrik arkları (ElectricArcs) ayrı bileşenler ama AYNI
// cismin parçaları. Renkleri üç yerde ayrı yazılsaydı konuşma rengi
// değiştiğinde biri geride kalır ve yeşil bir çekirdeğin etrafında mavi bir
// korona dönerdi.
//
// Kullanıcı isteğiyle (2026-07-30): Chiron KONUŞURKEN çekirdek maviden çıkıp
// turkuaz-yeşil bir plazmaya dönüyor (bkz. PLASMA_TEAL — beş ton karşılaştırılıp
// seçildi). Palet bilerek doygun neon değil: bloom (PostProcessing.tsx) üstüne
// bindiğinde beyaza kırpılmaması gerekiyor.
// Diğer durumlar globals.css'teki "Platin + Buz Mavisi" sisteminde kalıyor;
// renk dekorasyon değil, "Chiron şu an konuşuyor" bilgisini taşıyor.

export interface CorePalette {
  /** Gövdenin derin tonu — gölgede kalan yarı (shader'da uColorA). */
  bodyDeep: string;
  /** Gövdenin aydınlık tonu (shader'da uColorB). */
  bodyLight: string;
  /** Fresnel kenarı — gövdeden AYRI ve daha parlak bir ton (uRimColor). */
  rim: string;
  /** Çekirdeği saran parçacık koronası (EnergyTendrils uColor). */
  corona: string;
}

/** Platin + Buz Mavisi — varsayılan hâl (bkz. app/globals.css). */
const ICE: CorePalette = {
  bodyDeep: '#3f6db8',
  bodyLight: '#7fb2ff',
  rim: '#e8eef7',
  corona: '#bcd6ff',
};

/**
 * Konuşma — turkuaz-yeşil gövde, buzlu nane kenar.
 *
 * Kullanıcı seçimi (2026-07-30), beş ton yan yana çizilip karşılaştırıldıktan
 * sonra. Yol şuydu: ilk deneme limon-altındı (gövde #a8e05c, kenar #f0ffc4) ve
 * gövdeyle kenar aynı hueye düştüğü için küre tek düze bir asit yeşiline
 * yıkanıyordu; ikinci deneme kenarı altına çekip gövde/kenar ayrımını kurdu ama
 * gövde hâlâ fazla sıcak ve parlaktı.
 *
 * Bu palet yeşilin en SOĞUK ucunda duruyor ve asıl kazancı bu: ICE ile aynı renk
 * sıcaklığında kaldığı için idle → speaking geçişi bir renk kavgası değil, aynı
 * ailenin içinde bir kayma gibi okunuyor. Kenar (nane-beyaz) gövdeden hâlâ ayrı —
 * ICE'deki gövde/platin ilişkisinin karşılığı.
 */
const PLASMA_TEAL: CorePalette = {
  bodyDeep: '#06403c',
  bodyLight: '#4fd6a8',
  rim: '#dffff4',
  corona: '#8ae8c8',
};

/**
 * Otomasyon — Chiron makineye DOKUNUYOR (ekran müdahalesi, uygulama açma,
 * kabuk komutu). 2026-07-31, bkz. Notes/Arayuz.md § Beş tepki.
 *
 * Kehribar seçildi çünkü sahnede kullanılmayan tek aile o: ICE mavi, konuşma
 * turkuaz, uyku çelik. Ama asıl gerekçe anlamsal — kehribar her arayüzde
 * "dikkat, makine hareket ediyor" demek. Chiron'un fareyi ele aldığı an
 * kullanıcının bunu ANINDA fark etmesi gerekiyor; bu, dekorasyon değil uyarı.
 *
 * Kırmızıya kaçılmadı: kırmızı "hata" der, oysa burada her şey yolunda.
 * Doygunluk PLASMA_TEAL'inkiyle aynı hizada — bloom altında beyaza kırpılmaması
 * için (bkz. PostProcessing.tsx).
 */
const SOLAR_AMBER: CorePalette = {
  bodyDeep: '#3d2408',
  bodyLight: '#e0a355',
  rim: '#fff0d6',
  corona: '#f0c489',
};

/**
 * Hafıza — Chiron kendi belleğine uzanıyor (kayıt, silme, "şunu tanı").
 *
 * Mor, tayfın soğuk ucunda ve mavinin ÖTESİNDE: ICE ile aynı yönde ama daha
 * derinde. Amaçlanan okuma bu — hafıza dışarıdaki bir iş değil, çekirdeğin
 * kendi içine bakması. Kehribarın karşı kutbu, yani otomasyon ile hafıza
 * yan yana geldiğinde asla karışmıyor.
 *
 * Gövde bilerek koyu: hatırlamak parlamak değil, derinden bir şey çıkarmak.
 *
 * Kenar (rim) diğer paletlerdeki gibi neredeyse beyaz DEĞİL, mora boyalı. İlk
 * deneme `#ece4ff` idi ve ölçüm şunu gösterdi: fresnel kenarı kürenin parlak
 * piksellerine hâkim olduğu için doygunluk %15'e düşüyor, yani mor durum
 * sahnenin en soluk hâli oluyordu. Renk burada bilgi taşıyor — solmasına
 * izin verilemez.
 */
const DEEP_VIOLET: CorePalette = {
  bodyDeep: '#2a1650',
  bodyLight: '#9c6ef0',
  rim: '#dcc9ff',
  corona: '#c3a2ff',
};

export const STATE_PALETTE: Record<AIState, CorePalette> = {
  idle: ICE,
  listening: ICE,
  thinking: ICE,
  speaking: PLASMA_TEAL,
  vision: ICE,
  automation: SOLAR_AMBER,
  memory: DEEP_VIOLET,
};

/**
 * Uyku — renk YOK, yalnızca soğuk çelik.
 *
 * Uyuyan Chiron'un sönmüş değil "dinlenen" görünmesi bu paletin işi: gövde
 * neredeyse zemine karışıyor ama kenar hattı hâlâ okunuyor, yani cisim orada
 * duruyor. Tamamen siyaha indirilseydi uygulama çökmüş gibi görünürdü.
 */
export const SLEEP_PALETTE: CorePalette = {
  bodyDeep: '#0c141f',
  bodyLight: '#28374d',
  rim: '#5a7095',
  corona: '#2b3c54',
};

