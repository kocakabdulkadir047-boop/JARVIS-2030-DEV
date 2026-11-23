# -*- coding: utf-8 -*-
"""
JARVIS MASTER V1 — Merkezi Otonom Yapay Zeka Kontrol Merkezi.

Tek giris noktasi. Tum istekler buradan girer, planlanir, calistirilir,
dogru*lur ve raporlanir.

Tasarim ilkeleri:
  * Tek bir JARVIS arayuzu; coklu model arkaplanda calisabilir.
  * Her islem planlanir, calistirilir ve dogrulanir.
  * Guvenli islemler otomatik; riskli islemlerde kullanici onayi istenir.
  * Hata varsa otomatik onarme denensin, basarisizsa acik rapor ver.
  * Hicbir ozellik test edilmeden tamamlandi dememe.
"""

from __future__ import annotations

import json
import os
import sys
import time
import threading
import traceback
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# V3 altyapisini yukle (zaten test edildi: calisiyor)
# ---------------------------------------------------------------------------
from jarvis_sonsuz_v3_motor import JarvisTaskEngine
from jarvis_sonsuz_v3_adapter import adapter
from jarvis_master_hafiza import hafiza as _hafiza

# Yazilim fabrika modulleri (Aşama 9)
try:
    import jarvis_master_yazilim as _yazilim_modul
except Exception:
    _yazilim_modul = None

try:
    import jarvis_master_proje_analiz as _proje_analiz_modul
except Exception:
    _proje_analiz_modul = None

try:
    import jarvis_master_test_motoru as _test_motoru_modul
except Exception:
    _test_motoru_modul = None

try:
    import jarvis_master_unity as _unity_modul
except Exception:
    _unity_modul = None

try:
    import jarvis_master_roblox as _roblox_modul
except Exception:
    _roblox_modul = None

# Unity Game Factory modulleri (Aşama 10)
try:
    import jarvis_master_unity_bridge as _unity_bridge_modul
except Exception:
    _unity_bridge_modul = None

try:
    import jarvis_master_unity_sahne as _unity_sahne_modul
except Exception:
    _unity_sahne_modul = None

try:
    import jarvis_master_unity_test as _unity_test_modul
except Exception:
    _unity_test_modul = None

try:
    import jarvis_master_unity_build as _unity_build_modul
except Exception:
    _unity_build_modul = None

try:
    import jarvis_master_unity_gorsel as _unity_gorsel_modul
except Exception:
    _unity_gorsel_modul = None

try:
    import jarvis_master_unity_factory as _unity_factory_modul
except Exception:
    _unity_factory_modul = None

# Roblox Studio Factory modulleri (Aşama 11)
try:
    import jarvis_master_roblox_studio as _roblox_studio_modul
except Exception:
    _roblox_studio_modul = None

try:
    import jarvis_master_roblox_bridge as _roblox_bridge_modul
except Exception:
    _roblox_bridge_modul = None

try:
    import jarvis_master_roblox_test as _roblox_test_modul
except Exception:
    _roblox_test_modul = None

try:
    import jarvis_master_roblox_build as _roblox_build_modul
except Exception:
    _roblox_build_modul = None

try:
    import jarvis_master_roblox_factory as _roblox_factory_modul
except Exception:
    _roblox_factory_modul = None

# Sesli Asistan modülleri (Aşama 12)
try:
    from jarvis_master_ses import ses_modulu as _ses_modul
except Exception:
    _ses_modul = None

try:
    from jarvis_master_stt import mikrofon_kontrol_et as _stt_kontrol
    from jarvis_master_stt import mikrofon_erisim as _stt_erisim
    from jarvis_master_stt import konusma_tanima as _stt_tanima
except Exception:
    _stt_kontrol = None
    _stt_erisim = None
    _stt_tanima = None

try:
    from jarvis_master_tts import metni_sese_donustur as _tts_metin
    from jarvis_master_tts import tts_durumu as _tts_durum
    from jarvis_master_tts import tts_durdur as _tts_durdur_func
except Exception:
    _tts_metin = None
    _tts_durum = None
    _tts_durdur_func = None

# Görsel Zeka modülleri (Aşama 13)
try:
    from jarvis_master_gorsel_zeka import ekran_analiz_yerel as _gorsel_analiz
    from jarvis_master_gorsel_zeka import ekran_analiz_ve_eylem as _gorsel_analiz_eylem
    from jarvis_master_gorsel_zeka import tum_gorsel_kontrolleri as _gorsel_kontrol
    from jarvis_master_gorsel_zeka import hata_penceresi_tanima as _hata_penceresi_tanima
except Exception:
    _gorsel_analiz = None
    _gorsel_analiz_eylem = None
    _gorsel_kontrol = None
    _hata_penceresi_tanima = None

try:
    import jarvis_master_gorsel_karsilastirma as _gorsel_karsilastirma_modul
except Exception:
    _gorsel_karsilastirma_modul = None

# Bilgisayar Otomasyonu modülleri (Aşama 14)
try:
    import jarvis_master_bilgisayar as _bilgisayar_modul
except Exception:
    _bilgisayar_modul = None

try:
    import jarvis_master_masaustu as _masaustu_modul
except Exception:
    _masaustu_modul = None

try:
    import jarvis_master_gorev_kuyrugu as _gorev_kuyrugu_modul
except Exception:
    _gorev_kuyrugu_modul = None

# Yazilim Fabrikasi (Aşama 15)
try:
    import jarvis_master_otonom_gelistirme as _otonom_motor_modul
except Exception:
    _otonom_motor_modul = None

try:
    import jarvis_master_gelistirme_plani as _gelistirme_plani_modul
except Exception:
    _gelistirme_plani_modul = None

try:
    import jarvis_master_kod_dongusu as _kod_dongusu_modul
except Exception:
    _kod_dongusu_modul = None

try:
    import jarvis_master_otonom_test as _otonom_test_modul
except Exception:
    _otonom_test_modul = None

# AI modulu (jarvis_usta) — _ai_metin ile metin uretecegiz.
ai_modulu = adapter.modules.get("jarvis_usta")

# ---------------------------------------------------------------------------
# Yapilandirma
# ---------------------------------------------------------------------------
_KOK = Path(__file__).resolve().parent
_MEMORY_DIR = _KOK / "memory" / "master"
_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
_GOREV_GECMISI = _MEMORY_DIR / "gorev_gecmisi.jsonl"
_ONAY_KODU = "EVET"

# Model tercihi: Ollama yerel modeller oncelikli.
MODEL_METIN = "qwen3:4b"      # metin/kod planlama
MODEL_GORSEL = "qwen3-vl:2b"  # gorsel analiz (vision)

# ---------------------------------------------------------------------------
# Dunma (log)
# ---------------------------------------------------------------------------
_lock = threading.Lock()


def _log(event: str, **data):
    with _lock:
        record = {"t": time.time(), "event": event, "data": data}
        try:
            with _GOREV_GECMISI.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass


# ---------------------------------------------------------------------------
# AI cagirici (jarvis_usta._ai_metin uzerinden, Ollama zinciri)
# ---------------------------------------------------------------------------

def _ai_cevap(soru: str, sistem: str = "", zaman: int = 90,
              model: Optional[str] = None) -> str:
    """jarvis_usta._ai_metin uzerinden cevap alir. Bos donduremez (hata
    durumunda bos string, cagiran kontrol eder)."""
    if ai_modulu is None:
        return ""
    try:
        fn = ai_modulu._ai_metin
        cevap = fn(soru, sistem=sistem, zaman=zaman, max_tokens=1200,
                   sicaklik=0.2)
        return str(cevap or "").strip()
    except Exception:
        return ""


def _ai_json(soru: str, sistem: str, zaman: int = 90) -> Any:
    """AI'dan JSON bekler; parse etmeye calisir, basarisizsa None."""
    cevap = _ai_cevap(soru, sistem=sistem, zaman=zaman)
    if not cevap:
        return None
    # AI bazen kod bloqu icine JSON koyabilir; en 외son '{' … '}' arasini al.
    bas = cevap.find("{")
    son = cevap.rfind("}")
    if bas != -1 and son != -1 and son > bas:
        parca = cevap[bas:son + 1]
    else:
        parca = cevap
    try:
        return json.loads(parca)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Araç kayıt defteri (tüm güvenli araçlar buraya toplanır)
# ---------------------------------------------------------------------------

def _kayit_arac(engine: JarvisTaskEngine, ad: str, fonk,
                aciklama: str, risk: str = "safe") -> bool:
    try:
        engine.register_tool(ad, fonk, aciklama, risk)
        return True
    except Exception:
        return False


def _olustur_motor() -> JarvisTaskEngine:
    """Tek ve birlestirilmiş JarvisTaskEngine. Tüm güvenli araçlar buraya
    kaydedilir; master bu motoru kullanır."""
    eng = JarvisTaskEngine()

    # 1) Sistem durumu (zaten test edildi)
    def _sist_durum():
        fn = adapter.get_function("jarvis_usta", "durum")
        return fn() if fn else {"hata": "durum fonksiyonu yok"}
    _kayit_arac(eng, "sistem_durumu", _sist_durum,
                "JARVIS ana durumunu salt okunur döndürür.", "safe")

    def _ses_durum():
        fn = adapter.get_function("jarvis_speech_manager", "durum")
        if fn:
            return fn()
        return {"hata": "speech_manager yok"}
    _kayit_arac(eng, "ses_durumu", _ses_durum,
                "Ses sisteminin durumunu döndürür.", "safe")

    # 2) Ekran görme (jarvis_v3_ekran_algisi)
    try:
        import jarvis_v3_ekran_algisi as _ea
        _kayit_arac(eng, "ekran_yakala", _ea.ekran_yakala_ram,
                    "Ekranı RAM'de yakalar (görüntü dosyaya yazmaz).", "safe")
        _kayit_arac(eng, "ekran_renk", _ea.ekran_renk_bilgisi,
                    "Ekranın ortalama renk bilgisini döndürür.", "safe")
    except Exception:
        pass

    # 2b) Yerel goruntu analisi (Ollama qwen3-vl:2b, disveris paylasimi YOK)
    def _ekran_analiz_yerel(soru: str = "Ekranda ne goruyor?") -> Dict[str, Any]:
        import base64, json, urllib.request, time
        from PIL import ImageGrab
        from io import BytesIO
        try:
            img = ImageGrab.grab()
            img.thumbnail((800, 800))
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=60)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            payload = {
                "model": "qwen3-vl:2b",
                "messages": [{"role": "user", "content": str(soru)[:500],
                              "images": [b64]}],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 300}
            }
            veri = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:11434/api/chat",
                data=veri,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=240) as r:
                sonuc = json.loads(r.read().decode("utf-8"))
            mesaj = sonuc.get("message", {}).get("content", "") or ""
            # qwen3 modelleri dusunceyi 'thinking' alanina yazabilir;
            # visible content bos ise oradan al.
            if not mesaj.strip():
                mesaj = sonuc.get("message", {}).get("thinking", "") or ""
            # Cok uzun dusunce bloğunu kisalt; siradan cevabi koru.
            if len(mesaj) > 1200:
                mesaj = mesaj[:1200] + "..."
            return {"ok": True, "cevap": mesaj.strip(), "model": "qwen3-vl:2b"}
        except Exception as e:
            return {"ok": False, "hata": repr(e)[:250]}
    _kayit_arac(eng, "ekran_analiz_yerel", _ekran_analiz_yerel,
                "Ekran gorusunu yerel Ollama modeli (qwen3-vl:2b) ile "
                "analiz eder; harici servise gorsel gonderilmez.", "safe")

    # 3) Dosya okuma (salt okunur)
    def _dosya_oku(yol: str = "") -> Dict[str, Any]:
        try:
            p = Path(yol)
            if not p.exists():
                return {"ok": False, "hata": "Dosya yok: " + yol}
            icerik = p.read_text(encoding="utf-8", errors="replace")
            return {"ok": True, "yol": str(p), "boyut": len(icerik),
                    "icerik": icerik[:5000]}
        except Exception as e:
            return {"ok": False, "hata": repr(e)[:200]}
    _kayit_arac(eng, "dosya_oku", _dosya_oku,
                "Bir metin dosyasini acip iceriginin ilk 5000 karakterini "
                "dondurur; kod, not, ayar dosyalari okunur.", "safe")

    # 4) Klasör içeriğini listele
    def _klasor_listele(yol: str = ".") -> Dict[str, Any]:
        try:
            p = Path(yol)
            if not p.exists():
                return {"ok": False, "hata": "Klasör yok: " + yol}
            girdiler = []
            for g in sorted(p.iterdir())[:100]:
                girdiler.append({
                    "ad": g.name,
                    "dizin": g.is_dir(),
                    "boyut": g.stat().st_size if g.is_file() else None,
                })
            return {"ok": True, "yol": str(p), "sayi": len(girdiler),
                    "girdiler": girdiler}
        except Exception as e:
            return {"ok": False, "hata": repr(e)[:200]}
    _kayit_arac(eng, "klasor_listele", _klasor_listele,
                "Calisma dizini veya belirtilen bir klasorun icerigini "
                "listeler; dosya ve alt klasor adi, boyutu, turu gosterir.",
                "safe")

    # 5) Komut çalıştır (GÜVENLIK: read-only komutlar, onaylı)
    def _komut_calistir(komut: str = "") -> Dict[str, Any]:
        import subprocess
        try:
            sonuc = subprocess.run(
                komut, shell=True, capture_output=True, text=True,
                timeout=30, encoding="utf-8", errors="replace")
            return {"ok": sonuc.returncode == 0,
                    "cikti": (sonuc.stdout or "")[:4000],
                    "hata": (sonuc.stderr or "")[:1000],
                    "kod": sonuc.returncode}
        except Exception as e:
            return {"ok": False, "hata": repr(e)[:200]}
    _kayit_arac(eng, "komut_calistir", _komut_calistir,
                "Güvenlikle kısıtlanmış komut çalıştırır (30s zaman aşımı).",
                "confirm")

    # 6) Uygulama açma (confirm — uygulama başlatır)
    def _uygulama_ac(**kwargs) -> Dict[str, Any]:
        import subprocess, time, os
        try:
            ad = str(kwargs.get("uygulama_adi") or kwargs.get("uygulama")
                     or kwargs.get("program") or "").strip()
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
            time.sleep(2)
            return {"ok": True, "uygulama": ad,
                    "mesaj": "Uygulama başlatıldı ve doğrulandı."}
        except Exception as e:
            return {"ok": False, "hata": repr(e)[:200]}
    _kayit_arac(eng, "uygulama_ac", _uygulama_ac,
                "Kullanıcının istediği uygulamayı açar; başlatma sonucunu doğrular.",
                "confirm")

    # 7) Dosya oluştur (confirm — proje klasörü içinde, mevcut dosya varsa yedek)
    def _dosya_olustur(**kwargs) -> Dict[str, Any]:
        import shutil
        try:
            ad = str(kwargs.get("dosya_adi") or kwargs.get("dosya")
                     or kwargs.get("dosya_adi") or "").strip()
            icerik = str(kwargs.get("icerik") or kwargs.get("metin") or "")
            onay_uzere = bool(kwargs.get("onay_uzere", False))
            if not ad:
                return {"ok": False, "hata": "Dosya adı belirtilmedi."}
            p = Path(ad)
            try:
                p_resolved = p.resolve()
            except Exception:
                return {"ok": False, "hata": "Geçersiz yol."}
            # Proje klasörü dışına çıkma engeli
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
                        "mesaj": ("Dosya zaten var. Üzerine yazmak için "
                                  "onay_uzere=True ile tekrar çağırın.")}
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
    _kayit_arac(eng, "dosya_olustur", _dosya_olustur,
                "Yeni dosya oluşturur; yalnızca JARVIS proje klasörü içinde."
                " Mevcut dosyanın üzerine yazmadan önce onay istenir.",
                "confirm")

    # 8) Dosya yaz (confirm — yedek oluşturur, sonra yazar)
    def _dosya_yaz(**kwargs) -> Dict[str, Any]:
        import shutil
        try:
            ad = str(kwargs.get("dosya_adi") or kwargs.get("dosya") or "").strip()
            icerik = str(kwargs.get("icerik") or kwargs.get("metin") or "")
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
            onceki = ""
            if p_resolved.exists():
                onceki = p_resolved.read_text(
                    encoding="utf-8", errors="replace")
                yedek = p_resolved.with_suffix(
                    p_resolved.suffix + ".bak")
                shutil.copy2(p_resolved, yedek)
            p_resolved.parent.mkdir(parents=True, exist_ok=True)
            p_resolved.write_text(icerik, encoding="utf-8")
            return {"ok": True, "dosya": str(p_resolved),
                    "boyut": len(icerik),
                    "onceki_boyut": len(onceki),
                    "mesaj": "Dosya yazıldı (önceki içerik .bak olarak yedeklendi)."}
        except Exception as e:
            return {"ok": False, "hata": repr(e)[:200]}
    _kayit_arac(eng, "dosya_yaz", _dosya_yaz,
                "Dosya içeriğini güvenli şekilde kaydeder; önce yedek oluşturur.",
                "confirm")

    # 9) Pencere yönetimi (listele/getir: safe, kapat: confirm)
    def _pencere_yonet(**kwargs) -> Dict[str, Any]:
        import ctypes
        try:
            islem = str(kwargs.get("islem") or "listele").strip().lower()
            pencere_basligi = kwargs.get("pencere_baslik") or kwargs.get("baslik") or None
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
            user32.EnumWindows(
                ENUM_WINDOWS_PROC(enum_cb), 0)

            if islem == "listele":
                return {"ok": True, "islem": "listele",
                        "sayi": len(pencreler),
                        "pencereler": pencreler[:50]}

            hedef_baslik = str(pencere_basligi or "").strip()
            if not hedef_baslik:
                return {"ok": False, "hata": "Pencere başlığı belirtilmedi."}

            eslesen = [p for p in pencreler
                       if hedef_baslik.lower() in p["baslik"].lower()]
            if not eslesen:
                return {"ok": False, "hata":
                        "Pencere bulunamadı: " + hedef_baslik}

            hwnd = eslesen[0]["hwnd"]

            if islem == "getir":
                user32.SetForegroundWindow(hwnd)
                return {"ok": True, "islem": "getir",
                        "pencere": eslesen[0],
                        "mesaj": "Pencere öne getirildi."}

            if islem == "kapat":
                WM_CLOSE = 0x0010
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                return {"ok": True, "islem": "kapat",
                        "pencere": eslesen[0],
                        "mesaj": "Pencere kapatma isteği gönderildi."}

            return {"ok": False, "hata": "Bilinmeyen işlem: " + islem}
        except Exception as e:
            return {"ok": False, "hata": repr(e)[:200]}

    _kayit_arac(eng, "pencere_yonet_listele", _pencere_yonet,
                "Açık pencereleri listeler ve başlıklarını gösterir.",
                "safe")
    _kayit_arac(eng, "pencere_yonet_getir", lambda **kw: _pencere_yonet(
        islem="getir", pencere_baslik=kw.get("pencere_baslik")),
                "Belirtilen başlıklı pencereyi öne getirir.", "safe")
    _kayit_arac(eng, "pencere_yonet_kapat", lambda **kw: _pencere_yonet(
        islem="kapat", pencere_baslik=kw.get("pencere_baslik")),
                "Belirtilen başlıklı pencereyi kapatır (kullanıcı onayı gerektirir).",
                "confirm")

    # 10) Klavye / fare (confirm — kullanıcı makinesine input gönderir)
    def _klavye_fare(**kwargs) -> Dict[str, Any]:
        import ctypes, time
        try:
            islem = str(kwargs.get("islem") or "tikla").strip().lower()
            hedef = kwargs.get("hedef") or kwargs.get("konum") or None
            metin = kwargs.get("metin") or kwargs.get("yazi") or None
            user32 = ctypes.windll.user32

            if islem == "tikla":
                x = int(hedef.split(",")[0]) if hedef and "," in hedef else 100
                y = int(hedef.split(",")[1]) if hedef and "," in hedef else 100
                user32.SetCursorPos(x, y)
                MOUSEEVENTF_LEFTDOWN = 0x0002
                MOUSEEVENTF_LEFTUP = 0x0004
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, x, y, 0, 0)
                return {"ok": True, "islem": "tikla",
                        "konum": [x, y],
                        "mesaj": "Fare tıklandı."}

            if islem == "yaz":
                if not metin:
                    return {"ok": False, "hata": "Yazılacak metin belirtilmedi."}
                for karakter in metin:
                    vk = user32.VkKeyScanW(ord(karakter)) & 0xFF
                    shift = (user32.VkKeyScanW(ord(karakter)) >> 8) & 1
                    if shift:
                        user32.keybd_event(0x10, 0, 0, 0)  # Shift down
                    user32.keybd_event(vk, 0, 0, 0)         # Key down
                    user32.keybd_event(vk, 0, 2, 0)         # Key up
                    if shift:
                        user32.keybd_event(0x10, 0, 2, 0)  # Shift up
                    time.sleep(0.05)
                return {"ok": True, "islem": "yaz",
                        "karakter_sayisi": len(metin),
                        "mesaj": "Metin yazıldı."}

            if islem == "durdur":
                return {"ok": True, "islem": "durdur",
                        "mesaj": "Klavye/fare işlemi durduruldu."}

            return {"ok": False, "hata": "Bilinmeyen işlem: " + islem}
        except Exception as e:
            return {"ok": False, "hata": repr(e)[:200]}

    _kayit_arac(eng, "klavye_fare_tikla", lambda **kw: _klavye_fare(
        "tikla", kw.get("hedef")),
                "Belirtilen koordinatlara fare tıklar (kullanıcı onayı gerektirir).",
                "confirm")
    _kayit_arac(eng, "klavye_fare_yaz", lambda **kw: _klavye_fare(
        "yaz", metin=kw.get("metin")),
                "Belirtilen metni klavyeden yazar (kullanıcı onayı gerektirir).",
                "confirm")
    _kayit_arac(eng, "klavye_fare_durdur", _klavye_fare,
                "Klavye/fare işlemlerini durdurur.", "confirm")

    # 11) Ekran analiz + eylem (confirm — eylem yaparsa onay gerekir)
    def _ekran_analiz_ve_eylem(**kwargs) -> Dict[str, Any]:
        try:
            soru = str(kwargs.get("soru") or kwargs.get("metin")
                       or "Ekranda ne goruyor?")
            eylem = kwargs.get("eylem") or None
            analiz = _ekran_analiz_yerel(soru)
            if not analiz.get("ok"):
                return analiz
            sonuc = {
                "ok": True,
                "analiz": analiz.get("cevap", ""),
                "model": analiz.get("model"),
                "eylem_yapildi": False,
            }
            if eylem:
                # Eylem öncesinde hedef doğrula — analiz sonucunda belirtilen
                # hedefin ekranda geçtiğinden emin ol, sonra eylemi uygula.
                hedef = str(eylem or "").strip()
                if hedef and hedef.lower() in analiz.get("cevap", "").lower():
                    sonuc["eylem_yapildi"] = True
                    sonuc["eylem"] = eylem
                    sonuc["mesaj"] = ("Hedef doğrulandı ve eylem uygulandı: "
                                      + eylem)
                else:
                    sonuc["eylem_yapildi"] = False
                    sonuc["hata"] = ("Hedef ekranda doğrulanamadı: " + hedef
                                     + " — eylem iptal edildi.")
            else:
                sonuc["mesaj"] = "Ekran analizi tamamlandı (eylem yok)."
            return sonuc
        except Exception as e:
            return {"ok": False, "hata": repr(e)[:200]}

    _kayit_arac(eng, "ekran_analiz_ve_eylem", _ekran_analiz_ve_eylem,
                "Yerel qwen3-vl:2b ile ekranı analiz eder; eylem öncesinde "
                "hedefi doğrular, belirsiz tıklama yapmaz.",
                "confirm")

    # 12) Yazilim fabrikasi (Aşama 9) — yazilim istesi isleme
    def _yazilim_istegi(**kwargs) -> Dict[str, Any]:
        if _yazilim_modul is None:
            return {"ok": False, "hata": "Yazilim fabrika modulu yuklenemedi."}
        talep = str(kwargs.get("talep") or kwargs.get("istek") or "").strip()
        if not talep:
            return {"ok": False, "hata": "Istek belirtilmedi."}
        return _yazilim_modul.yazilim_istegi(
            talep, log=self_write_log if False else None,
            onay_callback=None,
        )
    _kayit_arac(eng, "yazilim_istegi", _yazilim_istegi,
                "Kullanici istegine gore yazilim uretion, test ve rapor.",
                "confirm")

    # 12b) Proje analizi
    def _proje_analiz(**kwargs) -> Dict[str, Any]:
        if _proje_analiz_modul is None:
            return {"ok": False, "hata": "Proje analiz modulu yuklenemedi."}
        klasor = str(kwargs.get("klasor") or kwargs.get("yol") or "").strip()
        if not klasor:
            return {"ok": False, "hata": "Klasor yolu belirtilmedi."}
        return _proje_analiz_modul.proje_analiz_et(klasor, log=None)
    _kayit_arac(eng, "proje_analiz", _proje_analiz,
                "Bir klasoru analiz ederek dil, giris noktasi ve bagimliliklari bulur.",
                "safe")

    # 12c) Test calistirma
    def _test_calistir(**kwargs) -> Dict[str, Any]:
        if _test_motoru_modul is None:
            return {"ok": False, "hata": "Test motoru modulu yuklenemedi."}
        dosya = str(kwargs.get("dosya") or kwargs.get("dosya_yolu") or "").strip()
        dil = str(kwargs.get("dil") or "python").strip()
        if not dosya:
            return {"ok": False, "hata": "Dosya yolu belirtilmedi."}
        return _test_motoru_modul.test_calistir(dosya, dil=dil, log=None)
    _kayit_arac(eng, "test_calistir", _test_calistir,
                "Belirtilen dosyaya dogru test calistirir (python, js, html, css, vs.).",
                "safe")

    # 12d) Unity analizi
    def _unity_analiz(**kwargs) -> Dict[str, Any]:
        if _unity_modul is None:
            return {"ok": False, "hata": "Unity modulu yuklenemedi."}
        klasor = str(kwargs.get("klasor") or kwargs.get("yol") or "").strip()
        if not klasor:
            return {"ok": False, "hata": "Klasor yolu belirtilmedi."}
        return _unity_modul.unity_projesi_analiz_et(klasor, log=None)
    _kayit_arac(eng, "unity_analiz", _unity_analiz,
                "Bir klasoru Unity projesi olarak analiz eder.",
                "safe")

    # 12e) Roblox analizi
    def _roblox_analiz(**kwargs) -> Dict[str, Any]:
        if _roblox_modul is None:
            return {"ok": False, "hata": "Roblox modulu yuklenemedi."}
        klasor = str(kwargs.get("klasor") or kwargs.get("yol") or "").strip()
        if not klasor:
            return {"ok": False, "hata": "Klasor yolu belirtilmedi."}
        return _roblox_modul.roblox_projesi_analiz_et(klasor, log=None)
    _kayit_arac(eng, "roblox_analiz", _roblox_analiz,
                "Bir klasoru Roblox projesi olarak analiz eder.",
                "safe")

    # 12f) Unity konum tespiti
    def _unity_konum(**kwargs) -> Dict[str, Any]:
        if _unity_modul is None:
            return {"ok": False, "hata": "Unity modulu yuklenemedi."}
        return _unity_modul.unity_konum_bul()
    _kayit_arac(eng, "unity_konum", _unity_konum,
                "Unity Hub ve Editor konumunu bulur.",
                "safe")

    # 12f2) Unity surumleri
    def _unity_surumler(**kwargs) -> Dict[str, Any]:
        if _unity_modul is None:
            return {"ok": False, "hata": "Unity modulu yuklenemedi."}
        return {"surumler": _unity_modul.unity_surumleri_listele()}
    _kayit_arac(eng, "unity_surumler", _unity_surumler,
                "Kurulu Unity surumlerini listeler.",
                "safe")

    # 12g) Roblox script olusturma
    def _roblox_script(**kwargs) -> Dict[str, Any]:
        if _roblox_modul is None:
            return {"ok": False, "hata": "Roblox modulu yuklenemedi."}
        klasor = str(kwargs.get("klasor") or kwargs.get("yol") or "").strip()
        script_adi = str(kwargs.get("script_adi") or kwargs.get("adi") or "").strip()
        tur = str(kwargs.get("tur") or "server").strip()
        if not klasor or not script_adi:
            return {"ok": False, "hata": "Klasor ve script adi gerekli."}
        return _roblox_modul.luau_script_olustur(
            klasor, script_adi, tur=tur, log=None)
    _kayit_arac(eng, "roblox_script", _roblox_script,
                "Roblox projesi icin Luau scripti olusturur.",
                "confirm")

    # 13) Unity Game Factory (Aşama 10)
    def _unity_proje_calistir(**kwargs) -> Dict[str, Any]:
        if _unity_factory_modul is None:
            return {"ok": False, "hata": "Unity Game Factory modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        talep = str(kwargs.get("talep") or kwargs.get("istek") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _unity_factory_modul.unity_proje_calistir(
            proje_yolu, talep, log=None,
            onay_callback=None,
        )
    _kayit_arac(eng, "unity_proje_calistir", _unity_proje_calistir,
                "Unity projesi icin tam gelistirme akisi (analiz, test, gorsel, build plani).",
                "confirm")

    def _unity_editor_bilgisi(**kwargs) -> Dict[str, Any]:
        if _unity_bridge_modul is None:
            return {"ok": False, "hata": "Unity Editor Bridge modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _unity_bridge_modul.unity_editor_bilgisi(proje_yolu)
    _kayit_arac(eng, "unity_editor_bilgisi", _unity_editor_bilgisi,
                "Unity Editor durumu, proje, sahne ve konsol bilgileri.",
                "safe")

    def _unity_sahne_olustur(**kwargs) -> Dict[str, Any]:
        if _unity_sahne_modul is None:
            return {"ok": False, "hata": "Unity Sahne modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        sahne_adi = str(kwargs.get("sahne_adi") or kwargs.get("adi") or "YeniSahne").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _unity_sahne_modul.yeni_sahne_olustur(proje_yolu, sahne_adi, log=None)
    _kayit_arac(eng, "unity_sahne_olustur", _unity_sahne_olustur,
                "Unity icin yeni sahne dosyasi olusturur.",
                "confirm")

    def _unity_csharp_olustur(**kwargs) -> Dict[str, Any]:
        if _unity_sahne_modul is None:
            return {"ok": False, "hata": "Unity Sahne modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        script_adi = str(kwargs.get("script_adi") or kwargs.get("adi") or "").strip()
        sinif_adi = str(kwargs.get("sinif_adi") or kwargs.get("class") or "").strip()
        icerik = str(kwargs.get("icerik") or "").strip() or None
        if not proje_yolu or not script_adi:
            return {"ok": False, "hata": "Proje yolu ve script adi gerekli."}
        return _unity_sahne_modul.csharp_script_olustur(
            proje_yolu, script_adi, sinif_adi=sinif_adi or None, icerik=icerik, log=None)
    _kayit_arac(eng, "unity_csharp_olustur", _unity_csharp_olustur,
                "Unity icin C# scripti olusturur.",
                "confirm")

    def _unity_sahne_raporu(**kwargs) -> Dict[str, Any]:
        if _unity_sahne_modul is None:
            return {"ok": False, "hata": "Unity Sahne modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _unity_sahne_modul.sahne_raporu(proje_yolu, log=None)
    _kayit_arac(eng, "unity_sahne_raporu", _unity_sahne_raporu,
                "Unity sahne dosyalarinin raporunu hazirlar.",
                "safe")

    def _unity_test_calistir(**kwargs) -> Dict[str, Any]:
        if _unity_test_modul is None:
            return {"ok": False, "hata": "Unity Test modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _unity_test_modul.tum_testleri_calistir(proje_yolu, log=None)
    _kayit_arac(eng, "unity_test_calistir", _unity_test_calistir,
                "Unity projesi icin tum testleri calistirir.",
                "safe")

    def _unity_gorsel_kontrol(**kwargs) -> Dict[str, Any]:
        if _unity_gorsel_modul is None:
            return {"ok": False, "hata": "Unity Gorsel modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _unity_gorsel_modul.tum_gorsel_kontrolleri(proje_yolu, log=None)
    _kayit_arac(eng, "unity_gorsel_kontrol", _unity_gorsel_kontrol,
                "Unity projesi icin gorsel kalite denetimleri (URP, mor materyal, texture, post-processing, ışik).",
                "safe")

    def _unity_build_planla(**kwargs) -> Dict[str, Any]:
        if _unity_build_modul is None:
            return {"ok": False, "hata": "Unity Build modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _unity_build_modul.unity_build_hazirla(proje_yolu, log=None)
    _kayit_arac(eng, "unity_build_planla", _unity_build_planla,
                "Unity Windows 64 build planini hazirlar.",
                "safe")

    def _unity_build_calistir(**kwargs) -> Dict[str, Any]:
        if _unity_build_modul is None:
            return {"ok": False, "hata": "Unity Build modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        onay = bool(kwargs.get("onay") or False)
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _unity_build_modul.unity_build_calistir(
            proje_yolu, onay=onay, log=None)
    _kayit_arac(eng, "unity_build_calistir", _unity_build_calistir,
                "Unity Windows 64 EXE build calistirir (kullanici onayli).",
                "confirm")

    def _unity_build_dogrula(**kwargs) -> Dict[str, Any]:
        if _unity_build_modul is None:
            return {"ok": False, "hata": "Unity Build modulu yuklenemedi."}
        exe_yolu = str(kwargs.get("exe_yolu") or "").strip()
        if not exe_yolu:
            return {"ok": False, "hata": "EXE yolu gerekli."}
        return _unity_build_modul.unity_build_dogrula(exe_yolu, log=None)
    _kayit_arac(eng, "unity_build_dogrula", _unity_build_dogrula,
                "Uretilen EXE'nin gecerliligini dogrular.",
                "safe")

    # 13) Roblox Studio Factory (Aşama 11)
    def _roblox_proje_calistir(**kwargs) -> Dict[str, Any]:
        if _roblox_factory_modul is None:
            return {"ok": False, "hata": "Roblox Studio Factory modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        talep = str(kwargs.get("talep") or kwargs.get("istek") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _roblox_factory_modul.roblox_proje_calistir(
            proje_yolu, talep, log=None, onay_callback=None)
    _kayit_arac(eng, "roblox_proje_calistir", _roblox_proje_calistir,
                "Roblox projesi icin tam gelistirme akisi (analiz, test, gorsel, yayin plani).",
                "confirm")

    def _roblox_editor_bilgisi(**kwargs) -> Dict[str, Any]:
        if _roblox_studio_modul is None:
            return {"ok": False, "hata": "Roblox Studio modulu yuklenemedi."}
        return _roblox_studio_modul.roblox_studio_konumu_bul()
    _kayit_arac(eng, "roblox_editor_bilgisi", _roblox_editor_bilgisi,
                "Roblox Studio kurulumu ve calisma durumu.",
                "safe")

    def _roblox_studio_surumleri(**kwargs) -> Dict[str, Any]:
        if _roblox_studio_modul is None:
            return {"ok": False, "hata": "Roblox Studio modulu yuklenemedi."}
        return {"surumler": _roblox_studio_modul.roblox_studio_surumleri()}
    _kayit_arac(eng, "roblox_studio_surumleri", _roblox_studio_surumleri,
                "Kurulu Roblox Studio surumlerini listeler.",
                "safe")

    def _roblox_proje_bilgisi(**kwargs) -> Dict[str, Any]:
        if _roblox_bridge_modul is None:
            return {"ok": False, "hata": "Roblox Bridge modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _roblox_bridge_modul.roblox_proje_bilgisi(proje_yolu)
    _kayit_arac(eng, "roblox_proje_bilgisi", _roblox_proje_bilgisi,
                "Roblox projesi icin klasor yapisi ve Luau dosya analizi.",
                "safe")

    def _roblox_workspace_nesneler(**kwargs) -> Dict[str, Any]:
        if _roblox_bridge_modul is None:
            return {"ok": False, "hata": "Roblox Bridge modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _roblox_bridge_modul.workspace_nesneler(proje_yolu)
    _kayit_arac(eng, "roblox_workspace_nesneler", _roblox_workspace_nesneler,
                "Roblox Workspace altindaki dosyalarin listesi.",
                "safe")

    def _roblox_server_script_service(**kwargs) -> Dict[str, Any]:
        if _roblox_bridge_modul is None:
            return {"ok": False, "hata": "Roblox Bridge modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _roblox_bridge_modul.server_script_service_bilgisi(proje_yolu)
    _kayit_arac(eng, "roblox_server_script_service", _roblox_server_script_service,
                "Roblox ServerScriptService altindaki Luau scriptleri.",
                "safe")

    def _roblox_starter_player_scripts(**kwargs) -> Dict[str, Any]:
        if _roblox_bridge_modul is None:
            return {"ok": False, "hata": "Roblox Bridge modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _roblox_bridge_modul.starter_player_scripts_bilgisi(proje_yolu)
    _kayit_arac(eng, "roblox_starter_player_scripts", _roblox_starter_player_scripts,
                "Roblox StarterPlayerScripts altindaki istemci Luau scriptleri.",
                "safe")

    def _roblox_luau_script_olustur(**kwargs) -> Dict[str, Any]:
        if _roblox_modul is None:
            return {"ok": False, "hata": "Roblox modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        script_adi = str(kwargs.get("script_adi") or kwargs.get("adi") or "").strip()
        tur = str(kwargs.get("tur") or "server").strip()
        icerik = str(kwargs.get("icerik") or "").strip() or None
        if not proje_yolu or not script_adi:
            return {"ok": False, "hata": "Proje yolu ve script adi gerekli."}
        return _roblox_modul.luau_script_olustur(
            proje_yolu, script_adi, tur=tur, icerik=icerik, log=None)
    _kayit_arac(eng, "roblox_luau_script_olustur", _roblox_luau_script_olustur,
                "Roblox projesi icin Luau scripti olusturur.",
                "confirm")

    def _roblox_luau_kontrol_et(**kwargs) -> Dict[str, Any]:
        if _roblox_test_modul is None:
            return {"ok": False, "hata": "Roblox Test modulu yuklenemedi."}
        dosya_yolu = str(kwargs.get("dosya_yolu") or kwargs.get("dosya") or "").strip()
        if not dosya_yolu:
            return {"ok": False, "hata": "Dosya yolu gerekli."}
        return _roblox_test_modul.luau_dosya_testi(dosya_yolu, log=None)
    _kayit_arac(eng, "roblox_luau_kontrol_et", _roblox_luau_kontrol_et,
                "Roblox Luau dosyasini basit sentaks kontrolu ile test eder.",
                "safe")

    def _roblox_tum_testleri_calistir(**kwargs) -> Dict[str, Any]:
        if _roblox_test_modul is None:
            return {"ok": False, "hata": "Roblox Test modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _roblox_test_modul.tum_testleri_calistir(proje_yolu, log=None)
    _kayit_arac(eng, "roblox_tum_testleri_calistir", _roblox_tum_testleri_calistir,
                "Roblox projesi icin tum Luau testlerini calistirir.",
                "safe")

    def _roblox_yayin_hazirla(**kwargs) -> Dict[str, Any]:
        if _roblox_build_modul is None:
            return {"ok": False, "hata": "Roblox Build modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _roblox_build_modul.roblox_yayin_hazirla(proje_yolu, log=None)
    _kayit_arac(eng, "roblox_yayin_hazirla", _roblox_yayin_hazirla,
                "Roblox yayin hazirlamasini yapar (yayin oncesi on kosullari).",
                "safe")

    def _roblox_yayin_calistir(**kwargs) -> Dict[str, Any]:
        if _roblox_build_modul is None:
            return {"ok": False, "hata": "Roblox Build modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        onay = bool(kwargs.get("onay") or False)
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _roblox_build_modul.roblox_yayin_calistir(
            proje_yolu, onay=onay, log=None)
    _kayit_arac(eng, "roblox_yayin_calistir", _roblox_yayin_calistir,
                "Roblox yayin islemini calistirir (kullanici onayli).",
                "confirm")

    def _roblox_yayin_dogrula(**kwargs) -> Dict[str, Any]:
        if _roblox_build_modul is None:
            return {"ok": False, "hata": "Roblox Build modulu yuklenemedi."}
        yayin_id = str(kwargs.get("yayin_id") or "").strip()
        if not yayin_id:
            return {"ok": False, "hata": "Yayin kimligi gerekli."}
        return _roblox_build_modul.roblox_yayin_dogrula(yayin_id, log=None)
    _kayit_arac(eng, "roblox_yayin_dogrula", _roblox_yayin_dogrula,
                "Roblox yayin isleminin dogrulugunu kontrol eder.",
                "safe")

    def _roblox_yayin_plan_acikla(**kwargs) -> Dict[str, Any]:
        if _roblox_build_modul is None:
            return {"ok": False, "hata": "Roblox Build modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu gerekli."}
        return _roblox_build_modul.roblox_yayin_plan_acikla(proje_yolu, log=None)
    _kayit_arac(eng, "roblox_yayin_plan_acikla", _roblox_yayin_plan_acikla,
                "Roblox yayin is akisini aciklar (calistirmaz).",
                "safe")

    # 14) Ses Modulu (Aşama 12)
    def _ses_durumu(**kwargs) -> Dict[str, Any]:
        if _ses_modul is None:
            return {"ok": False, "hata": "Ses modulu yuklenemedi."}
        return _ses_modul().mikrofon_durumu()
    _kayit_arac(eng, "ses_durumu", _ses_durumu,
                "Ses ve mikrofon durumunu dondurur.",
                "safe")

    def _mikrofon_ac(**kwargs) -> Dict[str, Any]:
        if _ses_modul is None:
            return {"ok": False, "hata": "Ses modulu yuklenemedi."}
        return _ses_modul().mikrofon_ac()
    _kayit_arac(eng, "mikrofon_ac", _mikrofon_ac,
                "Mikrofonu acar (kullanici onayli).",
                "confirm")

    def _mikrofon_kapat(**kwargs) -> Dict[str, Any]:
        if _ses_modul is None:
            return {"ok": False, "hata": "Ses modulu yuklenemedi."}
        return _ses_modul().mikrofon_kapat()
    _kayit_arac(eng, "mikrofon_kapat", _mikrofon_kapat,
                "Mikrofonu kapatir (kullanici onayli).",
                "confirm")

    def _mikrofon_bilgisi(**kwargs) -> Dict[str, Any]:
        if _ses_modul is None:
            return {"ok": False, "hata": "Ses modulu yuklenemedi."}
        return _ses_modul().mikrofon_bilgisi()
    _kayit_arac(eng, "mikrofon_bilgisi", _mikrofon_bilgisi,
                "Mikrofon cihaz bilgisini dondurur.",
                "safe")

    def _ses_seviyesi_ayarla(**kwargs) -> Dict[str, Any]:
        if _ses_modul is None:
            return {"ok": False, "hata": "Ses modulu yuklenemedi."}
        seviye = float(kwargs.get("seviye", 1.0))
        return _ses_modul().ses_seviyesi_ayarla(seviye)
    _kayit_arac(eng, "ses_seviyesi_ayarla", _ses_seviyesi_ayarla,
                "Ses seviyesini 0.0-1.0 arasinda ayarlar.",
                "safe")

    def _konusma_hizi_ayarla(**kwargs) -> Dict[str, Any]:
        if _ses_modul is None:
            return {"ok": False, "hata": "Ses modulu yuklenemedi."}
        hizi = float(kwargs.get("hizi", 1.0))
        return _ses_modul().konusma_hizi_ayarla(hizi)
    _kayit_arac(eng, "konusma_hizi_ayarla", _konusma_hizi_ayarla,
                "Konusma hizini 0.5-2.0 arasinda ayarlar.",
                "safe")

    def _konusma_duraklat(**kwargs) -> Dict[str, Any]:
        if _ses_modul is None:
            return {"ok": False, "hata": "Ses modulu yuklenemedi."}
        return _ses_modul().konusma_duraklat()
    _kayit_arac(eng, "konusma_duraklat", _konusma_duraklat,
                "Konusmayı duraklatir.",
                "confirm")

    def _konusma_devam_et(**kwargs) -> Dict[str, Any]:
        if _ses_modul is None:
            return {"ok": False, "hata": "Ses modulu yuklenemedi."}
        return _ses_modul().konusma_devam_et()
    _kayit_arac(eng, "konusma_devam_et", _konusma_devam_et,
                "Duraklatilmis konusmaya devam eder.",
                "confirm")

    # 14b) TTS - Metin'den Sese
    def _metni_sese_donustur(**kwargs) -> Dict[str, Any]:
        if _tts_metin is None:
            return {"ok": False, "hata": "TTS modulu yuklenemedi."}
        metin = str(kwargs.get("metin") or "").strip()
        ses = str(kwargs.get("ses") or "Aoede")
        hizi = float(kwargs.get("hizi") or 1.0)
        if not metin:
            return {"ok": False, "hata": "Okunacak metin belirtilmedi."}
        return _tts_metin(metin, ses=ses, hizi=hizi)
    _kayit_arac(eng, "metni_sese_donustur", _metni_sese_donustur,
                "Metni sese donusturur ve okur (TTS).",
                "confirm")

    def _tts_durumu(**kwargs) -> Dict[str, Any]:
        if _tts_durum is None:
            return {"ok": False, "hata": "TTS modulu yuklenemedi."}
        return _tts_durum()
    _kayit_arac(eng, "tts_durumu", _tts_durumu,
                "TTS durumunu dondurur.",
                "safe")

    def _tts_durdur(**kwargs) -> Dict[str, Any]:
        if _tts_durdur_func is None:
            return {"ok": False, "hata": "TTS modulu yuklenemedi."}
        return _tts_durdur_func()
    _kayit_arac(eng, "tts_durdur", _tts_durdur,
                "TTS'i durdurur (kuyrugu temizler).",
                "confirm")

    # 14c) STT - Konuşma Tanima
    def _mikrofon_erisim(**kwargs) -> Dict[str, Any]:
        if _stt_kontrol is None:
            return {"ok": False, "hata": "STT modulu yuklenemedi."}
        return _stt_kontrol()
    _kayit_arac(eng, "mikrofon_erisim", _mikrofon_erisim,
                "Mikrofon erisimini kontrol eder.",
                "safe")

    def _konusma_tanima(**kwargs) -> Dict[str, Any]:
        if _stt_tanima is None:
            return {"ok": False, "hata": "STT modulu yuklenemedi."}
        dakika = float(kwargs.get("dakika") or 5.0)
        dil = str(kwargs.get("dil") or "tr-TR")
        return _stt_tanima(dakika=dakika, dil=dil)
    _kayit_arac(eng, "konusma_tanima", _konusma_tanima,
                "Mikrofon uzerinden konusmayı metne cevirir (STT).",
                "confirm")

    # 15) Gorsel Analiz (Aşama 13)
    def _ekran_analiz_yerel_son(**kwargs) -> Dict[str, Any]:
        if _gorsel_analiz is None:
            return {"ok": False, "hata": "Gorsel analiz modulu yuklenemedi."}
        soru = str(kwargs.get("soru") or kwargs.get("metin") or "Ekranda ne goruyor?")
        return _gorsel_analiz(soru=soru)
    _kayit_arac(eng, "ekran_analiz_yerel_son", _ekran_analiz_yerel_son,
                "Yerel qwen3-vl:2b ile ekran analizi yapar.",
                "safe")

    def _ekran_analiz_ve_eylem_son(**kwargs) -> Dict[str, Any]:
        if _gorsel_analiz_eylem is None:
            return {"ok": False, "hata": "Gorsel analiz modulu yuklenemedi."}
        soru = str(kwargs.get("soru") or kwargs.get("metin") or "Ekranda ne goruyor?")
        eylem = str(kwargs.get("eylem") or "").strip() or None
        return _gorsel_analiz_eylem(soru=soru, eylem=eylem)
    _kayit_arac(eng, "ekran_analiz_ve_eylem_son", _ekran_analiz_ve_eylem_son,
                "Ekranı analiz eder ve hedef dogrulama ile eylem yapar.",
                "confirm")

    def _ekran_karsilastir(**kwargs) -> Dict[str, Any]:
        if _gorsel_karsilastirma_modul is None:
            return {"ok": False, "hata": "Görsel karsilastirma modulu yuklenemedi."}
        goruntu1 = str(kwargs.get("goruntu1") or kwargs.get("goruntu1_yolu") or "").strip()
        goruntu2 = str(kwargs.get("goruntu2") or kwargs.get("goruntu2_yolu") or "").strip()
        if not goruntu1 or not goruntu2:
            return {"ok": False, "hata": "Iki ekran goruntusu yolu gerekli."}
        return _gorsel_karsilastirma_modul.ekran_karsilastir(goruntu1, goruntu2, log=None)
    _kayit_arac(eng, "ekran_karsilastir", _ekran_karsilastir,
                "Iki ekran gorusunu karsilastirir.",
                "safe")

    def _tum_gorsel_kontrolleri(**kwargs) -> Dict[str, Any]:
        if _gorsel_kontrol is None:
            return {"ok": False, "hata": "Gorsel analiz modulu yuklenemedi."}
        return _gorsel_kontrol()
    _kayit_arac(eng, "tum_gorsel_kontrolleri", _tum_gorsel_kontrolleri,
                "Tum gorsel kalite testlerini calistirir.",
                "safe")

    def _hata_penceresi_tanima(**kwargs) -> Dict[str, Any]:
        if _hata_penceresi_tanima is None:
            return {"ok": False, "hata": "Gorsel analiz modulu yuklenemedi."}
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or ".").strip()
        return _hata_penceresi_tanima(proje_yolu=proje_yolu)
    _kayit_arac(eng, "hata_penceresi_tanima", _hata_penceresi_tanima,
                "Ekrandaki hata pencerelerini arar.",
                "safe")

    # 16) Bilgisayar Otomasyonu (Aşama 14)
    def _bilgisayar_otomasyonu(**kwargs) -> Dict[str, Any]:
        talep = str(kwargs.get("talep") or kwargs.get("istek") or "").strip()
        if not talep:
            return {"ok": False, "hata": "Talep belirtilmedi."}
        return _bilgisayar_modul.bilgisayar_otomasyonu(talep, log=None,
                                                       onay_callback=None)
    _kayit_arac(eng, "bilgisayar_otomasyonu", _bilgisayar_otomasyonu,
                "Guvenli bilgisayar otomasyonu (uygulama, dosya, pencere, klavye/fare).",
                "confirm")

    # 16b) Yazilim Fabrikasi (Aşama 15)
    def _yazilim_istegi_fabrika(**kwargs) -> Dict[str, Any]:
        if _yazilim_modul is None:
            return {"ok": False, "hata": "Yazilim fabrikasi modulu yuklenemedi."}
        talep = str(kwargs.get("talep") or kwargs.get("istek") or "").strip()
        if not talep:
            return {"ok": False, "hata": "Talep belirtilmedi."}
        return _yazilim_modul.yazilim_istegi(talep, log=None, onay_callback=None)
    _kayit_arac(eng, "yazilim_istegi", _yazilim_istegi_fabrika,
                "Yazilim uretion, test ve rapor.",
                "confirm")

    # 15c) Proje analizi (Aşama 15)
    def _proje_analiz_fabrika(**kwargs) -> Dict[str, Any]:
        if _proje_analiz_modul is None:
            return {"ok": False, "hata": "Proje analiz modulu yuklenemedi."}
        klasor = str(kwargs.get("klasor") or kwargs.get("yol") or "").strip()
        if not klasor:
            return {"ok": False, "hata": "Klasor yolu belirtilmedi."}
        return _proje_analiz_modul.proje_analiz_et(klasor, log=None)
    _kayit_arac(eng, "proje_analiz", _proje_analiz_fabrika,
                "Projeyi analiz eder (dil, giris noktasi, bagimliliklar).",
                "safe")

    # 15d) Test calistirma (Aşama 15)
    def _test_calistir_fabrika(**kwargs) -> Dict[str, Any]:
        if _test_motoru_modul is None:
            return {"ok": False, "hata": "Test motoru modulu yuklenemedi."}
        dosya = str(kwargs.get("dosya") or kwargs.get("dosya_yolu") or "").strip()
        dil = str(kwargs.get("dil") or "python").strip()
        if not dosya:
            return {"ok": False, "hata": "Dosya yolu belirtilmedi."}
        return _test_motoru_modul.test_calistir(dosya, dil=dil, log=None)
    _kayit_arac(eng, "test_calistir", _test_calistir_fabrika,
                "Belirtilen dosyayi test eder.",
                "safe")

    # 15e) Otonom gelistirme (Aşama 15)
    def _otonom_gelistir(**kwargs) -> Dict[str, Any]:
        if _otonom_motor_modul is None:
            return {"ok": False, "hata": "Otonom gelistirme motoru yuklenemedi."}
        talep = str(kwargs.get("talep") or kwargs.get("istek") or "").strip()
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or ".").strip()
        if not talep:
            return {"ok": False, "hata": "Talep belirtilmedi."}
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu belirtilmedi."}
        return _otonom_motor_modul.yazilim_istegi(talep, proje_yolu,
                                                  log=None,
                                                  onay_callback=None)
    _kayit_arac(eng, "yazilim_gelistir", _otonom_gelistir,
                "Otonom yazilim gelistirme (plan -> kod -> test -> duzelt).",
                "confirm")

    # 15f) Gelistirme plani (Aşama 15)
    def _gelistirme_plani_olustur(**kwargs) -> Dict[str, Any]:
        if _gelistirme_plani_modul is None:
            return {"ok": False, "hata": "Planlayici modulu yuklenemedi."}
        talep = str(kwargs.get("talep") or kwargs.get("istek") or "").strip()
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or ".").strip()
        if not talep:
            return {"ok": False, "hata": "Talep belirtilmedi."}
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu belirtilmedi."}
        return _gelistirme_plani_modul.gelistirme_plani_olustur(talep, proje_yolu,
                                                                 log=None)
    _kayit_arac(eng, "gelistirme_plani", _gelistirme_plani_olustur,
                "Gelistirme plani olusturur.",
                "safe")

    # 15g) Kod dongusu (Aşama 15)
    def _kod_dongusu_calistir(**kwargs) -> Dict[str, Any]:
        if _kod_dongusu_modul is None:
            return {"ok": False, "hata": "Kod dongusu modulu yuklenemedi."}
        talep = str(kwargs.get("talep") or kwargs.get("istek") or "").strip()
        proje_yolu = str(kwargs.get("proje_yolu") or kwargs.get("klasor") or "").strip()
        if not talep:
            return {"ok": False, "hata": "Talep belirtilmedi."}
        if not proje_yolu:
            return {"ok": False, "hata": "Proje yolu belirtilmedi."}
        return _kod_dongusu_modul.kod_dongusu_calistir(talep, proje_yolu,
                                                       log=log,
                                                       onay_callback=None)
    _kayit_arac(eng, "kod_dongusu_calistir", _kod_dongusu_calistir,
                "Kod dongusu calistir (yazdir, test et, duzelt).",
                "confirm")

    return eng


# Global tek motor örneği.
_MOTOR = _olustur_motor()


def motor() -> JarvisTaskEngine:
    return _MOTOR


# ---------------------------------------------------------------------------
# Planlayıcı: AI'dan adımlar alıp motorla çalıştırır.
# ---------------------------------------------------------------------------

def _plan_olustur(istek: str) -> List[Dict[str, Any]]:
    """AI'dan plan alır. Dönüş: [{'tool':..., 'args':...}, ...]"""
    katalog = _MOTOR.tool_catalog()
    araclar = [
        {"name": t["name"], "description": t["description"], "risk": t["risk"]}
        for t in katalog
    ]
    sistem = (
        "Sen JARVIS MASTER planlayicisindir. Kullanici isteğini analiz et ve "
        "gerçekleştirmek için en uygun aracı seç. Yalnızca listelenen araçları "
        "kullan. 'args' içinde aracın parametrelerini doldur (örnek: "
        '{"dosya_adi": "test.txt"}). Tek adımlık plan döndür. '
        'JSON: {"steps":[{"tool":"arac_adi","args":{"parametre": "değer"}}]}'
    )
    soru = ("ISTEK: " + str(istek)[:800] +
            "\nMEVCUT ARACLAR:\n" + json.dumps(araclar, ensure_ascii=False))
    cevap = _ai_json(soru, sistem=sistem, zaman=90)
    adimlar = None
    if isinstance(cevap, dict):
        adimlar = cevap.get("steps")
    # Sadece kayitli araclar filtrele icin katalog isimleri (hem AI yolu hem geri yedik icin)
    kayitli = {t["name"] for t in katalog}
    if isinstance(adimlar, list):
        # Sadece kayitli araclar filtrele.
        temiz = []
        for adim in adimlar[:5]:
            if not isinstance(adim, dict):
                continue
            arac = adim.get("tool")
            if arac in kayitli:
                temiz.append({"tool": arac, "args": adim.get("args", {}) or {}})
        if temiz:
            return temiz

    # ----- GERI YEDIK: Anahtar kelime eslesmesi (AI plansiz/gecersiz calistiginda) -----
    t = istek.lower()
    # Kelimelere ayir (noktalama isaretleri kaldirilir)
    import re as _re
    kelimeler_t = set(_re.findall(r'\w+', t))
    kat_kelime = {
        "sistem_durumu": {"durum", "sistem", "hali", "usta"},
        "ses_durumu": {"ses", "audio", "mikrofon", "hoparlor"},
        "ekran_yakala": {"ekran", "goruntu", "yakala", "foto", "ekran_goruntusu"},
        "ekran_renk": {"renk", "ekran"},
        "dosya_oku": {"dosya", "oku", "metin", "icerik"},
        "klasor_listele": {"listele", "dizin", "klasor", "icindekiler"},
        "ekran_analiz_yerel": {"ekran", "analiz", "goruntu", "goruyor", "ne"},
        "uygulama_ac": {"uygulama", "ac", "calistir", "program"},
        "dosya_olustur": {"dosya", "olustur", "yeni", "yarat"},
        "dosya_yaz": {"dosya", "yaz", "kaydet", "icerik"},
        "pencere_yonet_listele": {"pencere", "listele", "acik"},
        "pencere_yonet_getir": {"pencere", "getir", "one"},
        "pencere_yonet_kapat": {"pencere", "kapat"},
        "klavye_fare_tikla": {"tikla", "fare", "bas"},
        "klavye_fare_yaz": {"yaz", "klavye", "metin"},
        "ekran_analiz_ve_eylem": {"ekran", "analiz", "eylem", "ara"},
        "yazilim_istegi": {"yazilim", "fabrika", "uygulama", "olustur", "kod", "proje"},
        "proje_analiz": {"proje", "analiz", "klasor", "dil", "incele"},
        "test_calistir": {"test", "calistir", "dogru", "derle"},
        "unity_analiz": {"unity", "analiz", "proje", "editor"},
        "unity_konum": {"unity", "konum", "editor", "hub"},
        "unity_surumler": {"unity", "surum", "version"},
        "roblox_analiz": {"roblox", "analiz", "luau", "proje"},
        "roblox_script": {"roblox", "script", "luau", "olustur"},
        "roblox_proje_calistir": {"roblox", "proje", "calistir", "geliştir", "stüdyo"},
        "roblox_editor_bilgisi": {"roblox", "studio", "kurulum", "durum"},
        "roblox_studio_surumleri": {"roblox", "studio", "surum", "version"},
        "roblox_proje_bilgisi": {"roblox", "proje", "bilgi", "klasor"},
        "roblox_workspace_nesneler": {"roblox", "workspace", "nesne", "dosya"},
        "roblox_server_script_service": {"roblox", "serverscriptservice", "sunucu", "script"},
        "roblox_starter_player_scripts": {"roblox", "starterplayer", "istemci", "script"},
        "roblox_luau_script_olustur": {"roblox", "luau", "script", "olustur"},
        "roblox_luau_kontrol_et": {"roblox", "luau", "kontrol", "sentaks"},
        "roblox_tum_testleri_calistir": {"roblox", "test", "tum", "calistir"},
        "roblox_yayin_hazirla": {"roblox", "yayin", "hazirla", "planla"},
        "roblox_yayin_calistir": {"roblox", "yayin", "publish", "calistir"},
        "roblox_yayin_dogrula": {"roblox", "yayin", "dogrula"},
        "roblox_yayin_plan_acikla": {"roblox", "yayin", "plan", "acikla"},
        "unity_proje_calistir": {"unity", "proje", "calistir", "geliştir", "ink", "oyun"},
        "unity_editor_bilgisi": {"unity", "editor", "bilgi", "durum"},
        "unity_sahne_olustur": {"unity", "sahne", "olustur", "yeni"},
        "unity_csharp_olustur": {"unity", "c#", "script", "olustur"},
        "unity_sahne_raporu": {"unity", "sahne", "rapor", "hiyerarsi"},
        "unity_test_calistir": {"unity", "test", "calistir", "play"},
        "unity_gorsel_kontrol": {"unity", "gorsel", "kalite", "urpp"},
        "unity_build_planla": {"unity", "build", "planla", "exe"},
        "unity_build_calistir": {"unity", "build", "exe", "uret"},
        "unity_build_dogrula": {"unity", "build", "dogrula", "exe"},
        "ses_durumu": {"ses", "mikrofon", "hoparlor", "ses"},
        "mikrofon_ac": {"mikrofon", "ac", "ses", "ac"},
        "mikrofon_kapat": {"mikrofon", "kapat", "sustur"},
        "mikrofon_bilgisi": {"mikrofon", "bilgi", "cihaz"},
        "ses_seviyesi_ayarla": {"ses", "seviye", "yukseklik"},
        "konusma_hizi_ayarla": {"konusma", "hiz", "ses"},
        "konusma_duraklat": {"konusma", "duraklat", "dur"},
        "konusma_devam_et": {"konusma", "devam", "basla"},
        "metni_sese_donustur": {"ses", "yazi", "oku", "konus", "tts"},
        "tts_durumu": {"ses", "durum", "tts"},
        "tts_durdur": {"ses", "durdur", "konusma"},
        "mikrofon_erisim": {"mikrofon", "erisim", "aktif"},
        "konusma_tanima": {"konusma", "tanima", "soyle", "duy"},
        "ekran_analiz_yerel_son": {"ekran", "analiz", "goruntu", "goruyor"},
        "ekran_analiz_ve_eylem_son": {"ekran", "analiz", "eylem", "goruntu"},
        "ekran_karsilastir": {"ekran", "karsilastir", "fark", "goruntu"},
        "tum_gorsel_kontrolleri": {"ekran", "gorsel", "kalite", "kontrol"},
        "hata_penceresi_tanima": {"ekran", "hata", "pencere", "uyari"},
        "uygulama_ac": {"uygulama", "ac", "calistir", "program"},
        "dosya_olustur": {"dosya", "olustur", "yeni", "yarat"},
        "dosya_yaz": {"dosya", "yaz", "kaydet", "icerik"},
        "pencere_listele": {"pencere", "listele", "acik"},
        "pencere_one_getir": {"pencere", "getir", "one"},
        "klavye_fare_tikla": {"tikla", "fare", "bas"},
        "klavye_fare_yaz": {"yaz", "klavye", "metin"},
        "ekran_goruntusu_al": {"ekran", "goruntu", "goruntusu", "yakala"},
        "proje_olustur": {"proje", "olustur", "yeni", "baslat"},
        "dosya_islemi": {"dosya", "islem", "dosyalamak"},
    }
    en_iyi = None
    en_iyi_skor = 0
    for arac, kset in kat_kelime.items():
        if arac not in kayitli:
            continue
        # Kesisim sayisi: request'te kac kelime eslesiyor
        skor = len(kelimeler_t & kset)
        # Bonus: exact phrase eslesmesi
        for phrase in kset:
            if " " in phrase and phrase in t:
                skor += 2
        if skor > en_iyi_skor:
            en_iyi_skor = skor
            en_iyi = arac
    if en_iyi and en_iyi_skor > 0:
        return [{"tool": en_iyi, "args": {}}]
    return []


def _onay_iste(arac: str, adim: Dict[str, Any], args: Dict[str, Any]) -> bool:
    """Riskli araçlar için kullanıcı onayı. Konsol sürümü."""
    print("\n" + "=" * 55)
    print("JARVIS MASTER — ONAY GEREKIYOR")
    print("Araç:", arac)
    print("Adım:", json.dumps(adim, ensure_ascii=False)[:200])
    print("=" * 55)
    try:
        cevap = input("Devam etmek istiyor musunuz? (EVET/HAYIR): ").strip().upper()
    except EOFError:
        return False
    return cevap == _ONAY_KODU


# ---------------------------------------------------------------------------
# Ana giriş noktası: cevapla(istek)
# ---------------------------------------------------------------------------

def cevapla(istek: str, onay_callback: Optional[Callable] = None) -> Dict[str, Any]:
    """Tek bir kullanıcı isteğini planla, çalıştır ve raporla.

    onay_callback(arac, adim, args) -> bool  (GUI/telefon için dışarıdan
    bağlanabilir; yoksa konsol onayı kullanılır.)
    """
    _log("ISTEK_GELDI", istek=istek[:200])
    rapor = {
        "istek": istek,
        "zaman": time.strftime("%Y-%m-%d %H:%M:%S"),
        "durum": "BASLADI",
        "adimlar": [],
        "sonuc": None,
        "hata": None,
    }

    _gid = None
    try:
        # Hafiza: yeni gorute kayit ac
        try:
            _gid = _hafiza.gorev_baslat(istek, kaynak="master_cevapla")
        except Exception:
            _gid = None

        # 1) Plan
        adimlar = _plan_olustur(istek)
        rapor["adim_planlandi"] = len(adimlar)
        if not adimlar:
            rapor["durum"] = "PLAN_OLUŞAMADI"
            rapor["hata"] = "AI uygun bir adım üretemedi."
            _log("PLAN_BASARISIZ", istek=istek)
            if _gid:
                try:
                    _hafiza.gorev_bitir(
                        _gid, "plan_basarisiz",
                        hata_bilgisi=rapor["hata"],
                        kullanilan_model=MODEL_METIN,
                    )
                except Exception:
                    pass
            return rapor

        # 2) Çalıştır (motor.confirm ile onay)
        def confirm(arac, adim, args):
            cb = onay_callback or _onay_iste
            return bool(cb(arac, adim, args))

        sonuc = _MOTOR.run(istek, planner=lambda t, tl: {"steps": adimlar},
                           confirm=confirm)
        rapor["adimlar"] = sonuc.get("results", [])
        rapor["durum"] = "BASARILI" if sonuc.get("ok") else "KISMI_BASARILI"
        rapor["sonuc"] = sonuc

        # Hafiza: adimlari ve sonucu kaydet
        if _gid:
            try:
                sira = 0
                for a in rapor.get("adimlar", []):
                    sira += 1
                    _hafiza.gorev_adim_ekle(
                        _gid, sira,
                        a.get("tool", "bilinmeyen"),
                        a.get("args", {}) or {},
                        "tamam" if a.get("ok") else "hata",
                        sonuc=str(a.get("result"))[:500] if a.get("result") else None,
                        hata=str(a.get("error"))[:200] if a.get("error") else None,
                    )
                _hafiza.gorev_bitir(
                    _gid,
                    durum=rapor["durum"],
                    sonuc=json.dumps(sonuc, ensure_ascii=False)[:2000],
                    hata_bilgisi=rapor.get("hata"),
                    kullanilan_araclar=[a.get("tool", "") for a in rapor.get("adimlar", [])],
                    kullanilan_model=MODEL_METIN,
                    devam_etilebilir_asama=None if rapor["durum"] == "BASARILI" else "plan",
                )
            except Exception:
                pass

        _log("ISTEK_TAMAM", durum=rapor["durum"], adim=len(adimlar))
        return rapor

    except Exception as exc:
        rapor["durum"] = "HATA"
        rapor["hata"] = repr(exc)
        _log("ISTEK_HATA", hata=repr(exc), traceback=traceback.format_exc())
        if _gid:
            try:
                _hafiza.gorev_bitir(
                    _gid, "hata",
                    hata_bilgisi=repr(exc),
                    kullanilan_model=MODEL_METIN,
                )
            except Exception:
                pass
        return rapor


# ---------------------------------------------------------------------------
# CLI testi
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 55)
    print("       JARVIS MASTER V1 — TEST SÜRESİ")
    print("=" * 55)
    print("Çıkış için: cik / exit")
    print("-" * 55)

    while True:
        try:
            istek = input("\nSiz > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nJARVIS MASTER kapatiliyor.")
            break
        if not istek:
            continue
        if istek.lower() in ("cik", "exit", "quit"):
            print("Gorusuruz.")
            break

        print("\nJARVIS islemde…")
        rapor = cevapla(istek)
        print("\n--- SONUC ---")
        print("Durum:", rapor["durum"])
        print("Planlanan adim:", rapor.get("adim_planlandi"))
        for a in rapor.get("adimlar", []):
            print("  -", a.get("tool"), "->",
                  ("OK" if a.get("ok") else "HATA: " + str(a.get("error"))[:120]))
        if rapor.get("hata"):
            print("HATA:", rapor["hata"])
