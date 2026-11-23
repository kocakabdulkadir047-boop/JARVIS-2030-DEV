# JARVIS MASTER V1 — KURULUM VE KULLANIM DOKÜMANI
# Installation and Usage Documentation

## SISTEM GEREKSINIMLERI

- İşletim Sistemi: Windows 10 / Windows 11
- Python: 3.12 (tools/py312/python.exe)
- RAM: Minimum 8 GB, önerilen 16 GB
- İşlemci: i5 veya eşdeğer
- Ekran Kartı: GTX 1650 veya eşdeğer (Unity için)

## KURULUM

1. Proje klasörünü indirin veya kopyalayın:
   `C:\Users\Koçak\Downloads\jatvis\`

2. Python 3.12'yi kurun (veya mevcut `tools/py312/python.exe` kullanın)

3. Opsiyonel bağımlılıkları yükleyin:
   ```
   pip install psutil pyinstaller
   ```

4. JARVIS'i başlatın:
   ```
   cd C:\Users\Koçak\Downloads\jatvis
   tools\py312\python.exe -X utf8 jarvis_baslat.py
   ```

## KULLANIM

### Temel Komutlar

| Komut | Açıklama |
|-------|----------|
| `sistem durumu` | Sistem durumu raporu |
| `pencere listesi` | Açık pencereleri listeler |
| `dosya olustur X.txt` | Proje klasöründe dosya oluşturur |
| `arac listesi` | Tüm kayıtlı araçları listeler |
| `yardim` | Komut listesini gösterir |
| `cikis` | JARVIS'i kapatır |

### GUI Kullanımı

JARVIS GUI'sini başlatmak için:
```
tools\py312\python.exe -X utf8 jarvis_master_gui.py
```

GUI panelleri:
- Ana Sayfa: Sohbet ve görev paneli
- Bilgisayar Otomasyonu: Pencere, uygulama, dosya işlemleri
- Yazılım Fabrikası: Proje analizi, kod üretimi, test
- Unity Geliştirme: Unity projesi analizi, build
- Roblox Geliştirme: Roblox proje analizi, Luau script
- Ses: Mikrofon, TTS kontrolleri
- Görsel Zeka: Ekran analizi, karşılaştırma
- Ayarlar: Sistem yapılandırması

## GÜVENLIK KURALLARI

1. Dosya silme ve üzerine yazma için kullanıcı onayı gereklidir
2. Program kurma/kaldırma için kullanıcı onayı gereklidir
3. Proje klasörü dışına dosya yazma engellenir
4. Harici ağ işlemleri için kullanıcı onayı gereklidir
5. Kullanıcı durdurduğunda yeni işlem başlatılmaz

## MODÜLLER

| Modül | Açıklama |
|-------|----------|
| jarvis_master.py | Merkezi kontrol motoru |
| jarvis_master_bilgisayar.py | Bilgisayar otomasyonu (Aşama 14) |
| jarvis_master_masaustu.py | Masaüstü otomasyonu (Aşama 14) |
| jarvis_master_gorev_kuyrugu.py | Görev kuyruğu yönetimi |
| jarvis_master_gelistirme_plani.py | Geliştirme planı (Aşama 15) |
| jarvis_master_kod_dongusu.py | Kod döngüsü motoru |
| jarvis_master_otonom_gelistirme.py | Otonom geliştirme (Aşama 15) |
| jarvis_master_otonom_test.py | Otonom test (Aşama 15) |
| jarvis_master_yazilim.py | Yazılım fabrika entegrasyonu |
| jarvis_master_unity.py | Unity geliştirme altyapısı (Aşama 16) |
| jarvis_master_unity_build.py | Unity Windows EXE build (Aşama 10) |
| jarvis_master_unity_bridge.py | Unity Editor köprüsü |
| jarvis_master_roblox.py | Roblox geliştirme altyapısı (Aşama 17) |
| jarvis_master_roblox_bridge.py | Roblox köprüsü |
| jarvis_master_roblox_build.py | Roblox build |
| jarvis_master_roblox_factory.py | Roblox factory |
| jarvis_master_roblox_studio.py | Roblox Studio entegrasyonu |
| jarvis_master_roblox_test.py | Roblox test |
| jarvis_master_ses.py | Ses modülü (Aşama 12) |
| jarvis_master_stt.py | Konuşma tanıma (Aşama 12) |
| jarvis_master_tts.py | Metin-okuma (Aşama 12) |
| jarvis_master_gorsel_zeka.py | Görsel zeka (Aşama 13) |
| jarvis_master_gorsel_karsilastirma.py | Görsel karşılaştırma (Aşama 13) |
| jarvis_master_proje_analiz.py | Proje analizi |
| jarvis_master_durum.py | Durum takibi |
| jarvis_master_gui.py | GUI arayüzü |
| jarvis_master_hafiza.py | Kalıcı hafıza |
| jarvis_master_onay.py | Kullanıcı onay akışı |
| jarvis_master_gunluk.py | Kayıt sistemi |

## YEDEKLEME

Yedek klasörü: `C:\Users\Koçak\Downloads\jatvis_backup_*_stage*`

## BİLINEN SORUNLAR

Bkz. ASAMA_20_BILINEN_SORUNLAR.md

## SÜRÜM

JARVIS MASTER V1 — Final Build
Tarih: 10 Kasım 2026
