# JARVIS MASTER V1 — BAŞLATMA DOSYASI
# JARVIS MASTER V1 — Startup Script

import sys
import os
import time
import threading

# Proje klasörünü path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("JARVIS MASTER V1 — Başlatılıyor...")
print("=" * 60)

# Tüm modülleri import et
try:
    import jarvis_master as jm
    print("[OK] jarvis_master modulu yuklendi")
except Exception as e:
    print(f"[HATA] jarvis_master yuklenemedi: {e}")
    sys.exit(1)

# Motoru baslat
motor = jm.motor()
katalog = motor.tool_catalog()
print(f"[OK] Arac kayit sistemi: {len(katalog)} arac")

# Durum raporu
durum = motor.status()
print(f"[OK] Motor durumu: {durum}")

print("\n" + "=" * 60)
print("JARVIS MASTER V1 hazir. Komut bekliyor...")
print("=" * 60)

# Ana dongu
try:
    while True:
        try:
            komut = input("\nJARVIS> ").strip()
        except EOFError:
            break
        if not komut:
            continue
        if komut.lower() in ("cikis", "exit", "quit", "kapat"):
            print("JARVIS kapatiliyor...")
            break
        if komut.lower() in ("yardim", "help"):
            print("""
Kullanilabilir komutlar:
  - sistem durumu        : Sistem durumu raporu
  - pencere listesi      : Acik pencereleri listeler
  - dosya olustur X.txt  : Proje icinde dosya olusturur
  - arac listesi         : Tum araclari listeler
  - cikis                : JARVIS'i kapatir
""")
            continue
        if komut.lower() == "sistem durumu":
            sonuc = jm.cevapla("sistem durumu", onay_callback=lambda *a: True)
            print(f"  Durum: {sonuc.get('durum')}")
            for a in sonuc.get("adimlar", []):
                print(f"  - {a.get('tool')}: {'OK' if a.get('ok') else 'HATA'}")
        elif komut.lower() == "arac listesi":
            for t in katalog:
                print(f"  - {t['name']} [{t.get('risk', '?')}]")
        elif komut.lower().startswith("pencere listesi"):
            import jarvis_master_bilgisayar as bm
            s = bm.pencereleri_listele()
            if s.get("ok"):
                for p in s.get("pencereler", [])[:20]:
                    print(f"  - {p.get('baslik', 'Bilinmeyen')}")
            else:
                print(f"  Hata: {s.get('hata')}")
        elif komut.lower().startswith("dosya olustur"):
            parcalar = komut.split(" ", 2)
            if len(parcalar) >= 2:
                dosya_adi = parcalar[1]
                icerik = parcalar[2] if len(parcalar) >= 3 else ""
                import jarvis_master_bilgisayar as bm
                s = bm.dosya_olustur(dosya_adi=dosya_adi, icerik=icerik)
                print(f"  Sonuc: {s}")
            else:
                print("  Kullanim: dosya olustur dosya_adi.txt [icerik]")
        else:
            # AI planlayici ile calistir
            print("  Isleniyor...")
            sonuc = jm.cevapla(komut, onay_callback=lambda *a: True)
            print(f"  Durum: {sonuc.get('durum')}")
            if sonuc.get("hata"):
                print(f"  Hata: {sonuc['hata']}")
            for a in sonuc.get("adimlar", []):
                print(f"  - {a.get('tool')}: {'OK' if a.get('ok') else 'HATA'}")

except KeyboardInterrupt:
    print("\nJARVIS kapatiliyor (Kullanici ile durduruldu)...")

print("\nJARVIS MASTER V1 kapatildi.")
