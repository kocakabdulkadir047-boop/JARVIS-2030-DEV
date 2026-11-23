# JARVIS MASTER V1 — BİLINEN SORUNLAR
# Known Issues List

Tarih: 10 Kasım 2026
Sürüm: V1 Final Build

## KRİTİK SORUNLAR

### 1. Unity EXE Build - batchmode -executeMethod çalışmıyor
**Açıklama:** Unity Editor batchmode modunda `-executeMethod=JarvisBuild.Build` çalıştırıldığında Editor başlıyor, derleme yapıyor ama EXE üretmiyor. Return code 0 dönüyor ancak EXE dosyası oluşmuyor.
**Neden:** Unity Personal lisansının batchmode'da Hub lisans istemcisiyle iletişim kuramaması (`Access token is unavailable` hatası).
**Geçici çözüm:** Unity Editor'ı interaktif modda açın ve "JARVIS/BuildInkGame" menü öğesini kullanın.
**Öncelik:** Yüksek

### 2. psutil modülü eksik
**Açıklama:** `uygulamalari_listele()` ve `unity_editor_durumu()` gibi fonksiyonlar psutil gerektiriyor ancak psutil yüklü değil.
**Neden:** psutil opsiyonel bir bağımlılıktır ve kurulu değil.
**Geçici çözüm:** `pip install psutil` komutu ile kurun.
**Öncelik:** Orta

### 3. gorev_durumu instance metodu eksik
**Açıklama:** `GorevKuyrugu` sınıfının instance'ında `gorev_durumu` metodu yok; sadece modül seviyesinde `gorev_durumu()` fonksiyonu var.
**Neden:** Kod düzenleme sonucu instance metodu kaldırılmış.
**Geçici çözüm:** `jarvis_master_gorev_kuyrugu.gorev_durumu(gid)` şeklinde modül seviyesinden çağırın.
**Öncelik:** Düşük

## GÜVENLIK SORUNSALLIKLARI

1. **Dosya erişim sınırı:** Proje klasörü dışına dosya yazma engelleniyor (güvenlik özelliği)
2. **Kullanıcı onayı:** "confirm" risk etiketli araçlar onay_callback ile çalışıyor
3. **Yayınlama:** Unity/Roblox yayınlama işlemleri kullanıcı onayı gerektiriyor (yapılmadı)

## PERFORMANS SINIRLAMALARI

1. **Büyük klasör taraması:** `klasor_testi()` çok büyük dizinlerde yavaş yanıt verebilir
2. **GUI donma:** tkinter tabanlı GUI, uzun işlemler sırasında donabilir (ayrı thread kullanılmıyor)
3. **Bellek:** 16 GB RAM sistemde ~1 GB (Roblox Studio) kadar tüketim gözlemlenmiştir

## TEST EDILEMEYEN ÖZELLİKLER

1. Unity Play Mode testi (Editor GUI gerektirir)
2. Unity EXE açılış testi (EXE üretilmedi)
3. Roblox Play Test (Studio GUI gerektirir)
4. Roblox Output hata analizi (Studio çalışmıyor)
5. TTS (Gemini API anahtarı gerektirir)
6. STT (Mikrofon donanımı gerektirir)
7. Görsel zeka (API anahtarı gerektirir)
8. GUI görsel testi (headless ortamda test edilemedi)

## DÜZELTME GEÇMİŞİ

Aşama 20'de yapılmayan düzeltmeler (ileride yapılması gerekenler):
1. `gorev_durumu` instance metodunu `GorevKuyrugu` sınıfına ekle
2. psutil kurulum talimatını KULLANIM_DOKUMANI'ye ekle
3. Unity batchmode -executeMethod alternatif yöntemini araştır

## YEDEK KLASÖRÜ

C:\Users\Koçak\Downloads\jatvis_backup_20261110_004423_stage20_final (383 dosya)

## İLETİŞİM

Sorun bildirimleri için KULLANIM_DOKUMANI.md dosyasını inceleyin.
