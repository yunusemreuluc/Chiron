"""
Chiron — Gemini Live araç (tool) tanımları
Windows masaüstü çekirdeği (main.py) kullanır.
"""

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": "Windows'ta herhangi bir uygulamayı açar. Spotify, Chrome, Terminal, Dosya Gezgini, VS Code vb.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Uygulama adı (örn. 'Spotify', 'Chrome', 'Terminal')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "sys_info",
        "description": "Sistem bilgisi alır: pil durumu, CPU, RAM, disk, saat, tarih, ağ bağlantısı.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "battery | cpu | ram | disk | time | date | network | all"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "delegate_to_pc",
        "description": (
            "PC'de is yapar: kod yazar, projelerde/dosyalarda calisir (Dilcep, Chiron, Etsy...). Kullanici PC'de "
            "bir sey yapilmasini isterse ('Dilcep'te alt bari degistir', 'su projeye sunu ekle', 'hesap kismini "
            "gelistir') ILK IS bunu cagir; once soru sorma, onay isteme, belirsiz olsa da oldugu gibi gonder. "
            "Is Komuta ekranindaki konusmanin devami olarak arka planda surer. Ekrana bakip cevaplanacak soru "
            "icin DEGIL (onun icin analyze_screen)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task": {
                    "type": "STRING",
                    "description": "Kullanicinin istedigi is, kendi sozuyle ve ayrintisiyla; yorum ekleme."
                },
                "new_topic": {
                    "type": "BOOLEAN",
                    "description": "Onceki PC isiyle ilgisiz yeni bir konu (baska proje/is) ise true; devam isteginde verme."
                }
            },
            "required": ["task"]
        }
    },
    {
        "name": "answer_approval",
        "description": (
            "PC'deki bir oturumun izin sorusuna (komut calistirma, dosya yazma) cevap verir. Kullanici 'izin ver', "
            "'onayla', 'Dilcep'e izin ver', 'reddet', 'hayir yapma, sunu yap', 'ne onay bekliyor' derse bunu cagir. "
            "IZIN icin once confirm=false: araç istegi dondurur, kullaniciya OKU ve sor; acikca evet derse ayni "
            "oturumla confirm=true. Red tek adimda; kullanici bir talimat soylediyse message'a yaz."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "decision": {
                    "type": "STRING",
                    "description": "izin | red | liste (bekleyenleri soyle)"
                },
                "session": {
                    "type": "STRING",
                    "description": "Oturum/proje adi (Dilcep, Chiron...). Tek bekleyen varsa bos birak."
                },
                "message": {
                    "type": "STRING",
                    "description": "Red edilince oturuma iletilecek talimat, kullanicinin kendi sozuyle."
                },
                "always": {
                    "type": "BOOLEAN",
                    "description": "Kullanici 'bir daha sorma' derse true (yalniz izinde)."
                },
                "confirm": {
                    "type": "BOOLEAN",
                    "description": "Yalniz kullanici istegi duyup acikca onayladiktan sonra true."
                }
            },
            "required": ["decision"]
        }
    },
    {
        "name": "manage_window",
        "description": (
            "Acik pencereleri yonetir: one getirir, kucultur, tam ekran yapar, eski boyutuna alir, kapatir, "
            "ekranin sol/sag yarisina yaslar, masaustunu gosterir, acik pencereleri listeler. "
            "'Chrome'a gec', 'pencereyi kucult', 'Spotify'i kapat', 'bunu sola yasla', 'masaustunu goster', "
            "'hangi pencereler acik' dediginde kullan. Uygulama acmak icin open_app."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "list | focus | minimize | maximize | restore | close | left | right | show_desktop."
                },
                "app": {
                    "type": "STRING",
                    "description": "Surec adi ya da baslik parcasi (chrome, spotify, code, explorer, 'tarayici'). "
                                   "'Bu pencere' denirse bos birak: ondeki pencere."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "open_terminal",
        "description": (
            "Windows Terminal'de yeni sekme acar, istenen projenin klasorunde, icinde Claude'u baslatir. "
            "'Terminalde yeni sekme ac ve Claude'a baglan', 'Dilcep'te Claude ac', 'terminalde Chiron'a gec' "
            "dediginde kullan. Kullanici kendisi terminalde calismak istiyorsa bu; isi senin yapmani istiyorsa "
            "delegate_to_pc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "project": {
                    "type": "STRING",
                    "description": "Proje adi (Chiron, Dilcep, chiron-mobile...); belirtilmediyse bos birak (ev klasoru)."
                },
                "run_claude": {
                    "type": "BOOLEAN",
                    "description": "Sekmede Claude baslasin mi. Varsayilan true; sadece 'terminal ac/sekme ac' denirse false."
                },
                "continue_last": {
                    "type": "BOOLEAN",
                    "description": "'Kaldigi yerden', 'son konusmaya devam', 'onceki oturuma baglan' denirse true."
                }
            }
        }
    },
    {
        "name": "check_pc_job",
        "description": (
            "PC'de verilmis isin canli durumu: suruyor mu, kac dakikadir, su an hangi adimda, bittiyse sonucu. "
            "Kullanici 'is ne durumda', 'bitti mi', 'ne yapiyorsun su an', 'Dilcep isi ne alemde' derse cagir. "
            "Salt okuma; isi durdurmaz. [SUREN IS] bilgisi eski olabilir, durum sorulunca her zaman bunu cagir."
        ),
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "get_weather",
        "description": (
            "Anlik hava durumunu ozetler. Kullanici hava durumunu, sicakligi veya yagmur "
            "durumunu sordugunda kullan. Chiron kullanicinin GERCEK konumunu kendisi tespit "
            "ediyor — konumsuz sorularda ('hava nasil', 'disarisi soguk mu') location'i BOS "
            "BIRAK, sehir tahmin etme."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "location": {
                    "type": "STRING",
                    "description": (
                        "Sadece kullanici ACIKCA baska bir yeri sorduysa doldur "
                        "(\"Ankara'da hava nasil\"). Aksi halde bos birak — bos birakilinca "
                        "kullanicinin gercek konumu kullanilir."
                    )
                }
            }
        }
    },
    {
        "name": "get_calendar_events",
        "description": (
            "Takvim (Google Calendar) etkinliklerini okur. "
            "Bugun, yarin, siradaki etkinlik veya yaklasan ajandayi ozetler. "
            "Kullanici toplanti, takvim, ajanda, etkinlik veya gunluk programini sordugunda kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": (
                        "today | tomorrow | next | agenda | week veya dogal dilde "
                        "'onumuzdeki 30 gun', '2 hafta', 'bu ay', 'gelecek ay'"
                    )
                },
                "limit": {
                    "type": "NUMBER",
                    "description": "Maksimum etkinlik sayisi"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "add_calendar_event",
        "description": (
            "Takvim (Google Calendar) servisine yeni etkinlik ekler. "
            "Kullanici toplanti, randevu, takvime ekleme veya etkinlik olusturma isterse kullan. "
            "Baslangic tarihini gercek tarih/saat olarak ver; bitis verilmezse varsayilan sure kullanilir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {
                    "type": "STRING",
                    "description": "Etkinlik basligi. Ornek: 'Disci Randevusu'"
                },
                "start_iso": {
                    "type": "STRING",
                    "description": "Baslangic tarih/saat. ISO veya yyyy-MM-dd HH:mm formatinda."
                },
                "end_iso": {
                    "type": "STRING",
                    "description": "Bitis tarih/saat. Opsiyonel."
                },
                "location": {
                    "type": "STRING",
                    "description": "Etkinlik konumu. Opsiyonel."
                },
                "notes": {
                    "type": "STRING",
                    "description": "Etkinlik notlari. Opsiyonel."
                },
                "calendar_name": {
                    "type": "STRING",
                    "description": "Eklenecek takvim adi. Opsiyonel."
                },
                "all_day": {
                    "type": "BOOLEAN",
                    "description": "true ise tum gun etkinligi olusturur."
                }
            },
            "required": ["title", "start_iso"]
        }
    },
    {
        "name": "delete_calendar_event",
        "description": (
            "Takvim (Google Calendar) servisinden etkinlik siler. "
            "Kullanici bir toplantiyi, randevuyu veya takvim kaydini silmek istediginde kullan. "
            "Ayni ada birden fazla etkinlik varsa dogru kaydi bulmak icin baslangic tarihini gercek tarih/saat olarak ver. "
            "IKI ADIMDA kullan: (1) ONCE confirm=false ile cagir (sadece ne yapilacagini aciklar, HICBIR SEY YAPMAZ), "
            "kullaniciya sesli aktarip onay iste; (2) kullanici onaylarsa AYNI parametrelerle confirm=true olarak TEKRAR cagir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {
                    "type": "STRING",
                    "description": "Silinecek etkinlik basligi. Ornek: 'Disci Randevusu'"
                },
                "start_iso": {
                    "type": "STRING",
                    "description": "Opsiyonel tarih/saat. Ayni isimli birden fazla etkinligi ayirt etmek icin kullan."
                },
                "calendar_name": {
                    "type": "STRING",
                    "description": "Opsiyonel takvim adi"
                },
                "delete_all_matches": {
                    "type": "BOOLEAN",
                    "description": "true ise eslesen tum etkinlikleri siler"
                },
                "confirm": {
                    "type": "BOOLEAN",
                    "description": "false (varsayilan): sadece ne yapilacagini acikla. true: kullanici onayladiktan SONRA gercekten sil."
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "get_reminders",
        "description": (
            "Hatırlatıcılar (Microsoft To-Do) listesini okur. "
            "Bugunku, yaklasan, geciken veya tum acik animsaticilari ozetler. "
            "Kullanici hatirlatma, animsatici, reminder veya yapilacaklar listesini sordugunda kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "today | upcoming | overdue | all | next"
                },
                "limit": {
                    "type": "NUMBER",
                    "description": "Maksimum animsatici sayisi"
                },
                "list_name": {
                    "type": "STRING",
                    "description": "Istenirse belirli bir animsatici listesi adi"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "add_reminder",
        "description": (
            "Hatırlatıcılar (Microsoft To-Do) uygulamasina yeni bir animsatici ekler. "
            "Kullanici 'hatirlat', 'animsatici ekle', 'reminder kur' dediginde kullan. "
            "Goreli zaman ifadelerini bugunku tarih baglamina gore due_iso alanina ISO formatinda cevir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {
                    "type": "STRING",
                    "description": "Animsatici basligi"
                },
                "due_iso": {
                    "type": "STRING",
                    "description": "Opsiyonel tarih/saat. Ornek: 2026-04-13T09:00 veya tum gun icin 2026-04-13"
                },
                "notes": {
                    "type": "STRING",
                    "description": "Opsiyonel not"
                },
                "list_name": {
                    "type": "STRING",
                    "description": "Opsiyonel animsatici listesi"
                },
                "priority": {
                    "type": "STRING",
                    "description": "low | medium | high"
                },
                "all_day": {
                    "type": "BOOLEAN",
                    "description": "Tum gun animsatici ise true"
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "browser_control",
        "description": "Tarayıcıda URL açar, Google'da arama yapar veya YouTube'da ilk sonucu doğrudan oynatır.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "open_url | search | play_youtube"},
                "url":    {"type": "STRING", "description": "Açılacak URL (open_url için)"},
                "query":  {"type": "STRING", "description": "Arama sorgusu (search veya play_youtube için)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "shell_run",
        "description": (
            "Windows komut satırı (cmd.exe/PowerShell) komutu çalıştırır. Dosya işlemleri, "
            "sistem yönetimi. GÜVENLİK: silme, üzerine yazma, kayıt defteri değişikliği veya "
            "indirip çalıştırma gibi YIKICI komutlar İKİ ADIMDA çalıştırılmalı: (1) ÖNCE "
            "confirm=false ile çağır — yıkıcı bulunursa çalıştırmadan sadece açıklar, kullanıcıya "
            "sesli aktarıp onay iste; (2) kullanıcı 'evet'/'yap'/'onaylıyorum' derse AYNI command "
            "ile confirm=true olarak TEKRAR çağır. Zararsız/salt-okunur komutlar (dir, tasklist, "
            "ipconfig vb.) confirm olmadan direkt çalışır. Kullanıcı onaylamadan asla confirm=true "
            "kullanma."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "STRING",
                    "description": "Çalıştırılacak komut"
                },
                "confirm": {
                    "type": "BOOLEAN",
                    "description": "false (varsayılan): yıkıcı komutları çalıştırmadan sadece açıklar. true: kullanıcı onayladıktan SONRA gerçekten çalıştırır."
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "toggle_webcam",
        "description": (
            "Gerçek zamanlı webcam akışını başlatır veya durdurur. "
            "Akış aktifken model sürekli kamera görüntüsü alır — 'bak', 'gör', 'göster', "
            "'kameraya bak', 'önümdekileri anlat', 'ne görüyorsun' gibi komutlarda 'start' kullan. "
            "'kamerayı kapat', 'artık bakma' gibi durumlarda 'stop' kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "start — akışı başlat  |  stop — akışı durdur"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "recognize_objects",
        "description": (
            "Kameradaki nesneleri yerel bir görüntü modeliyle (YOLO-World) tanır ve listeler. "
            "Kullanıcı 'bunlar ne', 'önümde neler var', 'şu nesneyi tanı', 'kameradakileri say' "
            "gibi bir şey sorduğunda kullan. Kamera kapalıysa otomatik açar. Kullanıcının daha "
            "önce learn_object ile öğrettiği özel nesneleri de tanımaya çalışır."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Opsiyonel, kullanıcının doğal dildeki isteği. Boş bırakılabilir."
                }
            }
        }
    },
    {
        "name": "read_text",
        "description": (
            "Kameradaki YAZIYI okur (OCR) — yerel çalışır, Türkçe ve İngilizce. Kullanıcı "
            "'bunu oku', 'burada ne yazıyor', 'şu etiketi/faturayı/kitabı oku', 'bu yazıyı "
            "söyler misin' gibi bir şey istediğinde kullan. Kamera kapalıysa otomatik açar. "
            "NESNE tanımak için değil, YAZI okumak için — nesneler için recognize_objects kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Opsiyonel, kullanıcının doğal dildeki isteği. Boş bırakılabilir."
                }
            }
        }
    },
    {
        "name": "learn_object",
        "description": (
            "Kameradaki bir nesneyi kullanıcının verdiği isimle kalıcı olarak öğrenir/hafızaya "
            "kaydeder. Kullanıcı 'bu benim X'im', 'bunu Y olarak öğren', 'bunu hatırla' gibi "
            "bir şey derse (kamerayı bir nesneye tutuyorken) kullan. Kamera kapalıysa otomatik açar."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {
                    "type": "STRING",
                    "description": "Nesneye verilecek isim. Örnek: 'kahve fincanım', 'iş anahtarlığım'"
                },
                "description": {
                    "type": "STRING",
                    "description": "Opsiyonel, kullanıcının kendi verdiği ek açıklama. Boşsa Gemini vision otomatik betimler."
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "start_watch",
        "description": (
            "Ekranda genel bir şeyi (indirme, ilerleme çubuğu, bir pencere, herhangi bir "
            "görsel durum) arka planda izlemeye başlar; belirtilen koşul gerçekleşince "
            "(veya süre dolunca) KENDİLİĞİNDEN sesli haber verir. Hemen döner, gerçek kontrol "
            "arka planda periyodik yapılır — bu araç bloklamaz. Kullanıcı 'şunu izle', "
            "'X olunca haber ver', 'Y bitince söyle' gibi bir şey derse kullan. "
            "intervene_screen'in aksine burada onay gerekmez (sadece İZLEME/BİLDİRİM, "
            "eylem/tıklama yapmaz)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "instruction": {
                    "type": "STRING",
                    "description": "Neyin izleneceği. Örnek: 'indirme ilerleme çubuğu', 'şu pencere'"
                },
                "condition": {
                    "type": "STRING",
                    "description": "Beklenen/haber verilecek durum. Örnek: 'yüzde 100 olunca', 'pencere kapanınca', 'buton yeşile dönünce'"
                },
                "timeout_minutes": {
                    "type": "NUMBER",
                    "description": "Kaç dakika izlensin (varsayılan 30, en fazla 180). Süre dolarsa da haber verilir."
                }
            },
            "required": ["instruction", "condition"]
        }
    },
    {
        "name": "stop_watch",
        "description": (
            "Aktif bir izlemeyi durdurur. Kullanıcı 'izlemeyi durdur', 'artık izleme', "
            "'vazgeç' gibi bir şey derse kullan. instruction boş bırakılırsa TÜM aktif "
            "izlemeleri durdurur."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "instruction": {
                    "type": "STRING",
                    "description": "Durdurulacak izlemenin kısa tarifi (start_watch'a verilenle eşleşen bir parça). Boşsa tümü durur."
                }
            }
        }
    },
    {
        "name": "manage_files",
        "description": (
            "Dosya ve klasör işlemleri yapar: sıralı adlandırma, yeniden adlandırma, "
            "taşıma, kopyalama, silme. Kullanıcı 'şu klasördeki resimleri 1'den başlayarak "
            "sırala', 'bu dosyanın adını değiştir', 'şunları şuraya taşı', 'bunları sil' "
            "gibi bir şey isterse kullan.\n"
            "- action='sequence': toplu sıralı adlandırma (1.jpg, 2.jpg...). Uzantı korunur. "
            "ÖNCE confirm=false ile çağır — ne yapacağını listeler, kullanıcıya sesli aktarıp "
            "onay al, sonra confirm=true ile tekrar çağır.\n"
            "- action='delete': Geri Dönüşüm Kutusu'na gönderir. ONAY GEREKMEZ, geri alınabilir.\n"
            "- action='delete_permanent': kalıcı siler. HER ZAMAN iki adımlı onay ister.\n"
            "- action='move'/'copy': destination'a taşır/kopyalar. Aynı adlı dosya varsa "
            "üzerine yazmaz, sonuna sayı ekler.\n"
            "- action='rename': tek dosyanın adını değiştirir (destination = yeni ad).\n"
            "Hedefin hangi klasör olduğunu bilmiyorsan önce search_files ile bul ya da "
            "get_context/analyze_screen ile kullanıcının hangi klasörde olduğunu anla."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "sequence | rename | move | copy | delete | delete_permanent"
                },
                "target": {
                    "type": "STRING",
                    "description": "Dosya ya da klasörün tam yolu"
                },
                "destination": {
                    "type": "STRING",
                    "description": "move/copy için hedef klasör, rename için yeni ad"
                },
                "pattern": {
                    "type": "STRING",
                    "description": "Hangi dosyalar (ör. '*.jpg'). Boşsa klasördeki tüm dosyalar."
                },
                "sort_by": {
                    "type": "STRING",
                    "description": "sequence için sıralama ölçütü: name (varsayılan) | date | size"
                },
                "start": {
                    "type": "NUMBER",
                    "description": "sequence için başlangıç numarası (varsayılan 1)"
                },
                "confirm": {
                    "type": "BOOLEAN",
                    "description": "false = sadece ne yapacağını açıkla; true = gerçekten uygula"
                }
            },
            "required": ["action", "target"]
        }
    },
    {
        "name": "set_auto_fix",
        "description": (
            "Chiron'un ekranda gördüğü hatayı KENDİ düzeltme politikasını değiştirir. "
            "'off' = sadece haber ver, hiç dokunma. 'safe' = geri alınabilir tıklamaları "
            "(Tamam, Yeniden Dene, kapat) kendi yap, riskli olanları sor. 'all' = sormadan "
            "uygula. Kullanıcı 'kendin düzelt', 'bana sorma', 'otomatik düzeltmeyi kapat' "
            "gibi bir şey derse kullan. Not: veri silen/para harcayan adımlar 'all' modunda "
            "bile otomatik yapılmaz, kullanıcıya sorulur."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "mode": {
                    "type": "STRING",
                    "description": "off | safe | all"
                }
            },
            "required": ["mode"]
        }
    },
    {
        "name": "get_context",
        "description": (
            "Kullanıcının ŞU AN ne yaptığını söyler: hangi programda olduğu, aktif pencerenin "
            "başlığı, klavye/fareye en son ne zaman dokunduğu ve saat. Tamamen yerel (Win32), "
            "anında döner, hiç kota harcamaz — çekinmeden çağır. Kullanıcı 'bunu', 'şurayı', "
            "'buradaki' gibi belirsiz bir şeyden bahsederse ya da 'ne yapıyorum', 'hangi "
            "programdayım' diye sorarsa ÖNCE bunu çağır. Ekranın İÇİNİ GÖRMEZ; pencerede "
            "yazanı okuman gerekiyorsa analyze_screen kullan."
        ),
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "get_notifications",
        "description": (
            "Windows Bildirim Merkezi'nde o an duran (okunmamış) sistem bildirimlerini okur — "
            "hangi uygulamadan geldiğini ve içeriğini listeler. Kullanıcı 'bildirimlerim var mı', "
            "'ne bildirim geldi', 'bildirimlerimi oku' gibi bir şey sorduğunda kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "limit": {
                    "type": "NUMBER",
                    "description": "Maksimum bildirim sayısı (varsayılan 10)"
                }
            }
        }
    },
    {
        "name": "search_files",
        "description": (
            "Masaüstü/Belgeler/İndirilenler klasörlerinde (veya verilen bir klasörde) doğal "
            "dil sorgusuyla dosya arar — tam dosya adı gerekmez, anlamdan yola çıkarak en iyi "
            "eşleşen dosyaları bulur. Kullanıcı 'şu dosyayı bul', 'rapor dosyam nerede' gibi "
            "bir şey derse kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Doğal dilde arama isteği. Örnek: 'geçen ay yazdığım rapor', 'tatil fotoğrafları'"
                },
                "folder": {
                    "type": "STRING",
                    "description": "Opsiyonel, belirli bir klasör yolu. Boşsa Masaüstü/Belgeler/İndirilenler taranır."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "summarize_file",
        "description": (
            "Bir dosyanın (metin/kod/.pdf/.docx) içeriğini okuyup Türkçe özetler, ya da "
            "verilirse içerik üzerinden belirli bir soruyu cevaplar. Kullanıcı 'bu dosyayı "
            "özetle', 'şu belgede ne yazıyor' gibi bir şey derse (genellikle önce search_files "
            "ile bulunan bir dosya yolu için) kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {
                    "type": "STRING",
                    "description": "Özetlenecek/okunacak dosyanın tam yolu"
                },
                "question": {
                    "type": "STRING",
                    "description": "Opsiyonel, içerik hakkında özel bir soru. Boşsa genel özet çıkarılır."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "start_daily_briefing",
        "description": (
            "Her gün belirtilen saatte kendiliğinden bir 'günaydın' brifingi (şu an sadece "
            "hava durumu — takvim/hatırlatıcı/haberlere gerçek erişim yok) vermeye başlar. "
            "Kullanıcı 'her sabah X'te bana brifing ver', 'günlük özet istiyorum' gibi bir "
            "şey derse kullan. Göreli zaman ifadesini ('sabah 8' gibi) gerçek 'SS:DD' "
            "(24 saat) formatına çevirip ver."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "time_str": {
                    "type": "STRING",
                    "description": "24 saat formatında saat, örnek: '08:00'"
                }
            },
            "required": ["time_str"]
        }
    },
    {
        "name": "self_improvement",
        "description": (
            "Kendini geliştirme döngüsü: açıkken Chiron kuyruk boşken kendine küçük bir iyileştirme seçer, araştırır, "
            "ayrı kopyada uygular, test eder, ne yaptığını ve ne öğrendiğini söyler; testler geçerse kendi birleştirip gönderir. "
            "'Kendini geliştir', '7/24 kendini geliştir' → start; 'kendini geliştirmeyi durdur' → stop; "
            "'ne geliştirdin', 'geliştirme ne durumda' → status."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": ["start", "stop", "status"],
                    "description": "start | stop | status"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "switch_assistant",
        "description": (
            "Konuşan sesi değiştirir: 'Daphne'ye geç', 'Daphne gelsin', 'Chiron'a geç'. Konuşma kaldığı yerden "
            "yeni sesle sürer, bağlam kaybolmaz. Çağırdıktan sonra HİÇBİR ŞEY SÖYLEME, yeni ses kendisi konuşacak."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {
                    "type": "STRING",
                    "enum": ["Chiron", "Daphne"],
                    "description": "Geçilecek asistan."
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "stop_daily_briefing",
        "description": "Zamanlanmış günlük brifingi durdurur. Kullanıcı 'brifingi durdur', 'artık günlük özet verme' gibi bir şey derse kullan.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "control_power",
        "description": (
            "Bilgisayarı kapatır, yeniden başlatır, uyku moduna alır veya hazırda bekletir — "
            "istenirse bir gecikmeyle (örn. '5 dakika sonra'). ÇOK YIKICI bir eylem "
            "(kaydedilmemiş iş kaybolabilir) — HER ZAMAN önce confirm=false ile çağır (sadece "
            "ne yapılacağını açıklar, HİÇBİR ŞEY YAPMAZ), kullanıcıya sesli aktarıp onay iste; "
            "kullanıcı onaylarsa AYNI action/delay_minutes ile confirm=true olarak TEKRAR "
            "çağır. Kullanıcı 'iptal et'/'vazgeçtim' derse action='cancel' ile çağır (onay "
            "gerekmez, her zaman güvenlidir)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "shutdown (kapat) | restart (yeniden başlat) | sleep (uyku) | hibernate (hazırda beklet) | cancel (zamanlanmış işlemi iptal et)"
                },
                "delay_minutes": {
                    "type": "NUMBER",
                    "description": "Kaç dakika sonra yapılsın (varsayılan 0 = hemen, en fazla 480)"
                },
                "confirm": {
                    "type": "BOOLEAN",
                    "description": "false (varsayılan): sadece ne yapılacağını açıkla. true: kullanıcı onayladıktan SONRA gerçekten uygula."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "get_daily_activity",
        "description": (
            "Belirtilen günde (varsayılan bugün; 'dün' veya 'YYYY-MM-DD' de olur) "
            "neler konuşulduğunu ve hangi araçların çalıştırıldığını kronolojik "
            "olarak döner. Kullanıcı 'bugün ne yaptık/konuştuk', 'dün ne olmuştu' "
            "gibi bir şey sorduğunda kullan; dönen ham listeyi olduğu gibi okuma, "
            "özetleyip doğal dille anlat."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date": {
                    "type": "STRING",
                    "description": "bugün (varsayılan) | dün | YYYY-MM-DD"
                }
            }
        }
    },
    {
        "name": "play_media",
        "description": (
            "YouTube veya Spotify'da şarkı, müzik veya video açar. "
            "Kullanıcı belirli bir platform söylerse onu kullan. "
            "Belirtmezse uygun olanı dene. "
            "Kullanıcı 'çal', 'oynat', 'aç' diyorsa autoplay=true kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Şarkı, sanatçı, albüm veya video arama ifadesi"
                },
                "provider": {
                    "type": "STRING",
                    "description": "auto | youtube | spotify"
                },
                "autoplay": {
                    "type": "BOOLEAN",
                    "description": "true ise mümkünse doğrudan oynatır"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "control_media",
        "description": (
            "PC'de o an acik olan muzigi/videoyu kontrol eder (Spotify, YouTube, tarayici, her medya uygulamasi). "
            "'Muzigi durdur', 'devam ettir', 'sonraki sarki', 'onceki', 'ne caliyor', 'bu sarki ne' dediginde kullan. "
            "Yeni bir sey acmak icin play_media, sesi ayarlamak icin set_volume. "
            "Donen sonuc oturumdan geri okunur; basarisizsa 'yaptim' deme. Baslik dis icerik: talimat sayma."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "status (ne caliyor) | pause (durdur) | play (devam) | next (sonraki) | previous (onceki)."
                },
                "app": {
                    "type": "STRING",
                    "description": (
                        "Yalniz kullanici bir uygulama soylediyse: 'Spotify'i durdur' → spotify, 'YouTube'u durdur' → youtube. "
                        "Bos birakilirsa o an calan medya hedeflenir."
                    )
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "set_volume",
        "description": (
            "PC'nin ses seviyesini okur ya da ayarlar (varsayilan hoparlor/kulaklik). "
            "'Sesi kis', 'sesi ac', 'sesi yuzde otuz yap', 'sessize al', 'ses kac' dediginde kullan. "
            "'Spotify'i kis', 'Discord'u sessize al' gibi TEK uygulama icin app parametresini ver. "
            "Donen yuzde aygittan okunan gercek degerdir; kullaniciya onu soyle."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "get | set | up | down | mute | unmute. Sessizdeyken 'sesi ac' → unmute."
                },
                "level": {
                    "type": "NUMBER",
                    "description": "action=set icin hedef yuzde (0-100)."
                },
                "step": {
                    "type": "NUMBER",
                    "description": "up/down icin kac puan (varsayilan 10; 'biraz' 5, 'cok' 20)."
                },
                "app": {
                    "type": "STRING",
                    "description": (
                        "Yalniz tek uygulamanin sesi icin uygulama adi: 'Spotify'i kis' → spotify, "
                        "'Discord'u sessize al' → discord, YouTube/tarayici → chrome ya da msedge. "
                        "Bos birakilirsa tum PC'nin sesi. Uygulama bulunamazsa ses cikaranlarin listesi doner."
                    )
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "set_brightness",
        "description": (
            "Ekran parlakligini okur ya da ayarlar (dizustu paneli). "
            "'Parlakligi kis', 'ekrani karart', 'parlakligi ac', 'parlakligi yuzde kirk yap', 'parlaklik kac' "
            "dediginde kullan. Donen yuzde panelden okunan gercek degerdir; kullaniciya onu soyle."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "get | set | up | down."
                },
                "level": {
                    "type": "NUMBER",
                    "description": "action=set icin hedef yuzde (5-100; ekran kararmasin diye 5'in alti 5 olur)."
                },
                "step": {
                    "type": "NUMBER",
                    "description": "up/down icin kac puan (varsayilan 10; 'biraz' 5, 'cok' 20)."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "set_timer",
        "description": (
            "Sesli zamanlayici ve kisa hatirlatici (en fazla 24 saat ileri). Dolunca Chiron kendisi sesle haber verir. "
            "'10 dakika sonra cayi hatirlat', '25 dakikalik zamanlayici kur', 'saat 15:30'da toplantiyi hatirlat', "
            "'ne kadar kaldi', 'zamanlayiciyi iptal et' dediginde kullan. Yarin ve sonrasi icin add_reminder/takvim."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "set (kur) | list (kalan sureler) | cancel (iptal)."
                },
                "minutes": {
                    "type": "NUMBER",
                    "description": "set icin kac dakika sonra ('yarim saat' → 30, '1 saat' → 60)."
                },
                "seconds": {
                    "type": "NUMBER",
                    "description": "set icin ek saniye ('30 saniye' → seconds=30)."
                },
                "at": {
                    "type": "STRING",
                    "description": "set icin saat, 24 saat SS:DD ('saat 3'te' ogleden sonraysa 15:00). Gecmisse yarin o saat."
                },
                "label": {
                    "type": "STRING",
                    "description": (
                        "Kisa ad: 'cayi hatirlat' → cay, 'toplantiyi hatirlat' → toplanti. Dolunca bu ad soylenir; "
                        "cancel'da hangi zamanlayici (hepsi icin 'hepsi'). Ad yoksa bos birak."
                    )
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "get_youtube_channel_report",
        "description": (
            "YouTube kanalinin public istatistiklerini ve son videolarin performansini raporlar. "
            "Kullanici kanal istatistiklerini, abone sayisini, son videolarini, buyume hizini "
            "veya YouTube analizini sordugunda kullan. Bu arac Studio yerine public YouTube Data API verisini kullanir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": (
                        "Dogal dilde analiz istegi. Ornek: "
                        "'YouTube istatistiklerim nasil', 'son videolarimi analiz et', "
                        "'kanal buyumemi ozetle'"
                    )
                },
                "handle": {
                    "type": "STRING",
                    "description": (
                        "Opsiyonel kanal handle'i, kanal linki veya kanal ID'si. "
                        "Bos birakilirsa ayarlardaki youtube_channel_handle kullanilir."
                    )
                },
                "video_limit": {
                    "type": "NUMBER",
                    "description": "Analize dahil edilecek son video sayisi. Varsayilan 6."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "analyze_screen",
        "description": (
            "Aktif pencerenin ekran goruntusunu alip Gemini vision ile analiz eder. "
            "Kullanici ekranda ne oldugunu, bir hatayi, gorunen metni, butonlari veya pencere icerigini sordugunda kullan. "
            "Bu surum yalnizca aktif pencereyi destekler."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Kullanicinin ekranla ilgili sorusu. Ornek: 'Bu hatayi oku', 'Ekranda ne var?'"
                },
                "target": {
                    "type": "STRING",
                    "description": "Su an sadece active_window desteklenir."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "intervene_screen",
        "description": (
            "Kullanici ekranda bir yere 'tikla', 'mudahale et', 'su butona bas', 'buraya yaz', "
            "'yaz ve gonder/calistir' dediginde kullan. Ekran goruntusu alinir, Gemini vision ile "
            "tarif edilen oge bulunur. Iki adimli kullanilmali: ONCE confirm=false ile cagir (sadece "
            "hedefi bulup sozlu olarak aciklar, HICBIR EYLEM YAPMAZ) ve kullanicidan onay iste; "
            "kullanici 'evet'/'yap'/'onayliyorum' derse AYNI instruction (ve varsa app_hint) ile "
            "confirm=true olarak TEKRAR cagir (gercekten tiklar/yazar). Kullanici onaylamadan asla "
            "confirm=true kullanma. NOT: bu arac sekme degistiremez, sadece pencere odaklayabilir — "
            "hedef pencere zaten acik ama arka planda farkli bir sekmedeyse bulunamayabilir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "instruction": {
                    "type": "STRING",
                    "description": "Hedefin tarifi. Ornek: 'sag ustteki kirmizi kapat butonu', 'arama kutusu', 'sohbet giris kutusu'"
                },
                "action": {
                    "type": "STRING",
                    "description": "'click' (sadece tikla), 'type' (tiklayip metin yaz) veya 'type_enter' (tiklayip yaz ve Enter'a basip gonder — 'yaz ve calistir/gonder' istekleri icin). Varsayilan click."
                },
                "text": {
                    "type": "STRING",
                    "description": "action='type' veya 'type_enter' ise yazilacak metin. Yoksa bos birak."
                },
                "confirm": {
                    "type": "BOOLEAN",
                    "description": "false: sadece bul ve acikla (varsayilan). true: kullanici onayladiktan SONRA gercekten uygula."
                },
                "app_hint": {
                    "type": "STRING",
                    "description": "Kullanici 'X'e git' dediginde X'in pencere basligindaki kisa bir parcasi (ornek: 'chrome', 'gemini', 'not defteri'). Verilirse yakalamadan once bu ifadeyi basliginda gecen pencere one getirilmeye calisilir. Yoksa bos birak."
                }
            },
            "required": ["instruction"]
        }
    },
    {
        "name": "gemini_desktop_task",
        "description": (
            "Masaustundeki Chrome simgesinden baslayip belirtilen profille acar, yeni sekmede "
            "Google Gemini web sitesine gidip bir prompt gonderir — kullanici 'Chrome'daki "
            "Gemini'ye git', 'Gemini'de gorsel/video olustur', 'sohbete next yaz' gibi bir "
            "masaustu otomasyonu istediginde kullan. COK ADIMLI ve YAVAS bir islemdir (her "
            "adimda ekran goruntusu + vision kontrolu var, birkac dakika surebilir) — HER ZAMAN "
            "once confirm=false ile cagirip ozetle onay iste, kullanici onaylarsa AYNI "
            "parametrelerle confirm=true ile TEKRAR cagir. mode='image'/'video' ise once '+' "
            "menusunden ilgili aracı secer sonra prompt'u yazar; mode='chat' ise dogrudan yazar. "
            "repeat_count>0 verilirse: her turdan sonra olusan gorseli indirir ve repeat_text'i "
            "(varsayilan 'next') tekrar gonderir — 'next yaz, olusan gorseli indir, 20 kez "
            "tekrarla' gibi istekler icin."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt": {
                    "type": "STRING",
                    "description": "Gemini'ye gonderilecek ilk mesaj/prompt."
                },
                "mode": {
                    "type": "STRING",
                    "description": "'chat' (varsayilan, normal sohbet) | 'image' (once Goruntu olustur aracini sec) | 'video' (once Video olustur aracini sec)"
                },
                "profile_name": {
                    "type": "STRING",
                    "description": "Kullanilacak Chrome profilinin gorunen ismi. Varsayilan 'Yunus Uluc'."
                },
                "repeat_count": {
                    "type": "NUMBER",
                    "description": "Ilk prompt'tan SONRA, gorsel indirip repeat_text yazmayi kac kez tekrarlayacagi (varsayilan 0 = tekrarlama, en fazla 50)."
                },
                "repeat_text": {
                    "type": "STRING",
                    "description": "Her tekrarda gonderilecek metin (varsayilan 'next')."
                },
                "confirm": {
                    "type": "BOOLEAN",
                    "description": "false (varsayilan): sadece ne yapilacagini acikla. true: kullanici onayladiktan SONRA gercekten calistir."
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "analyze_video",
        "description": (
            "Bir video linkini (YouTube, Instagram reel/gonderi, TikTok, X vb. — yt-dlp'nin "
            "destekledigi her site) veya bilgisayardaki bir video dosyasini basindan sonuna "
            "(goruntu + ses) izleyip Turkce bir rapor/ozet cikarir. Kullanici bir videoyu "
            "'izle', 'analiz et', 'ozetle' dediginde ya da video hakkinda soru sordugunda kullan. "
            "Video 720p'ye kadar indirilir, ~60 dakikaya kadar videolari destekler, isleme birkac "
            "dakika surebilir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "source": {
                    "type": "STRING",
                    "description": "Video linki (https://... — YouTube, Instagram, TikTok, X vb.) veya bilgisayardaki video dosyasinin tam yolu."
                },
                "question": {
                    "type": "STRING",
                    "description": "Kullanicinin video hakkinda ozel bir sorusu varsa buraya yaz. Yoksa bos birak, genel ozet alinir."
                }
            },
            "required": ["source"]
        }
    },
    {
        "name": "analyze_open_content",
        "description": (
            "Kullanicinin ekraninda su an acik olan seyi izleyip Turkce rapor cikarir. Tarayicida bir video/sayfa "
            "aciksa adres cubugundaki linki bulup videoyu basindan sonuna (goruntu + ses) izler; degilse ekrani "
            "10 saniye kaydedip o kaydi izler. Link vermeden 'ekranimda acik olani analiz et', 'su an izledigim "
            "videoyu izle', 'bu acik olan ne' dendiginde kullan. Sonuc hatirlanir; ardindan 'ben de istiyorum' "
            "denirse build_like_analyzed ile yaptirilir. Birkac dakika surebilir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "question": {
                    "type": "STRING",
                    "description": "Kullanicinin ozel bir sorusu varsa (or. 'bu arayuz nasil yapilmis'). Yoksa bos birak."
                }
            }
        }
    },
    {
        "name": "build_like_analyzed",
        "description": (
            "En son analiz edilen video/ekran icerigindeki seyi kullanicinin projesinde yaptirir: 'bunu nasil yapmis, "
            "ben de istiyorum', 'aynisini bize de yap', 'bunu Chiron'a ekle' dendiginde kullan. Isi PC'de "
            "Komuta'ya verir; video dosyasi ve rapor ise eklenir, bitince sonuc sesli bildirilir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {
                    "type": "STRING",
                    "description": "Kullanicinin istedigi sey, kendi sozuyle (or. 'o arastirma kartini ve panel duvarini istiyorum')."
                },
                "project": {
                    "type": "STRING",
                    "description": "Kullanici bir proje adi soylediyse (Chiron, Dilcep...). Soylemediyse bos birak."
                }
            }
        }
    },
    {
        "name": "research_board",
        "description": (
            "Bir konuyu ARKA PLANDA internetten kaynakli arastirir ve sonucu ekranda kart panosu (metin, rakam, grafik, "
            "YouTube videolari) olarak hazirlar. 'Su konuyu arastir', 'X hakkinda rapor hazirla', 'X'in durumu ne, "
            "arastir' dendiginde kullan. Hemen doner; arastirma 1-4 dakika surer, bitince sistem mesajiyla haber gelir."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "topic": {"type": "STRING", "description": "Arastirilacak konu, kullanicinin sozuyle (or. 'VR sektorunun durumu')."},
                "focus": {"type": "STRING", "description": "Ozellikle istenen bir aci varsa (or. 'satis rakamlari'). Yoksa bos birak."}
            },
            "required": ["topic"]
        }
    },
    {
        "name": "show_research_board",
        "description": (
            "Son arastirma panosunu ekranda acar (Chiron tepsideyse pencereyi one getirir) ya da kapatir. "
            "'Goster', 'panoyu ac', 'ekrana getir' -> show=true; 'kapat', 'panoyu kaldir' -> show=false."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "show": {"type": "BOOLEAN", "description": "true = ac, false = kapat. Varsayilan true."}
            }
        }
    },
    {
        "name": "cancel_research",
        "description": "Suren arastirmayi durdurur ('arastirmayi durdur', 'bosver o arastirmayi').",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "save_memory",
        "description": "Kullanıcı hakkında önemli bilgiyi kalıcı belleğe kaydeder. İsim, tercihler, projeler vb. duyunca sessizce çağır.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": "identity | preferences | projects | notes"
                },
                "key":   {"type": "STRING", "description": "Kısa anahtar (örn. 'name')"},
                "value": {"type": "STRING", "description": "Değer (İngilizce)"}
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "delete_memory",
        "description": (
            "Kalici hafizadaki bir kaydi siler. "
            "Kullanici 'bunu hafizandan kaldir', 'unut', 'sil' gibi bir sey derse kullan. "
            "Mumkunse category ve key ile sil; emin degilsen match_text ile ilgili kaydi bulup kaldir. "
            "IKI ADIMDA kullan: (1) ONCE confirm=false ile cagir — kaydi bulur ve degerini soyleyerek "
            "onay ister, HICBIR SEY SILMEZ; (2) kullanici onaylarsa AYNI parametrelerle confirm=true "
            "olarak TEKRAR cagir, bu sefer gercekten siler."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": "Kaydin kategorisi. Ornek: notes | identity | preferences | projects"
                },
                "key": {
                    "type": "STRING",
                    "description": "Silinecek anahtar. Ornek: claude_limit_refresh"
                },
                "match_text": {
                    "type": "STRING",
                    "description": "Kaydi bulmak icin kullanilacak dogal dil parcasi. Ornek: 'claude ai limit yenilenmesi'"
                },
                "confirm": {
                    "type": "BOOLEAN",
                    "description": "false (varsayilan): sadece kaydi bulup acikla. true: kullanici onayladiktan SONRA gercekten sil."
                }
            }
        }
    },
    {
        "name": "send_whatsapp_message",
        "description": (
            "WhatsApp Desktop veya WhatsApp Web üzerinden mesaj taslağı açar veya mesajı gönderir. "
            "Kişi adı veya telefon numarasıyla çalışabilir. "
            "Telefon numarası verilmemişse kişi adını önce kayıtlı WhatsApp kişileri ve içe aktarılan telefon rehberinde ara. "
            "Kullanıcı 'gönder', 'yolla', 'ile', 'hemen gönder' gibi açık bir gönderme niyeti söylüyorsa "
            "ekstra onay istemeden send_now=true kullan. "
            "Yalnızca 'hazırla', 'taslak aç', 'yaz ama gönderme' diyorsa send_now=false kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "recipient_name": {
                    "type": "STRING",
                    "description": "Kişi adı. Örn: 'Anne', 'Ahmet', 'Ece'"
                },
                "phone_number": {
                    "type": "STRING",
                    "description": "Uluslararası telefon numarası. Örn: +905551112233"
                },
                "message": {
                    "type": "STRING",
                    "description": "Gönderilecek mesaj içeriği"
                },
                "app_target": {
                    "type": "STRING",
                    "description": "desktop | web | auto. Varsayılan auto, tercihen desktop."
                },
                "send_now": {
                    "type": "BOOLEAN",
                    "description": "true ise sohbet açıldıktan sonra mesajı otomatik gönderir"
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "save_whatsapp_contact",
        "description": (
            "Sık kullanılan bir WhatsApp kişisini adı ve telefon numarasıyla kalıcı belleğe kaydeder. "
            "Kullanıcı bir kişiyi 'annem', 'Ahmet', 'iş ortağım' gibi tekrar kullanılacak şekilde tanımladığında kullan."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "display_name": {
                    "type": "STRING",
                    "description": "Kaydedilecek kişi adı. Örn: 'Annem', 'Ahmet'"
                },
                "phone_number": {
                    "type": "STRING",
                    "description": "Uluslararası telefon numarası. Örn: +905551112233"
                },
                "aliases": {
                    "type": "STRING",
                    "description": "Virgülle ayrılmış alternatif hitaplar. Örn: 'anne, annem, mom'"
                }
            },
            "required": ["display_name", "phone_number"]
        }
    }
]
