"""Unity'yi şimdiden öğren: üniversitede sorulunca aramadan göstersin (2026-11-07).

Yunus: "uniyde oyun yapacağım, yapmak istediklerimi bulamayabilirim, o bana göstersin diye şimdiden Unity öğrenebilir."
Her ders `actions/ogrenme.py`nin kayıt dosyasına girer, `learn_how` oradan hemen cevaplar.

Yeniden çalıştırılabilir: öğrenilmiş dersi atlar, yarıda kalırsa kaldığı yerden sürer. Her ders internet araması yapar,
Claude kullanım sınırından yer. Çalıştırma: `venv\\Scripts\\python.exe scripts\\unity_on_ogrenme.py [ders sayısı]`.
"""

from __future__ import annotations

import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from actions import ogrenme as og

APP = "Unity"
VERSION = "Unity 6 (kurulu sürüm 6000.6.4f1), 3D ve 2D, C#. Menü adları Unity'nin İngilizce arayüzündeki gibi."
KEEP_DAYS = 365  # üniversite başlayana kadar lazım; sürüm değişirse fresh=true ile yenilenir
WORKERS = 2
STOP_AFTER_ERRORS = 3  # kullanım sınırı ya da ağ: boşuna denemeye devam etme

DERSLER = """
Unity'de yeni proje nasıl açılır ve şablon nasıl seçilir
Unity arayüzü: Scene Game Hierarchy Project Inspector Console pencereleri ne işe yarar
Unity'de sahneye küp ya da başka nesne nasıl eklenir
Unity'de nesne nasıl taşınır döndürülür ve ölçeklenir
Unity'de sahne görünümünde nasıl gezinilir
Unity'de yeni sahne nasıl oluşturulur ve kaydedilir
Unity'de material nasıl oluşturulur ve nesneye renk nasıl verilir
Unity'de dışarıdan model ve texture nasıl içe aktarılır
Unity'de Prefab nasıl oluşturulur ve kullanılır
Unity'de C# betiği nasıl oluşturulur ve nesneye nasıl eklenir
Unity'de Start ve Update ne işe yarar
Unity'de Inspector'dan değer ayarlamak için public ve SerializeField nasıl kullanılır
Unity'de bir nesneden başka bir nesneye ya da bileşene nasıl erişilir GetComponent
Unity'de klavye ile karakter nasıl hareket ettirilir
Unity'de yeni Input System nasıl kurulur ve kullanılır
Unity'de karakter nasıl zıplatılır
Unity'de Rigidbody ve Collider nasıl eklenir
Unity'de iki nesnenin çarpışması nasıl algılanır OnCollisionEnter OnTriggerEnter
Unity'de Character Controller nasıl kullanılır
Unity'de birinci şahıs kamera ve fare ile bakış nasıl yapılır
Unity'de kamera karakteri nasıl takip eder Cinemachine
Unity'de nesne kod ile nasıl oluşturulur ve yok edilir Instantiate Destroy
Unity'de ateş etme ve mermi nasıl yapılır
Unity'de Coroutine nasıl kullanılır
Unity'de sahneler arası nasıl geçilir SceneManager
Unity'de ekrana yazı ve puan nasıl yazdırılır UI Canvas TextMeshPro
Unity'de ana menü ve düğme nasıl yapılır
Unity'de can barı nasıl yapılır
Unity'de oyun durdurma ve zaman kontrolü nasıl yapılır Time.timeScale
Unity'de ses ve müzik nasıl eklenir AudioSource
Unity'de Animator ile animasyon nasıl yapılır
Unity'de ışık nasıl eklenir ve ayarlanır
Unity'de düşman yapay zekası NavMesh ile oyuncuyu nasıl takip eder
Unity'de Particle System ile efekt nasıl yapılır
Unity'de 2D sprite nasıl eklenir ve 2D karakter nasıl hareket ettirilir
Unity'de Tilemap ile 2D harita nasıl yapılır
Unity'de oyun verisi nasıl kaydedilir PlayerPrefs JSON
Unity'de hata nasıl ayıklanır Debug.Log ve Console hataları nasıl okunur
Unity'de sık görülen NullReferenceException ve pembe material hatası nasıl çözülür
Unity'de oyun Windows için nasıl derlenir Build Profiles
Unity projesi Git ile nasıl kullanılır .gitignore ve sürüm kontrolü
""".strip().splitlines()

_errors = 0
_lock = threading.Lock()


def one(question: str, index: int, total: int) -> None:
    global _errors
    with _lock:
        if _errors >= STOP_AFTER_ERRORS:
            return
    started = time.time()
    try:
        lesson = og._research({"id": uuid.uuid4().hex[:12], "question": question, "app": APP, "context": VERSION})
    except Exception as error:
        with _lock:
            _errors += 1
        print(f"[{index}/{total}] HATA {question[:60]}: {str(error)[:160]}", flush=True)
        return
    if not lesson["answer"]:
        print(f"[{index}/{total}] BOŞ {question[:60]}", flush=True)
        return
    lesson["keep_days"] = KEEP_DAYS
    og.remember(lesson)
    print(f"[{index}/{total}] {time.time() - started:.0f} sn, {len(lesson['steps'])} adım, güven {lesson['confidence']}: {question[:60]}", flush=True)


def main() -> int:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(DERSLER)
    todo = [q for q in DERSLER if og.recall(q, APP) is None][:limit]
    print(f"{len(DERSLER)} dersten {len(todo)} tanesi öğrenilecek", flush=True)
    with ThreadPoolExecutor(WORKERS) as pool:
        for i, question in enumerate(todo, 1):
            pool.submit(one, question, i, len(todo))
    learned = sum(1 for item in og._load() if item.get("app") == APP)
    print(f"bitti: kayıtta {learned} Unity dersi, {_errors} hata", flush=True)
    return 1 if _errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
