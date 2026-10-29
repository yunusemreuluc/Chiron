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
            "Bir YouTube linkini veya bilgisayardaki bir video dosyasini basindan sonuna "
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
                    "description": "YouTube linki (https://...) veya bilgisayardaki video dosyasinin tam yolu."
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
