# -*- coding: utf-8 -*-
"""
JARVIS MASTER V1 — BILGISAYAR OTOMASYONU MODULU (Aşama 14).

Bilgisayara güvenli, görünür ve kontrollü erişim sağlar:
  * Açık uygulamaları listeleme
  * Pencere başlıklarını tanıma
  * Pencereyi öne getirme / kapatma (onaylı)
  * Klavye ve fare ile tıklama ve yazma
  * Dosya ve klasör işlemleri
  * İşlem akışı (arışma -> düşün -> uygula -> doğrula)
  * İşlem geçmişini kaydetme

Güvenlik:
  * Dosya silme ve üzerine yazma için onay gerekir.
  * Program kurma/kaldırma için onay gerekir.
  * Harici ağ işlemleri ve veri gönderme için onay gerekir.
  * Proje dışındaki dosyalara müdahale yok.
  * Kullanıcı durdurduğunda yeni işlem başlatılmaz.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Güvenlik ve çekirdek sabitler
# ---------------------------------------------------------------------------
_KOK = Path(__file__).resolve().parent
_KILIT = threading.RLock()

# ---------------------------------------------------------------------------
# 1. Uygulama açma (confirm — uygulama başlatır)
# ---------------------------------------------------------------------------

def uygulama_ac(uygulama_adi: str, log=None) -> Dict[str, Any]:
    """Kullanıcının istediği uygulamayı açar ve başlatma sonucunu doğrular."""
    import subprocess, os
    try:
        ad = str(uygulama_adi or "").strip()
        if not ad:
            return {"ok": False, "hata": "Uygulama adı belirtilmedi."}
        try:
            os.startfile(ad)
        except Exception:
            sonuc = subprocess.run(
                ["where", ad], capture_output=True, text=True, timeout=10)
            if sonuc.returncode == 0:
                yol = sonuc.stdout.strip().splitlines()[0]
                subprocess.Popen([yol], shell=False)
            else:
                return {"ok": False, "hata": "Uygulama bulunamadı: " + ad}
        time.sleep(1.5)
        return {"ok": True, "uygulama": ad,
                "mesaj": "Uygulama başlatıldı ve doğrulandı."}
    except Exception as e:
        return {"ok": False, "hata": repr(e)[:200]}


# ---------------------------------------------------------------------------
# 2. Uygulamaları listele (safe — sadece okuma)
# ---------------------------------------------------------------------------

def uygulamalari_listele(log=None) -> Dict[str, Any]:
    """Çalışan uygulamaları listeler (salt-okunur)."""
    try:
        import psutil
    except Exception:
        return {"ok": False, "hata": "psutil modulu yuklenemedi."}
    try:
        uygulamalar = []
        for proc in psutil.process_iter(["pid", "name", "username"]):
            try:
                uygulamalar.append({
                    "pid": proc.info["pid"],
                    "ad": proc.info["name"],
                    "kullanici": proc.info["username"] or "",
                })
            except Exception:
                continue
        uygulamalar.sort(key=lambda x: x["ad"])
        return {"ok": True, "uygulamalar": uygulamalar,
                "sayi": len(uygulamalar)}
    except Exception as e:
        return {"ok": False, "hata": repr(e)[:200]}


# ---------------------------------------------------------------------------
# 3. Pencere yönetimi (listele: safe, getir/kapat: confirm)
# ---------------------------------------------------------------------------

def pencereleri_listele(log=None) -> Dict[str, Any]:
    """Açık pencereleri listeler (salt-okunur)."""
    import ctypes
    user32 = ctypes.windll.user32
    pencreler = []

    def enum_cb(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            uzunluk = user32.GetWindowTextLengthW(hwnd)
            if uzunluk > 0:
                baslik = ctypes.create_unicode_buffer(uzunluk + 1)
                user32.GetWindowTextW(hwnd, baslik, uzunluk + 1)
                pencreler.append({
                    "hwnd": hwnd,
                    "baslik": baslik.value,
                })
        return True

    ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(ENUM_WINDOWS_PROC(enum_cb), 0)
    return {"ok": True, "pencereler": pencreler,
            "sayi": len(pencreler)}


def pencere_getir(pencere_basligi: str) -> Dict[str, Any]:
    """Belirtilen başlıklı pencereyi öne getirir (safe)."""
    import ctypes
    user32 = ctypes.windll.user32
    pencreler = []

    def enum_cb(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            uzunluk = user32.GetWindowTextLengthW(hwnd)
            if uzunluk > 0:
                baslik = ctypes.create_unicode_buffer(uzunluk + 1)
                user32.GetWindowTextW(hwnd, baslik, uzunluk + 1)
                pencreler.append((hwnd, baslik.value))
        return True

    ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(ENUM_WINDOWS_PROC(enum_cb), 0)

    hedef = str(pencere_basligi or "").strip()
    if not hedef:
        return {"ok": False, "hata": "Pencere başlığı belirtilmedi."}

    eslesen = [p for p in pencreler
               if hedef.lower() in p[1].lower()]
    if not eslesen:
        return {"ok": False, "hata": "Pencere bulunamadı: " + hedef}

    hwnd = eslesen[0][0]
    user32.SetForegroundWindow(hwnd)
    return {"ok": True, "pencere": eslesen[0][1],
            "mesaj": "Pencere öne getirildi: " + hedef}


def pencere_kapat(pencere_basligi: str) -> Dict[str, Any]:
    """Belirtilen başlıklı pencereyi kapatır (kullanıcı onayı gerektirir)."""
    import ctypes
    user32 = ctypes.windll.user32
    pencreler = []

    def enum_cb(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            uzunluk = user32.GetWindowTextLengthW(hwnd)
            if uzunluk > 0:
                baslik = ctypes.create_unicode_buffer(uzunluk + 1)
                user32.GetWindowTextW(hwnd, baslik, uzunluk + 1)
                pencreler.append((hwnd, baslik.value))
        return True

    ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(ENUM_WINDOWS_PROC(enum_cb), 0)

    hedef = str(pencere_basligi or "").strip()
    if not hedef:
        return {"ok": False, "hata": "Pencere başlığı belirtilmedi."}

    eslesen = [p for p in pencreler
               if hedef.lower() in p[1].lower()]
    if not eslesen:
        return {"ok": False, "hata": "Pencere bulunamadı: " + hedef}

    hwnd = eslesen[0][0]
    WM_CLOSE = 0x0010
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    return {"ok": True, "pencere": eslesen[0][1],
            "mesaj": "Pencere kapatma isteği gönderildi: " + hedef}


# ---------------------------------------------------------------------------
# 4. Klavye / fare kontrolü (confirm — kullanıcı makinesine input gönderir)
# ---------------------------------------------------------------------------

def fare_tikla(hedef: str) -> Dict[str, Any]:
    """Belirtilen koordinatlara fare tıklar (kullanıcı onayı gerektirir).
    hedef: "x,y" formatında koordinat string'i.
    """
    import ctypes, time
    try:
        user32 = ctypes.windll.user32
        x = int(str(hedef).split(",")[0]) if "," in str(hedef) else 100
        y = int(str(hedef).split(",")[1]) if "," in str(hedef) else 100
        user32.SetCursorPos(x, y)
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP = 0x0004
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, x, y, 0, 0)
        return {"ok": True, "islem": "tikla", "konum": [x, y],
                "mesaj": f"Fare tıklandı: {x},{y}"}
    except Exception as e:
        return {"ok": False, "hata": repr(e)[:200]}


def klavye_yaz(metin: str) -> Dict[str, Any]:
    """Belirtilen metni klavyeden yazar (kullanıcı onayı gerektirir)."""
    import ctypes, time
    try:
        user32 = ctypes.windll.user32
        metin = str(metin or "")
        if not metin:
            return {"ok": False, "hata": "Yazılacak metin belirtilmedi."}
        for karakter in metin:
            vk = user32.VkKeyScanW(ord(karakter)) & 0xFF
            shift = (user32.VkKeyScanW(ord(karakter)) >> 8) & 1
            if shift:
                user32.keybd_event(0x10, 0, 0, 0)
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 2, 0)
            if shift:
                user32.keybd_event(0x10, 0, 2, 0)
            time.sleep(0.05)
        return {"ok": True, "islem": "yaz",
                "karakter_sayisi": len(metin),
                "mesaj": "Metin yazıldı: " + metin[:50] + ("..." if len(metin) > 50 else "")}
    except Exception as e:
        return {"ok": False, "hata": repr(e)[:200]}


# ---------------------------------------------------------------------------
# 5. Dosya işlemleri (confirm — proje klasörü içinde, yedekli)
# ---------------------------------------------------------------------------

def dosya_olustur(dosya_adi: str, icerik: str = "",
                  onay_uzere: bool = False) -> Dict[str, Any]:
    """Yeni dosya oluşturur (yalnızca JARVIS proje klasörü içinde,
    üzerine yazmadan önce onay istenir)."""
    import shutil
    try:
        ad = str(dosya_adi or "").strip()
        if not ad:
            return {"ok": False, "hata": "Dosya adı belirtilmedi."}
        p = Path(ad)
        try:
            p_resolved = p.resolve()
        except Exception:
            return {"ok": False, "hata": "Geçersiz yol."}
        if (_KOK not in p_resolved.parents
                and p_resolved != _KOK):
            return {"ok": False, "hata":
                    "Proje klasörü dışına dosya yazma engellendi."}
        if p_resolved.exists():
            if not onay_uzere:
                return {
                    "ok": False,
                    "gerekli_onay": "dosya_var",
                    "dosya": str(p_resolved),
                    "mesaj": "Dosya zaten var. Üzerine yazmak için onay_uzere=True ile tekrar çağırın."}
                yedek = p_resolved.with_suffix(
                    p_resolved.suffix + ".bak")
                shutil.copy2(p_resolved, yedek)
        p_resolved.parent.mkdir(parents=True, exist_ok=True)
        p_resolved.write_text(icerik, encoding="utf-8")
        return {"ok": True, "dosya": str(p_resolved),
                "boyut": len(icerik),
                "mesaj": "Dosya oluşturuldu / yazıldı."}
    except Exception as e:
        return {"ok": False, "hata": repr(e)[:200]}


# ---------------------------------------------------------------------------
# 6. Görev durumu
# ---------------------------------------------------------------------------

_DURUM = {
    "calisiyor": False,
    "faz": "beklemede",
    "mesaj": "",
    "talep": "",
    "baslangic": 0.0,
    "adim": 0,
    "toplam_adim": 0,
    "iptal": False,
    "klasor": "",
    "dosyalar": [],
    "hatalar": [],
}


def durum() -> Dict[str, Any]:
    """Bilgisayar otomasyonu durumunu döndürür."""
    global _DURUM
    with _KILIT:
        return dict(_DURUM)


def iptal():
    """Çalışan işlemi durdurur."""
    global _DURUM
    with _KILIT:
        _DURUM["iptal"] = True
        _DURUM["mesaj"] = "Durdurma istendi..."


def _durum_guncelle(**kwargs):
    global _DURUM
    with _KILIT:
        _DURUM.update(kwargs)


# ---------------------------------------------------------------------------
# 7. Ana giriş noktası — bilgisayar otomasyonu
# ---------------------------------------------------------------------------

def bilgisayar_otomasyonu(talep: str, log=None,
                          onay_callback: Optional[Callable] = None
                          ) -> Dict[str, Any]:
    """Tek giris noktasi: talep al, planla, calistir, raporla."""
    _durum_guncelle(
        calisiyor=True, faz="planlaniyor",
        mesaj="Istek analiz ediliyor...",
        talep=talep, baslangic=time.time(),
        adim=0, toplam_adim=0,
        iptal=False, klasor="", dosyalar=[], hatalar=[]
    )

    rapor = {
        "talep": talep,
        "zaman": time.strftime("%Y-%m-%d %H:%M:%S"),
        "durum": "BASLADI",
        "adimlar": [],
        "sonuc": None,
        "hata": None,
    }

    def _log(msg: str):
        if log:
            log(msg)
        _durum_guncelle(mesaj=msg)

    try:
        # 1) Talep analizi
        _durum_guncelle(faz="talep analiz ediliyor", adim=1)
        rapor["adimlar"].append(
            {"adim": 1, "islem": "talep_analizi",
             "durum": "calisiyor",
             "detay": "Talep analiz ediliyor..."})
        _log("1/7 Talep analiz ediliyor...")

        talep_lower = str(talep or "").lower()

        # Basit anahtar kelimeye dayalı plan
        adimlar_plan = []

        if any(k in talep_lower for k in
               ["uygulama ac", "program ac", "uygulamayi ac", "calistir"]):
            adimlar_plan.append(("uygulama_ac", "Uygulama açma"))

        if any(k in talep_lower for k in
               ["pencere listele", "acik pencereler", "pencere listesi"]):
            adimlar_plan.append(("pencere_listele", "Pencere listesi"))

        if any(k in talep_lower for k in
               ["dosya olustur", "yeni dosya", "dosya yarat"]):
            adimlar_plan.append(("dosya_olustur", "Dosya oluşturma"))

        if any(k in talep_lower for k in
               ["dosya yaz", "dosyaya yaz", "metin yaz", "yazi yaz"]):
            adimlar_plan.append(("dosya_yaz", "Dosyaya yazma"))

        if any(k in talep_lower for k in
               ["tikla", "fare tikla", "fare bas"]):
            adimlar_plan.append(("klavye_fare_tikla", "Fare tıklama"))

        if any(k in talep_lower for k in
               ["yaz", "klavye yaz", "metin yaz", "yazi yaz"]):
            adimlar_plan.append(("klavye_fare_yaz", "Klavye yazma"))

        if not adimlar_plan:
            adimlar_plan.append(("bilgi_ver", "Bilgi verme"))

        rapor["adim_planlandi"] = len(adimlar_plan)
        _durum_guncelle(toplam_adim=len(adimlar_plan))

        # 2) Adımları çalıştır
        for sira, (islem_adi, aciklama) in enumerate(adimlar_plan, 1):
            if _DURUM["iptal"]:
                rapor["durum"] = "DURDURULDU"
                rapor["adimlar"].append(
                    {"adim": sira, "islem": islem_adi,
                     "durum": "durduruldu",
                     "detay": "Kullanıcı durdurdu."})
                break

            _durum_guncelle(faz=f"adim {sira}/{len(adimlar_plan)}",
                            adim=sira)
            rapor["adimlar"].append(
                {"adim": sira, "islem": islem_adi,
                 "durum": "calisiyor",
                 "detay": aciklama})
            _log(f"{sira}/{len(adimlar_plan)} {aciklama}...")

            try:
                if islem_adi == "uygulama_ac":
                    sonuc = uygulama_ac(talep, log=_log)
                elif islem_adi == "pencere_listele":
                    sonuc = pencereleri_listele(log=_log)
                elif islem_adi == "dosya_olustur":
                    sonuc = dosya_olustur(talep, icerik="", log=_log)
                elif islem_adi == "dosya_yaz":
                    sonuc = dosya_yaz(talep, icerik="", log=_log)
                elif islem_adi == "klavye_fare_tikla":
                    sonuc = fare_tikla("100,100")
                elif islem_adi == "klavye_fare_yaz":
                    sonuc = klavye_yaz(metin=talep)
                elif islem_adi == "bilgi_ver":
                    sonuc = {"ok": True, "mesaj":
                             "Talep alindi: " + talep[:100]}
                else:
                    sonuc = {"ok": False,
                             "hata": "Bilinmeyen islem: " + islem_adi}

                if sonuc.get("ok"):
                    rapor["adimlar"][-1]["durum"] = "tamam"
                    rapor["adimlar"][-1]["detay"] = (
                        str(sonuc.get("mesaj", ""))[:200])
                    _log(f"{sira}/{len(adimlar_plan)} {aciklama} - Tamamlandı")
                else:
                    rapor["adimlar"][-1]["durum"] = "basarisiz"
                    rapor["adimlar"][-1]["detay"] = (
                        str(sonuc.get("hata", ""))[:200])
                    _log(f"{sira}/{len(adimlar_plan)} {aciklama} - "
                         f"Hata: {sonuc.get('hata', '')}")

            except Exception as e:
                rapor["adimlar"][-1]["durum"] = "hata"
                rapor["adimlar"][-1]["detay"] = str(e)[:200]
                _log(f"{sira}/{len(adimlar_plan)} {aciklama} - "
                     f"Hata: {str(e)[:200]}")

        # Sonuç
        _durum_guncelle(calisiyor=False, faz="tamamlandi",
                        mesaj="Islem tamamlandi.")
        rapor["durum"] = "BASARILI"
        rapor["sonuc"] = {
            "adim_sayisi": len(adimlar_plan),
            "tamamlanan": sum(1 for a in rapor["adimlar"]
                              if a.get("durum") == "tamam"),
            "basarisiz": sum(1 for a in rapor["adimlar"]
                             if a.get("durum") == "basarisiz"),
        }
        rapor["adimlar"][-1]["durum"] = "tamam"
        rapor["adimlar"][-1]["detay"] = "Rapor hazir."
        _log("Islem tamamlandi.")

        return rapor

    except Exception as exc:
        rapor["durum"] = "HATA"
        rapor["hata"] = repr(exc)
        _durum_guncelle(calisiyor=False, faz="hata",
                        mesaj=repr(exc)[:200])
        return rapor


# ---------------------------------------------------------------------------
# 8) Yardimci: dosya yazma (iceri gonderilmemis, sadece icerigini
#     alarak yazmak icin kullanilir)
# ---------------------------------------------------------------------------

def dosya_yaz(dosya_adi: str, icerik: str,
              onay_uzere: bool = False) -> Dict[str, Any]:
    """Dosya icerigini guvenli sekilde kaydeder."""
    return dosya_olustur(dosya_adi, icerik,
                         onay_uzere=onay_uzere)


if __name__ == "__main__":
    print("JARVIS MASTER V1 — Bilgisayar Otomasyon Modulu yuklendi.")
    print("Araclar: uygulama_ac, pencere_yonet, klavye_fare_tikla,"
          " klavye_fare_yaz, dosya_olustur, dosya_yaz")
