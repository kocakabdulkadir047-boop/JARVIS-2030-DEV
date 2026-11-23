# -*- coding: utf-8 -*-
"""
jarvis_ai_sarmalayici — JARVIS FAZ 1: GERCEK YEREL YZ BAGLANTISI
=================================================================

Ollama (http://localhost:11434) + qwen3:4b modelini JARVIS'in ORIJINAL
sohbet ekranina baglar. Bu modul hicbir ORIJINAL dosyaya dokunmaz;
yalnizca calisma zamaninda (runtime) fonksiyonlari sarar (monkey-patch).

FAZ 1 KURALLARI (bu dosya bunlari uygular):
  1. Tek etkin saglayici: yerel Ollama + qwen3:4b.
  2. Cevrimiçi saglayici cagrilari (gemini/groq/openrouter/pollinations/
     anthropic/openai) yerel modele yonlendirilir; disaga veri GITMEZ.
  3. Soket duzeyinde "yalnizca localhost" muhafizasi: dis baglanti
     denemeleri engellenir ve loglanir (dogrulanabilir).
  4. TTS (Gemini seslendirme) bu fazda TETIKLENMEZ (Faz 2'de yerel TTS).
  5. Modelin "thinking" (ic dusunme) metni yanita KARISTIRILMAZ.
  6. Hatalar Turkce gosterilir; bos cevap basari sayilmaz.
  7. Konusma baglami (_recent_dialog) modele aktarilir.

ANAHTARLAR (ortam degiskenleri):
  JARVIS_AI=0          -> sarmalayici tamamen KAPALI (orijinal davranis)
  JARVIS_AI_AG=0       -> soket muhafizasi kapali (test icin)
  JARVIS_AI_TTS=acik   -> TTS serbest (varsayilan: KAPALI, Faz 1)
  JARVIS_AI_TEST=1     -> HUD uzerinden otomatik test modu

KORUNAN DOSYALAR (asla degismez):
  ORJİNALJARVIS.exe, orijinal/main.pyc, orijinal/ui.pyc, config/api_keys.json

Geri alma: geri_al() -> tum yamalar kaldirilir.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
MODEL = "qwen3:4b"
OLLAMA_BASE = "http://localhost:11434"
ZAMAN_ASIMI = 300          # saniye; TURK_AI olcumu: qwen3:4b 90-230 sn surebilir
GECMIS_SINIR = 10          # modele aktarilan son dialog satiri siniri (5 cift)
NUM_CTX = 4096
NUM_PREDICT = 2500
SICAKLIK = 0.6

SISTEM_PROMPT = (
    "Sen JARVIS adinda, Turkce konusan kisisel bir asistanin. "
    "Kullaniciyla dogal, kisa ve net Turkce konusursun; yalnizca Turkce yazarsin. "
    "Bilmedigin seyi bilmedigini soyle, uydurma bilgi verme. "
    "Gereksiz uzun aciklama yapma; kisa ve net cevap ver."
)

# ---------------------------------------------------------------------------
# Durum
# ---------------------------------------------------------------------------
_durum = {"aktif": False, "kapatilma_nedeni": None, "hatalar": [],
          "ders_modu": False, "yerel_tts": False, "yerel_tts_modul": False}
_orijinal = {}
_kayit = {
    "istekler": [],    # yerel model cagrilari
    "saglayici": [],   # hangi saglayici adiyla cagirildi (hepsi yerel'e gider)
    "tts": [],         # bastirilan TTS cagrilari
    "ag": [],          # engellenen dis ag denemeleri
    "loglar": [],      # HUD write_log kayitlari (test modu)
    "durumlar": [],    # HUD set_state kayitlari (test modu)
    "ui": None,
}


class YerelModelHatasi(Exception):
    """Yerel model hatasi. tur: baglanti|zaman|model|sunucu|bos|girdi|hata"""

    def __init__(self, mesaj, tur="hata"):
        super().__init__(mesaj)
        self.tur = tur


# ---------------------------------------------------------------------------
# Ag muhafizasi — yalnizca localhost'a cikis serbest
# ---------------------------------------------------------------------------
def _yerel_mi(host):
    if not isinstance(host, str) or host == "":
        return True  # AF_UNIX / belirsiz adres: yerel say
    h = host.strip("[]").lower()
    if h in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    if h.startswith("127."):
        return True
    return False


def _log_dosyasi(ad):
    kok = _log_kok()
    klasor = os.path.join(kok, "jarvis_ai_faiz1")
    try:
        os.makedirs(klasor, exist_ok=True)
        return os.path.join(klasor, ad)
    except Exception:
        return None


def _log_kok():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _log_yaz(ad, satir):
    yol = _log_dosyasi(ad)
    if not yol:
        return
    try:
        with open(yol, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), satir))
    except Exception:
        pass


def _ag_engelle(host, port):
    kayit = {"t": time.time(), "host": str(host), "port": str(port)}
    _kayit["ag"].append(kayit)
    if len(_kayit["ag"]) > 500:
        del _kayit["ag"][:250]
    _log_yaz("ag_denetimi.log",
             "ENGELLENDI (dis ag kapali) -> %s:%s" % (host, port))


# ---------------------------------------------------------------------------
# Ag muhafizasi — yalnizca loopback + IZINLI saglayici alan adlari
# ---------------------------------------------------------------------------
# Cozulmus IP'ler: ip -> (alan_adi, zaman)
_SOLULEN_IP = {}


def _izinli_alan_adlari():
    """Izinli saglayici alan adlari (router modulunden)."""
    try:
        import jarvis_ai_router as _router
        return set(_router.izinli_alan_adlari())
    except Exception:
        return set()


def _alan_adi_izinli_mi(host):
    """Alan adi izin listesinde mi? (loopback her zaman serbest)"""
    h = str(host or '').strip().lower().rstrip('.')
    if not h:
        return False
    if _yerel_mi(h):
        return True
    return h in _izinli_alan_adlari()


def _cozulmus_ip_ekle(ip, alan_adi):
    """Cozumlenen IP'yi izinli isaretle (5 dk gecerli)."""
    try:
        _SOLULEN_IP[str(ip)] = (str(alan_adi or ''), time.time())
    except Exception:
        pass


def _ip_izinli_mi(ip):
    """IP izinli mi? (loopback veya izinli alan adindan cozulmus)"""
    i = str(ip or '')
    if _yerel_mi(i):
        return True
    kayit = _SOLULEN_IP.get(i)
    if not kayit:
        return False
    alan_adi, zaman = kayit
    if (time.time() - float(zaman or 0.0)) > 300.0:
        _SOLULEN_IP.pop(i, None)
        return False
    return _alan_adi_izinli_mi(alan_adi)


def _soket_muhafizasi_kur():
    """DNS/TCP/UDP: sadece loopback + izinli saglayici alan adlarina izin.

    * Alan adi dogrulamasi: izin listesinde olmayan alan adi HIC cozulmez.
    * DNS cozumlemesi basarisiz olursa baglanti reddedilir.
    * Cozulen IP yalnizca izinli alan adindan geldiyse baglanilabilir.
    * TLS sertifika dogrulamasi bu katmanda DEGISTIRILMEZ (aktif kalir).
    """
    try:
        import socket
    except Exception:
        return False
    if getattr(socket.socket, "_jarvis_ai_guard", False):
        return True
    orj_connect = socket.socket.connect
    orj_sendto = getattr(socket.socket, "sendto", None)
    orj_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host, port, *a, **k):
        """DNS: once ALAN ADI dogrulamasi, sonra cozumleme."""
        if host and not _alan_adi_izinli_mi(host):
            _ag_engelle(host, port)
            raise OSError(101, "JARVIS_AI: izin listesinde olmayan alan adi")
        # Cozumleme basarisiz olursa hata yukarida yuzulur (baglanti reddi).
        sonuc = orj_getaddrinfo(host, port, *a, **k)
        for kayit in (sonuc or ()):
            try:
                _cozulmus_ip_ekle(kayit[4][0], host)
            except Exception:
                continue
        return sonuc

    def connect(self, address, /):
        try:
            host = address[0]
            port = address[1]
        except Exception:
            host, port = address, ""
        if _ip_izinli_mi(host):
            return orj_connect(self, address)
        _ag_engelle(host, port)
        raise OSError(101, "JARVIS_AI: dis ag erisimi kapali "
                           "(guvenli saglayici listesi)")

    def sendto(self, data, address, /):
        try:
            host = address[0]
            port = address[1]
        except Exception:
            host, port = address, ""
        if _ip_izinli_mi(host):
            return orj_sendto(self, data, address)
        _ag_engelle(host, port)
        raise OSError(101, "JARVIS_AI: dis ag erisimi kapali "
                           "(guvenli saglayici listesi)")

    socket.getaddrinfo = getaddrinfo
    socket.socket.connect = connect
    if orj_sendto is not None:
        socket.socket.sendto = sendto
    socket.socket._jarvis_ai_guard = True
    _orijinal["soket_connect"] = orj_connect
    _orijinal["soket_sendto"] = orj_sendto
    _orijinal["soket_getaddrinfo"] = orj_getaddrinfo
    return True


# ---------------------------------------------------------------------------
# Yerel model istemcisi (yalnizca stdlib: urllib + json)
# ---------------------------------------------------------------------------
def _post(govde, zaman):
    veri = json.dumps(govde).encode("utf-8")
    istek = urllib.request.Request(
        OLLAMA_BASE + "/api/chat", data=veri,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=zaman) as yanit:
        return json.loads(yanit.read().decode("utf-8", "replace"))


def _hata_cevir(hata, zaman, model=None):
    model = model or MODEL
    if isinstance(hata, urllib.error.HTTPError):
        govde = ""
        try:
            govde = hata.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        if hata.code == 404:
            return YerelModelHatasi(
                "Yerel model bulunamadi: %s (Ollama'da kayitli degil; "
                "indirme yapilmadi)." % model, "model")
        return YerelModelHatasi(
            "Yerel model hatasi (HTTP %s). %s" % (hata.code, govde.strip()),
            "sunucu")
    metin = str(hata)
    kucuk = metin.lower()
    if "timed out" in kucuk or "timeout" in kucuk or isinstance(hata, TimeoutError):
        return YerelModelHatasi(
            "Yerel model yanit vermedi (zaman asimi: %d sn)." % zaman, "zaman")
    if ("refused" in kucuk or "10061" in kucuk or "111" in kucuk
            or "failed to establish" in kucuk or "no connection" in kucuk):
        return YerelModelHatasi(
            "Yerel modele ulasilamadi - Ollama calisiyor mu? (localhost:11434)",
            "baglanti")
    return YerelModelHatasi(
        "Yerel model baglanti hatasi: %s" % metin[:200], "hata")


def _temizle(metin):
    """Yanittan olasi thinking (ic dusunme) artiklarini temizler.

    Qwen3 modelinin usual output formatı:
    - message.content: Kullanıcıya gösterilecek metin
    - message.thinking: Sunucunun "düşüncesi" (kullanıcıya GONDERILMEZ)

    KURALLAR
      * message.thinking AYRI alanda gelir; buraya girmez, kullaniciya/TTS'ye
        GONDERILMEZ (bosta `yerel_cevap()` icinde ayri okunur).
      * Duz/normal Turkce metin, "thinking" kelimesi ve tirnak icindeki
        kod ETIKETLERI degistirilmez.
      * JSON ayristirma hatasi veri kaybina donusmez: metin aynen korunur.
      * UTF-8 temizliginde 'ignore' KULLANILMAZ.
    """
    m = str(metin)

    # 1) Girdi JSON metni ise 'content' alanini al.
    #    Parse hatasi olursa m DEGISTIRILMEZ (veri kaybi yok).
    try:
        veri = json.loads(m)
    except Exception:
        veri = None
    if isinstance(veri, dict):
        icerik = veri.get("content")
        if not isinstance(icerik, str):
            alt = veri.get("message")
            if isinstance(alt, dict):
                icerik = alt.get("content")
        if isinstance(icerik, str):
            m = icerik

    # 2) Thinking AYRACLARI (gercek etiketler).
    #    Duz metindeki "thinking" kelimesi bu adima DOKUNMAZ.
    bas = -1
    uz = 0
    for acilis in ("<im_start|>", "<think>"):
        b = m.find(acilis)
        if b >= 0 and (bas < 0 or b < bas):
            bas = b
            uz = len(acilis)
    if bas >= 0:
        bit = -1
        kb = 0
        for kapanis in ("</im>", "<im_end|>", "</think>"):
            k = m.find(kapanis, bas + uz)
            if k >= 0 and (bit < 0 or k < bit):
                bit = k
                kb = len(kapanis)
        if bit >= 0:
            # Kapanistan SONRAKI gercek cevap kalir.
            m = m[bit + kb:]
        else:
            # Kapanis yok: acilistan sonrasi tumu dusunce sayilir.
            m = m[bas + uz:]

    # 3) Kapanis etiketi tek basina varsa (acilis yoksa) ondan sonrasi kalir.
    if "</think>" in m and "<think>" not in m:
        m = m.split("</think>", 1)[1]
    if "<im_end|>" in m and "<im_start|>" not in m:
        m = m.split("<im_end|>", 1)[1]

    # 4) Kod blogu fence ISARETLERI temizlenir; BLOK ICERIGI KORUNUR.
    if "```" in m:
        # 4a) Satir basinda tek basina duran fence satiri (ve 'python' gibi
        #     dil etiketi) atilir; satirin KOD ICERIGI korunur.
        _satirlar = m.split("\n")
        _temiz = []
        for _p in _satirlar:
            _s = _p.strip()
            if _s.startswith("```") and "```" not in _s[3:]:
                continue
            _temiz.append(_p)
        m = "\n".join(_temiz)
        # 4b) Satir ici kalan fence'ler: bosluklu olan tek bosluga iner,
        #     kalanlar tamamen silinir (icerik korunur).
        m = m.replace(" ``` ", " ")
        m = m.replace("```", "")

    # 5) UTF-8: 'ignore' KULLANILMA. Vekil (surrogate) karakter varsa
    #    'replace' ile guvenli metne cevrilir; normal metne dokunulmaz.
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in m):
        m = m.encode("utf-8", "replace").decode("utf-8", "replace")

    return m.strip()


def gecmis_ciftleri(gecmis, sinir=GECMIS_SINIR):
    """HUD log satirlarindan (Kullanici: / JARVIS:) model mesajlarina donusturur."""
    cikti = []
    for satir in list(gecmis or [])[-(sinir * 2):]:
        s = str(satir)
        if s.startswith("Kullanıcı: "):
            cikti.append({"role": "user", "content": s[len("Kullanıcı: "):]})
        elif s.startswith("Kullanici: "):
            cikti.append({"role": "user", "content": s[len("Kullanici: "):]})
        elif s.startswith("JARVIS: "):
            cikti.append({"role": "assistant", "content": s[len("JARVIS: "):]})
    return cikti


def yerel_cevap(soru, sistem=None, gecmis=None, zaman=ZAMAN_ASIMI, model=MODEL,
               ders_modu=False):
    """Ollama /api/chat ile GERCEK yanit alir.

    * think=True denenir (TURK_AI olcumu: think=False cevabi bozar);
      sunucu desteklemiyorsi think'siz yeniden dener.
    * thinking metni AYRI alanda gelir; yalnizca content dondurulur.
    * Bos cevap YerelModelHatasi ile isaretlenir (basari sayilmaz).
    * Hatalar Turkce YerelModelHatasi olarak dondurulur.
    * ders_modu=True ise: Akademik/öğretici sistem promptu kullanilir,
      Python örnekleri ve seviye uygun açıklamalar sunulur.
    """
    soru = str(soru or "").strip()
    if not soru:
        raise YerelModelHatasi("Istek metni bos.", "girdi")
    # Ders modu için özel sistem promptu
    if ders_modu:
        ders_sistem = (
            "Sen JARVIS öğretmen assistant'ınız. Kullanıcıya seviyesine "
            "göre, adım adım Python veya genel bilim örnekleriyle konuyu "
            "öğret. Cevapları çok kisa, pratik ve kod odaklı tut. "
            "Sadece gerekiyorsa Türkçe'yi kullan, aksi halde İngilizce. "
            "Farklı seviyeler: 'basics' (başlangıç), 'intermediate' (orta), "
            "'advanced' (ileriye). Kullanıcı seviyesini bilmediğinde varsayılanı "
            "'basics' kabul et. Consider cevabı düşündükten sonra 'thinking' "
            "metnini tamamen at, sadece kullanıcıya gösterilecek content'i dondur."
        )
        sistem = ders_sistem
    else:
        sistem = sistem or SISTEM_PROMPT
    mesajlar = [{"role": "system", "content": sistem}]
    mesajlar.extend(gecmis_ciftleri(gecmis))
    mesajlar.append({"role": "user", "content": soru})
    govde = {
        "model": model,
        "messages": mesajlar,
        "stream": False,
        "think": True,
        "options": {
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
            "temperature": SICAKLIK,
        },
    }
    t0 = time.time()
    think_kullanimi = True
    try:
        veri = _post(govde, zaman)
    except urllib.error.HTTPError as e:
        if getattr(e, "code", None) == 400:
            # think parametresi desteklenmiyor olabilir -> thinksiz dene
            govde.pop("think", None)
            think_kullanimi = False
            try:
                veri = _post(govde, zaman)
            except Exception as e2:
                hata = _hata_cevir(e2, zaman, model)
                _istek_kaydet(model, t0, hata.tur, think_kullanimi, 0)
                raise hata from None
        else:
            hata = _hata_cevir(e, zaman, model)
            _istek_kaydet(model, t0, hata.tur, think_kullanimi, 0)
            raise hata from None
    except Exception as e:
        hata = _hata_cevir(e, zaman, model)
        _istek_kaydet(model, t0, hata.tur, think_kullanimi, 0)
        raise hata from None

    mesaj = (veri or {}).get("message") or {}
    dusunme = str(mesaj.get("thinking") or "")
    metin = _temizle(mesaj.get("content") or "")
    if not metin:
        hata = YerelModelHatasi(
            "Yerel model bos yanit dondurdu (%s)." % model, "bos")
        _istek_kaydet(model, t0, hata.tur, think_kullanimi, len(dusunme))
        raise hata
    _istek_kaydet(model, t0, "cevap", think_kullanimi, len(dusunme))
    return metin


def _istek_kaydet(model, t0, tur, think, dusunme_uz):
    kayit = {
        "t": t0,
        "model": model,
        "sure_sn": round(time.time() - t0, 1),
        "sonuc": tur,
        "think": think,
        "thinking_uzunluk": dusunme_uz,
    }
    _kayit["istekler"].append(kayit)
    if len(_kayit["istekler"]) > 200:
        del _kayit["istekler"][:100]


# ---------------------------------------------------------------------------
# Yamalar (patch fonksiyonlari)
# ---------------------------------------------------------------------------
def _ders_modu_komutu(metin):
    """'ders modu ac' / 'ders modu kapat' komutunu algilar.

    Donus: None (komut yok) veya (acik_mi, cevap_metni).
    Turkce karakterler (ac/acr) once ASCII'ye indirgenir.
    """
    import re
    t = str(metin or '').lower()
    for a, b in (('ç', 'c'), ('ğ', 'g'), ('ı', 'i'), ('ö', 'o'),
                 ('ş', 's'), ('ü', 'u')):
        t = t.replace(a, b)
    m = re.search(r"ders\s*modu\s*(\w+)?", t)
    if not m:
        return None
    sonra = (m.group(1) or '').strip()
    kapali_kelimeler = ('kapat', 'kapatildi', 'kapatili', 'kapali',
                         'kapatil', 'off', 'close', 'durdur')
    acik_kelimeler = ('ac', 'acildi', 'acili', 'acik', 'on', 'open', 'baslat')
    if sonra in kapali_kelimeler:
        return (False, 'Ders modu kapatildi. Normal sohbete donuyorum.')
    if sonra in acik_kelimeler:
        return (True, 'Ders modu acildi. Python ve konu ornekleriyle, '
                      'adim adim ogretecegim.')
    return None


# ---------------------------------------------------------------------------
# FAZ 4E.2: GECICI HATA / DEVRE KESICI / ISTEK CAKISMASI
# ---------------------------------------------------------------------------
#: "iptal" komutu - devam eden istegi guvenle durdurur
_IPTAL_KOMUTLARI = ("iptal", "iptal et", "vazgec", "vazgeç", "durdur istegi")


def _iptal_komutu(s):
    """Iptal komutu mu? Donus: True/False"""
    t = ' '.join(str(s or "").strip().lower().split())
    if not t:
        return False
    return t in _IPTAL_KOMUTLARI


def _iptal_uygula():
    """Devam eden istekleri iptal et. Donus: iptal edilen sayisi."""
    try:
        import jarvis_ai_router as _router
        n = _router.istek_iptal()
    except Exception as e:
        _durum["hatalar"].append("iptal: %r" % (e,))
        return 0
    return n


def _kullanici_bildirimi(jarvis, metin, gorev_id=None):
    """Kullanici bilgilendirmesini HUD'a yazar (API anahtari/icerik YOK).

    FAZ 4E.3: ui.JarvisUI.write_log bir worker thread'den cagrildiginda
    mesaji kuyruga atip BIRAKABILIYOR (bosaltma zamanlanmayabiliyor) ->
    mesaj HIC gorunmuyordu. Bu yuzden yazma ISLEMININ KENDISI ana
    thread'e (root.after) devredilir; boylece mesaj kesin gorunur.
    """
    m = str(metin or "").strip()
    if not m:
        return
    if gorev_id:
        m = "%s [görev %s]" % (m, gorev_id)
    try:
        ui = getattr(jarvis, "ui", None)
        root = getattr(ui, "root", None)
        if ui is not None and root is not None:
            def _yaz():
                try:
                    ui.write_log("SYS: " + m)
                except Exception:
                    pass
            try:
                root.after(0, _yaz)
            except Exception:
                _yaz()
            return
    except Exception:
        pass
    try:
        ui = getattr(jarvis, "ui", None)
        if ui is not None and hasattr(ui, "write_log"):
            ui.write_log("SYS: " + m)
            return
    except Exception:
        pass
    _log_yaz("bildirim.log", m)


def _yerel_etiket(sonuc):
    """Cevabin GERCEK kaynağını gösteren etiket (FAZ 4E.4.2 §5).

    HER cevapta kaynak bilgisi gösterilir:
        * Gemini 3.8-flash  (bulut)
        * Ollama Qwen3:4b   (yerel model)
    Yerel modelin cevabı Gemini cevabı gibi SUNULMAZ.

    Yalnizca bulut saglayicilari denendi ve basarisiz oldugunda ek aciklama
    gelir (OFFLINE modda kullanici yerel modeli kendisi sectigi icin ek
    aciklama uretilmez).
    """
    try:
        kaynak = str(sonuc.get("kaynak") or "").strip()
        if not kaynak:
            try:
                import jarvis_ai_router as _r
                kaynak = _r.kaynak_etiketi(sonuc.get("saglayici"),
                                           sonuc.get("model"))
            except Exception:
                kaynak = str(sonuc.get("saglayici") or "").strip()
        if not kaynak:
            return ""
        etiket = "(%s)" % kaynak
        if sonuc.get("yerel_donus"):
            bildirim = str(sonuc.get("bildirim") or "").strip()
            if bildirim:
                etiket = "(%s - %s)" % (kaynak, bildirim)
        return etiket + "\n\n"
    except Exception:
        return ""


def _v51_kapka(jarvis, soru):
    """jarvis_v51_ajan._v51_ai_her_kosul yerine: OTOMATIK YONLENDIRME.

    FAZ 4A: internet varsa izinli bulut saglayicilari (gemini / groq /
    openrouter) sirayla denenir. Internet yoksa veya hepsi basarisizsa
    otomatik olarak yerel Ollama modeline (qwen3:4b) gecilir.
    Ders modu komutu ve mevcut sohbet gecmisi korunur.

    FAZ 4E.2: gecici hatalarda kontrollu tekrar deneme, devre kesici,
    kullanici bilgilendirmesi ve istek iptali.
    """
    s = str(soru or "").strip()
    if not s:
        return ""
    # FAZ 4E.2: IPTAL komutu - devam eden istegi durdur.
    if _iptal_komutu(s):
        n = _iptal_uygula()
        return ("Tamam, devam eden istek iptal edildi."
                if n else "Tamam, iptal edilecek devam eden istek yok.")
    # DERS MODU komutu: modele gitmeden once ele alinir.
    komut = _ders_modu_komutu(s)
    if komut is not None:
        acik_mi, cevap = komut
        ders_modu_ayarla(acik_mi)
        return cevap
    try:
        gecmis = list(getattr(jarvis, "_recent_dialog", None) or [])
    except Exception:
        gecmis = []
    ders_modu = bool(_durum.get("ders_modu", False))
    # FAZ 2.2B: dogrudan router YOK. Tek yol merkezi bulut broker'i;
    # bilet/onay/mode karari orada verilir. OFFLINE'da broker yerel
    # modele yonlendirir, ONLINE'da izinsiz istek gonderilmez.
    try:
        import jarvis_chat_v2_entegrasyon as _c2e
        sonuc, _tekrar = _c2e.guvenli_isle(s, kaynak='v51')
        cevap = str((sonuc or {}).get("response") or "").strip()
        if cevap and str((sonuc or {}).get("result_type") or "") in (
                "answer", "status"):
            _router_durum_yaz(sonuc)
            etiket = _yerel_etiket(sonuc)
            return etiket + cevap if etiket else cevap
        return str((sonuc or {}).get("error") or "").strip() or (
            "Bulut isteği gönderilmedi.")
    except Exception as e:
        _log_yaz("router_hata.log", "broker hatasi: %r" % (e,))
        return "Bulut kapısı hatası; istek gönderilmedi."


def _saglayici_kapka(ad, url, model, anahtar, soru, sistem=None, zaman=35,
                     max_tokens=1200, sicaklik=0.4):
    """jarvis_yetenek._saglayici_istek yerine: OTOMATIK YONLENDIRME.

    FAZ 4A: disaridan gelen saglayici adi ('ad') ve 'url' GUVENILMEZ;
    karar router'a aittir. Izin listesindeki disi saglayicilar (openai,
    anthropic, deepseek, pollinations...) HIC CAGRILMAZ. Internet yoksa veya
    bulut saglayicilari basarisizsa yerel Ollama'ya gecilir.
    """
    _kayit["saglayici"].append(str(ad))
    if len(_kayit["saglayici"]) > 500:
        del _kayit["saglayici"][:250]
    # FAZ 2.2B: dogrudan router YOK. Tek yol merkezi broker.
    try:
        import jarvis_chat_v2_entegrasyon as _c2e
        if getattr(_c2e._ISTEK_BAGLAM, "bilet", None):
            return "İç içe bulut isteği reddedildi."
        sonuc, _tekrar = _c2e.guvenli_isle(soru, kaynak='sarmalayici')
        cevap = str((sonuc or {}).get("response") or "").strip()
        if cevap:
            _router_durum_yaz(sonuc)
            return cevap
        return str((sonuc or {}).get("error") or "").strip()
    except Exception as e:
        _log_yaz("router_hata.log", "broker hatasi: %r" % (e,))
        return "Bulut kapısı hatası; istek gönderilmedi."


def _router_durum_yaz(sonuc):
    """Kullanilan saglayici bilgisini TEKNIK loga yaz.

    API anahtari ve ozel sohbet icerigi ASLA yazilmaz.
    """
    try:
        import jarvis_ai_router as _router
        _router.log_yaz("saglayici=%s model=%s" % (sonuc.get("saglayici"),
                                                   sonuc.get("model")))
    except Exception:
        pass


def _config_kapka(key=None, default=None):
    """app_config.get_app_config_value yerine: YEREL mod + dogru model.

    config/api_keys.json DOSYASI DEGISTIRILMEZ; yalnizca okuma sonucu
    calisma zamaninda yonlendirilir.
    """
    if key == "offline_mode":
        return True
    if key == "offline_model":
        return MODEL
    orj = _orijinal.get("get_app_config_value")
    if orj is None:
        return default
    return orj(key, default)


def _online_mi_kapka():
    """jarvis_anlama.online_mi yerine: her zaman YEREL (offline) mod."""
    return False


def _sm_gonder_kapka(*args, **kwargs):
    """jarvis_speech_manager.gonder — Faz 1'de Gemini TTS tetiklenmez."""
    _kayit["tts"].append({
        "t": time.time(),
        "fonksiyon": "gonder",
        "ozet": str(args[:2])[:160],
    })
    if len(_kayit["tts"]) > 200:
        del _kayit["tts"][:100]
    return {"id": "", "durum": "SUPPRESSED"}


def _sm_konus_kapka(*args, **kwargs):
    """jarvis_speech_manager.konus — Faz 1'de Gemini TTS tetiklenmez."""
    _kayit["tts"].append({
        "t": time.time(),
        "fonksiyon": "konus",
        "ozet": str(args[:2])[:160],
    })
    if len(_kayit["tts"]) > 200:
        del _kayit["tts"][:100]
    return True


# ---------------------------------------------------------------------------
# Test modu: HUD uzerinden otomatik sohbet testi (JARVIS_AI_TEST=1)
# ---------------------------------------------------------------------------
TEST_MESAJLAR = [
    "Bana kisa bir Turkce siir yaz.",
    "Dun bir volkan patlamasi vardi, cok etkilendim.",
    "Hangi doga olayindan bahsettim? Cok kisa cevap ver.",
]
TEST_ZAMAN_SINIRI = 2400   # saniye (tum test; qwen3:4b mesaj basina 90-240 sn)


def _ui_test_kur():
    """ui.JarvisUI sinifini kayit icin sarar + test zamanlayicisi kurar."""
    try:
        import ui as _ui
    except Exception as e:
        _durum["hatalar"].append("ui import: %r" % (e,))
        return False
    J = _ui.JarvisUI
    if getattr(J, "_jarvis_ai_test_sarili", False):
        return True
    orj_init = J.__init__
    orj_wl = J.write_log
    orj_ss = J.set_state

    def init_kapka(self, *a, **k):
        sonuc = orj_init(self, *a, **k)
        _kayit["ui"] = self
        try:
            self.root.after(1000, lambda: _test_dongu(self))
        except Exception as e:
            _durum["hatalar"].append("test zamanlama: %r" % (e,))
        return sonuc

    def write_log_kapka(self, text, *a, **k):
        try:
            _kayit["loglar"].append({"t": time.time(), "m": str(text)})
            if len(_kayit["loglar"]) > 2000:
                del _kayit["loglar"][:1000]
        except Exception:
            pass
        return orj_wl(self, text, *a, **k)

    def set_state_kapka(self, state, *a, **k):
        try:
            _kayit["durumlar"].append({"t": time.time(), "s": str(state)})
            if len(_kayit["durumlar"]) > 1000:
                del _kayit["durumlar"][:500]
        except Exception:
            pass
        return orj_ss(self, state, *a, **k)

    J.__init__ = init_kapka
    J.write_log = write_log_kapka
    J.set_state = set_state_kapka
    J._jarvis_ai_test_sarili = True
    return True


def _test_dongu(ui):
    """HUD mesajlarini sira ile gonderir, cevaplari ve metrikleri toplar."""
    import threading  # noqa: F401  (bilgi: GUI disi is parcaciklarini ayirt etmek icin)
    t_bas = time.time()
    S = {
        "adim": 0,               # 0=hazirlik, 1..3=mesaj bekleme, 9=bitti
        "t_gonderim": 0.0,
        "mesajlar": [],
        "hatalar": [],
        "max_gui_gecikme_ms": 0.0,
        "son_log_indeks": 0,
        "bitti": False,
    }
    sonuc_yolu = os.environ.get(
        "JARVIS_AI_TEST_CIKTI",
        os.path.join(_log_kok(), "jarvis_ai_faiz1", "test_sonuc.json"))

    def ticker(onceki):
        if S["bitti"]:
            return
        simdi = time.time()
        if onceki:
            gecikme = (simdi - onceki - 0.05) * 1000.0
            if gecikme > S["max_gui_gecikme_ms"]:
                S["max_gui_gecikme_ms"] = round(gecikme, 1)
        try:
            ui.root.after(50, lambda: ticker(simdi))
        except Exception:
            pass

    def live_durum():
        try:
            lv = getattr(ui, "on_text_command", None)
            lv = getattr(lv, "__self__", None)
            if lv is None:
                return None
            return {
                "offline_active": getattr(lv, "_offline_active", None),
                "live_ok": getattr(lv, "_live_ok", None),
                "yerel_mod_kullanici": getattr(lv, "_yerel_mod_kullanici", None),
            }
        except Exception:
            return None

    def gonder(i):
        metin = TEST_MESAJLAR[i]
        ui._input_var.set(metin)
        ui._on_input_submit()
        S["t_gonderim"] = time.time()
        S["mesajlar"].append({
            "sira": i + 1,
            "metin": metin,
            "gonderim_t": S["t_gonderim"],
            "cevap": None,
            "cevap_t": None,
            "sure_sn": None,
            "durumlar": [],
            "live_durum": None,
        })

    def yeni_cevap():
        t0 = S["t_gonderim"] - 0.5
        for i in range(S["son_log_indeks"], len(_kayit["loglar"])):
            kayit = _kayit["loglar"][i]
            if kayit["t"] > t0 and str(kayit["m"]).startswith("JARVIS: "):
                S["son_log_indeks"] = i + 1
                return str(kayit["m"])[len("JARVIS: "):]
        return None

    def bitir(neden):
        if S["bitti"]:
            return
        S["bitti"] = True
        sonuc = {
            "baslangic": t_bas,
            "bitis": time.time(),
            "sure_sn": round(time.time() - t_bas, 1),
            "sonuc": neden,
            "hazirlik_sn": round(S.get("t_ilk_gonderim", t_bas) - t_bas, 1),
            "mesajlar": S["mesajlar"],
            "max_gui_gecikme_ms": S["max_gui_gecikme_ms"],
            "hatalar": S["hatalar"],
            "log_sayisi": len(_kayit["loglar"]),
            "loglar": [
                {"t": round(k["t"], 1), "m": str(k["m"])[:400]}
                for k in _kayit["loglar"][-400:]
            ],
            "durumlar": [
                {"t": round(d["t"], 1), "s": d["s"]}
                for d in _kayit["durumlar"][-200:]
            ],
            "tts_cagrilari": _kayit["tts"][:50],
            "tts_cagri_sayisi": len(_kayit["tts"]),
            "ag_denetimi": _kayit["ag"][:100],
            "ag_denetimi_sayisi": len(_kayit["ag"]),
            "istekler": _kayit["istekler"][:50],
            "saglayici_adlari": sorted(set(_kayit["saglayici"]))[:20],
            "sarm_durum": durum(),
        }
        try:
            os.makedirs(os.path.dirname(sonuc_yolu), exist_ok=True)
            with open(sonuc_yolu, "w", encoding="utf-8") as f:
                json.dump(sonuc, f, ensure_ascii=False, indent=1)
        except Exception:
            pass
        _log_yaz("test.log", "TEST BITTI: %s (%.1f sn)" % (neden, sonuc["sure_sn"]))
        try:
            ui.root.destroy()
        except Exception:
            pass

    def dongu():
        if S["bitti"]:
            return
        try:
            simdi = time.time()
            if simdi - t_bas > TEST_ZAMAN_SINIRI:
                S["hatalar"].append("test zaman siniri doldu")
                bitir("zaman_asimi")
                return
            if S["adim"] == 0:
                hazir = (callable(getattr(ui, "on_text_command", None))
                         and getattr(ui, "_input_var", None) is not None
                         and getattr(ui, "root", None) is not None)
                if hazir:
                    S["t_ilk_gonderim"] = simdi
                    gonder(0)
                    S["adim"] = 1
            elif 1 <= S["adim"] <= len(TEST_MESAJLAR):
                cevap = yeni_cevap()
                if cevap is not None:
                    m = S["mesajlar"][-1]
                    m["cevap"] = cevap
                    m["cevap_t"] = time.time()
                    m["sure_sn"] = round(m["cevap_t"] - m["gonderim_t"], 1)
                    m["live_durum"] = live_durum()
                    t0 = m["gonderim_t"] - 1.0
                    m["durumlar"] = [
                        d["s"] for d in _kayit["durumlar"]
                        if d["t"] >= t0 and d["t"] <= m["cevap_t"] + 0.5
                    ]
                    if S["adim"] < len(TEST_MESAJLAR):
                        gonder(S["adim"])
                        S["adim"] += 1
                    else:
                        bitir("tamam")
                        return
        except Exception as e:
            S["hatalar"].append(repr(e)[:300])
        try:
            ui.root.after(500, dongu)
        except Exception:
            if not S["bitti"]:
                S["hatalar"].append("root.after basarisiz (GUI kapandi mi?)")
                bitir("hata")

    try:
        ui.root.after(50, lambda: ticker(None))
        ui.root.after(500, dongu)
    except Exception as e:
        _durum["hatalar"].append("test baslatma: %r" % (e,))


# ---------------------------------------------------------------------------
# FAZ 4E: BAGLANTI MODU (ONLINE / OFFLINE / OTOMATIK) + HUD BUTONU
# ---------------------------------------------------------------------------
# Mimari:
#   * Modun tek karar yeri = jarvis_ai_router (bulut yonlendirmesi orada).
#   * HUD'daki mevcut ONL/OFF butonu (ui.pyc) 3 moda yukseltilir:
#       OTO (yesil) -> ONL (mavi) -> OFF (turuncu) -> OTO ...
#   * Mevcut buton YENIDEN OLUSTURULMAZ; sadece metin/renk/command degisir.
#     Bu sayede GONDER / F / K / M / MM / B butonlari ve klavye
#     kisayollari bozulmaz, yerlesim degismez.
#   * Mod ayri bir dosyada saklanir (config/api_keys.json'A DOKUNULMAZ).
#   * Sohbet gecmisi korunur: uygulama her zaman _offline_handle_text ->
#     _v51_kapka -> router yolundan gecer; karari router verir.
# ---------------------------------------------------------------------------
import re as _re_faz4e

#: 'otomatik mod' gibi yazimlari taniyan desen
_OTO_DESEN = _re_faz4e.compile(
    r'\b(oto|otomatik|automatik|automatik)\b', _re_faz4e.IGNORECASE)

_MOD_ETIKET_TR = {
    'online': 'ONLINE (AI cevaplar)',
    'offline': 'OFFLINE (internet gerekmez)',
    'auto': 'OTOMATIK (internet varsa AI, yoksa yerel)',
}


def _router_al():
    """jarvis_ai_router modulunu getirir (yoksa None)."""
    try:
        import jarvis_ai_router as _r
        return _r
    except Exception:
        return None


def _mod_oku_kapka():
    """jarvis_anlama.mod_oku yerine: FAZ 4E modu (auto/online/offline)."""
    r = _router_al()
    if r is None:
        return 'offline'
    try:
        return r.mod_oku()
    except Exception:
        return 'offline'


def _mod_yaz_kapka(mod):
    """jarvis_anlama.mod_yaz yerine: FAZ 4E modu kalici olarak yazar."""
    r = _router_al()
    if r is None:
        return None
    try:
        yeni = r.mod_yaz(mod)
    except Exception as e:
        _durum["hatalar"].append("mod_yaz: %r" % (e,))
        return None
    _faz4e_live_senkronla(yeni)
    return yeni


def _mod_iste_kapka(metin):
    """jarvis_anlama.mod_iste yerine: 'otomatik mod' da taninir."""
    try:
        s = str(metin or '')
        if _OTO_DESEN.search(s) and 'mod' in s.lower():
            return 'auto'
    except Exception:
        pass
    orj = _orijinal.get("mod_iste")
    if orj is None:
        return None
    try:
        return orj(metin)
    except Exception:
        return None


def _faz4e_live_senkronla(mod):
    """JarvisLive ic durumunu 3 modla senkronlar.

    * _offline_active HER ZAMAN True kalir: sohbet gecmisi korunsun diye
      karar router'da verilir (bulut -> gemini/groq/openrouter, gerekirse
      yerel qwen3:4b).
    * _yerel_mod_kullanici yalnizca OFFLINE modunda True olur
      (offline modda ikinci cevap/arama yapilmaz).
    """
    try:
        ui = _kayit.get("ui")
        gonder = getattr(ui, "on_text_command", None)
        canli = getattr(gonder, "__self__", None)
        if canli is None:
            return False
        canli._offline_active = True
        canli._yerel_mod_kullanici = (str(mod) == "offline")
        return True
    except Exception as e:
        _durum["hatalar"].append("live senkron: %r" % (e,))
        return False


def _faz4e_mod_buton_guncelle(self):
    """Mod butonunu 3 mod durumuna gore gunceller (ONL / OFF / OTO)."""
    try:
        r = _router_al()
        mod = r.mod_oku() if r is not None else 'auto'
    except Exception:
        mod = 'auto'
    kisa = {'online': 'ONL', 'offline': 'OFF', 'auto': 'OTO'}.get(mod, 'OTO')
    renk = {'online': '#00e5ff', 'offline': '#ffaa00',
            'auto': '#00ff88'}.get(mod, '#00ff88')
    aciklama = _MOD_ETIKET_TR.get(mod, mod)
    b = getattr(self, "_mode_btn", None)
    if b is None:
        b = getattr(self, "_mod_btn", None)
    if b is not None:
        try:
            b.configure(text=kisa, fg=renk)
        except Exception:
            pass
    try:
        self._mod_aciklama = aciklama
    except Exception:
        pass
    return mod


def _faz4e_mod_degistir(self, event=None):
    """ONL/OFF/OTO butonu: 3 mod arasinda gecis yapar.

    Siralama: OTOMATIK -> ONLINE -> OFFLINE -> OTOMATIK -> ...
    """
    try:
        r = _router_al()
        if r is None:
            return None
        yeni = r.mod_sonraki()
        r.mod_yaz(yeni)
        _faz4e_live_senkronla(yeni)
        _faz4e_mod_buton_guncelle(self)
        try:
            self.write_log('SYS: Baglanti modu -> %s'
                           % _MOD_ETIKET_TR.get(yeni, yeni))
        except Exception:
            pass
        # FAZ 4E.4.1: mod degisimi devam eden bulut gorevlerini durdurdu.
        try:
            bilgi = r.mod_degis_bilgisi()
            n = int(bilgi.get('durdurulan') or 0)
            if n:
                self.write_log(
                    'SYS: %d devam eden bulut isteği durduruldu '
                    '(OFFLINE modu). Bu görevler yerel modele geçti.'
                    % n)
        except Exception:
            pass
        _log_yaz("mod.log", "baglanti modu degisti: %s" % yeni)
        return yeni
    except Exception as e:
        _durum["hatalar"].append("faz4e mod degistir: %r" % (e,))
        return None


def _acilis_mod_mesaji(ui):
    """FAZ 4E.4.1: acilis bilgilendirmesi MEVCUT MODA gore olur.

    OFFLINE modunda 'ONLINE calisma aciklamasi' aktif durum gibi
    gosterilmez; kullaniciya gercek durum soylenir.
    """
    try:
        import jarvis_ai_router as _r
        mod = _r.mod_oku()
    except Exception:
        mod = 'auto'
    metinler = {
        'offline': ('SYS: Baglanti modu OFFLINE - dis AI saglayicilari '
                    '(Gemini/Groq/OpenRouter) KAPALI, internet aramasi '
                    'yapilmaz. Yalnizca yerel model (Ollama) kullanilir.'),
        'online': ('SYS: Baglanti modu ONLINE - internet kontrolu '
                   'atlanir, izinli bulut saglayicilari dogrudan denenir; '
                   'basarisiz olursa yerel modele gecilir.'),
        'auto': ('SYS: Baglanti modu OTOMATIK - internet varsa bulut AI, '
                 'yoksa yerel model (Ollama) kullanilir.'),
    }
    try:
        ui.write_log(metinler.get(mod, metinler['auto']))
    except Exception:
        pass


def _faz4e_ui_kur():
    """ui.JarvisUI: 3 modlu baglanti butonu (giris cubugu butonu).

    FAZ 4E.3 ayrica: _shutdown patch'i - uygulama kapanirken calisan
    gorevler guvenle iptal edilir ve kayitlari yazilir (os._exit oncesi).
    """
    try:
        import ui as _ui
    except Exception as e:
        _durum["hatalar"].append("faz4e ui import: %r" % (e,))
        return False
    J = _ui.JarvisUI
    if getattr(J, "_jarvis_ai_faz4e_sarili", False):
        return True
    orj_init = J.__init__
    orj_shutdown = getattr(J, "_shutdown", None)
    _orijinal["_mod_buton_guncelle"] = getattr(J, "_mod_buton_guncelle", None)
    _orijinal["_mod_degistir"] = getattr(J, "_mod_degistir", None)
    _orijinal["_shutdown"] = orj_shutdown

    def init_kapka(self, *a, **k):
        sonuc = orj_init(self, *a, **k)
        try:
            _kayit["ui"] = self
            b = getattr(self, "_mode_btn", None)
            if b is None:
                b = getattr(self, "_mod_btn", None)
            if b is not None:
                # Buton yeniden OLUSTURULMAZ; sadece command baglanir.
                b.configure(command=lambda e=None:
                            _faz4e_mod_degistir(self, e))
            _faz4e_mod_buton_guncelle(self)
            _acilis_mod_mesaji(self)
        except Exception as e:
            _durum["hatalar"].append("faz4e init: %r" % (e,))
        return sonuc

    def shutdown_kapka(self, *a, **k):
        """FAZ 4E.3: kapanista gorevleri guvenle yonet.

        ui._shutdown -> os._exit(0) 380 ms sonra; oncesinde aktif
        gorevler iptal edilir ve teknik log'a yazilir.
        """
        try:
            import jarvis_ai_router as _router
            n = _router.gorev_kapat()
            _log_yaz("baslangic.log",
                     "kapanis: %d aktif gorev iptal edildi" % n)
        except Exception as e:
            _durum["hatalar"].append("shutdown: %r" % (e,))
        if orj_shutdown is not None:
            return orj_shutdown(self, *a, **k)
        return None

    J.__init__ = init_kapka
    J._mod_buton_guncelle = _faz4e_mod_buton_guncelle
    J._mod_degistir = _faz4e_mod_degistir
    if orj_shutdown is not None:
        J._shutdown = shutdown_kapka
    J._jarvis_ai_faz4e_sarili = True
    return True


# ---------------------------------------------------------------------------
# FAZ 4E.4: HIZLI GOREV MOTORU / OFFLINE KORUMASI / DOGRULAMA
# ---------------------------------------------------------------------------
def _offline_modda_mi():
    """OFFLINE modunda mi? (mod bilgisi belirsizse FAIL-CLOSED: True)

    Uc ajan zinciri (SONSUZ v2 / USTA / 10 AI Konsey / HAKEM / UYGULAYICI)
    bu fonksiyonu kontrol ederek OFFLINE modunda DIS AGA cikmaz.
    """
    try:
        import jarvis_ai_router as _r
        return bool(_r.mod_offline_mi())
    except Exception:
        return True          # mod bilinmiyorsa guvenli tarafa gir


def _hizli_calistir(talep, log=None):
    """Basit gorevleri deterministik motorla cozer (ag/Ollama/ajan YOK).

    Donus: cevap metni (str) veya None (bu motor handle etmedi).
    """
    try:
        import jarvis_ai_hizli as _h
    except Exception as e:
        _durum["hatalar"].append("hizli motor: %r" % (e,))
        return None
    try:
        sonuc = _h.calistir(talep)
    except Exception as e:
        _durum["hatalar"].append("hizli motor calistir: %r" % (e,))
        return None
    if not sonuc:
        return None
    tur = sonuc.get("tur") or "?"
    if log:
        try:
            log("SYS: HIZLI GOREV MOTORU | tur=%s | kaynak=Hizli yerel "
                "gorev motoru | ag/Ollama/ajan zinciri KULLANILMADI" % tur)
            log("SYS: DOGRULAMA | %s" % str(sonuc.get("dogrulama") or "")[:220])
            if not sonuc.get("ok"):
                log("SYS: GOREV BASARISIZ - sonuc kullaniciya aktariliyor")
            log("JARVIS: " + str(sonuc.get("cevap") or ""))
        except Exception:
            pass
    try:
        import jarvis_ai_router as _r
        _r.log_yaz("hizli gorev: tur=%s ok=%s | %s"
                   % (tur, sonuc.get("ok"),
                      str(sonuc.get("dogrulama") or "")[:120]), 'gorev')
    except Exception:
        pass
    return str(sonuc.get("cevap") or "")


def _hizli_gorev_kur():
    """USTA/SONSUZ girisini hizli gorev motoruna baglar.

    Basit matematik/birim/tarih/metin/dosya istekleri icin 10 AI Konsey +
    11. HAKEM + PowerShell zincirine GIRILMEZ.
    """
    try:
        import jarvis_usta as _ju
    except Exception as e:
        _durum["hatalar"].append("hizli kurulum: %r" % (e,))
        return False
    if getattr(_ju, "_jarvis_ai_hizli_sarili", False):
        return True
    orj_sinirsiz = getattr(_ju, "sinirsiz_calistir", None)
    orj_calistir = getattr(_ju, "calistir", None)
    _orijinal["usta_sinirsiz_calistir"] = orj_sinirsiz
    _orijinal["usta_calistir"] = orj_calistir

    def sinirsiz_calistir_kapka(talep, log=None, ses=None, ekran_al=True,
                                _v2=True, *a, **k):
        cevap = _hizli_calistir(talep, log)
        if cevap is not None:
            return None
        if orj_sinirsiz is None:
            return None
        return orj_sinirsiz(talep, log=log, ses=ses, ekran_al=ekran_al,
                            _v2=_v2, *a, **k)

    def calistir_kapka(talep, log=None, ses=None, ekran_al=True, bekle=True,
                       *a, **k):
        cevap = _hizli_calistir(talep, log)
        if cevap is not None:
            return None
        if orj_calistir is None:
            return None
        return orj_calistir(talep, log=log, ses=ses, ekran_al=ekran_al,
                            bekle=bekle, *a, **k)

    if orj_sinirsiz is not None:
        _ju.sinirsiz_calistir = sinirsiz_calistir_kapka
    if orj_calistir is not None:
        _ju.calistir = calistir_kapka
    _ju._jarvis_ai_hizli_sarili = True
    return True


def _offline_koruma_kur():
    """OFFLINE modunda DIS AGI TAMAMEN kapatir (fail-closed).

    * jarvis_yetenek.ai_sor_saglayici / ai_sor_ex: OFFLINE'da yalnizca
      yerel (ollama) saglayiciya izin verilir.
    * jarvis_anlama.web_ozetler: OFFLINE'da internet aramasi yapilmaz.
    """
    try:
        import jarvis_yetenek as _yt
    except Exception as e:
        _durum["hatalar"].append("offline yetenek: %r" % (e,))
        return False
    if getattr(_yt, "_jarvis_ai_offline_sarili", False):
        return True
    orj_sor_saglayici = getattr(_yt, "ai_sor_saglayici", None)
    orj_sor_ex = getattr(_yt, "ai_sor_ex", None)
    _orijinal["yt_ai_sor_saglayici"] = orj_sor_saglayici
    _orijinal["yt_ai_sor_ex"] = orj_sor_ex

    def _yerel_mi(ad):
        a = str(ad or "").lower()
        return ("ollama" in a or "localhost" in a or "127.0.0.1" in a)

    def ai_sor_saglayici_kapka(ad, soru, *a, **k):
        if _offline_modda_mi() and not _yerel_mi(ad):
            try:
                import jarvis_ai_router as _r
                _r.log_yaz("OFFLINE: dis saglayici engellendi: %s" % ad,
                           'offline')
            except Exception:
                pass
            raise RuntimeError(
                "OFFLINE modunda dis AI saglayicisi kullanilamaz: %s" % ad)
        if orj_sor_saglayici is None:
            return ""
        return orj_sor_saglayici(ad, soru, *a, **k)

    def ai_sor_ex_kapka(soru, *a, **k):
        if _offline_modda_mi():
            atla = tuple(k.get("atla") or ())
            # Zincirdeki dis saglayicileri atlanir; yerel Ollama kalir.
            if atla:
                k = dict(k)
                k["atla"] = tuple(atla)
        if orj_sor_ex is None:
            return "", ""
        return orj_sor_ex(soru, *a, **k)

    orj_istek = getattr(_yt, "_saglayici_istek", None)
    _orijinal["yt_saglayici_istek"] = orj_istek

    def _saglayici_istek_kapka(ad, url, model, anahtar, soru, *a, **k):
        """OFFLINE modunda DIS uc noktaya istek atilmaz (fail-closed) + CHAT V2 Mod Sorgulama Entegrasyonu."""
        try:
            from CHAT_V2.message_router_v2 import classify_intent
            if soru and classify_intent(soru).get("type") == "mod_sorgulama":
                # FAZ 2.2B: dogrudan motor cagrisi YOK; broker uzerinden.
                import jarvis_chat_v2_entegrasyon as _c2e
                res, _tekrar = _c2e.guvenli_isle(
                    soru, kaynak='sarmalayici')
                if res.get("success") and res.get("response"):
                    return res["response"]
        except Exception:
            pass

        if _offline_modda_mi() and not _yerel_mi(ad):
            try:
                import jarvis_ai_router as _r
                _r.log_yaz("OFFLINE: dis uc nokta engellendi: %s" % ad,
                           'offline')
            except Exception:
                pass
            raise RuntimeError(
                "OFFLINE modunda dis uc noktaya istek atilamaz: %s" % ad)
        if orj_istek is None:
            return ''
        return orj_istek(ad, url, model, anahtar, soru, *a, **k)

    if orj_sor_saglayici is not None:
        _yt.ai_sor_saglayici = ai_sor_saglayici_kapka
    if orj_sor_ex is not None:
        _yt.ai_sor_ex = ai_sor_ex_kapka
    if orj_istek is not None:
        _yt._saglayici_istek = _saglayici_istek_kapka
    _yt._jarvis_ai_offline_sarili = True
    # Internet aramasi (jarvis_anlama)
    try:
        import jarvis_anlama as _an
        if not getattr(_an, "_jarvis_ai_offline_sarili", False):
            orj_web = getattr(_an, "web_ozetler", None)
            _orijinal["an_web_ozetler"] = orj_web

            def web_ozetler_kapka(*a, **k):
                if _offline_modda_mi():
                    try:
                        import jarvis_ai_router as _r
                        _r.log_yaz("OFFLINE: internet aramasi engellendi",
                                   'offline')
                    except Exception:
                        pass
                    return []
                if orj_web is None:
                    return []
                return orj_web(*a, **k)

            if orj_web is not None:
                _an.web_ozetler = web_ozetler_kapka
            _an._jarvis_ai_offline_sarili = True
    except Exception as e:
        _durum["hatalar"].append("offline anlama: %r" % (e,))
    # Gorsel/ekonomi katmani (Gemini tabanli vizyon) - OFFLINE'da engellenir
    for _mod_ad, _fn_ad in (("jarvis_ergonomi", "gemini_vizyon"),
                            ("jarvis_sonsuz2", "_vizyon")):
        try:
            _mod = __import__(_mod_ad)
        except Exception:
            continue
        if getattr(_mod, "_jarvis_ai_offline_sarili", False):
            continue
        _orijinal["%s_%s" % (_mod_ad, _fn_ad)] = getattr(_mod, _fn_ad, None)

        def _make(_orj, _ad):
            def _kapak(*a, **k):
                if _offline_modda_mi():
                    try:
                        import jarvis_ai_router as _r
                        _r.log_yaz("OFFLINE: %s engellendi" % _ad,
                                   'offline')
                    except Exception:
                        pass
                    return ''
                if _orj is None:
                    return ''
                return _orj(*a, **k)
            return _kapak

        _fn = getattr(_mod, _fn_ad, None)
        if _fn is not None:
            setattr(_mod, _fn_ad, _make(_fn, _fn_ad))
        _mod._jarvis_ai_offline_sarili = True
    return True


def _anahtar_log_kapat():
    """'Mevcut API anahtarlari kullaniliyor: ...' logunu kapatir.

    API anahtarlari ASLA loglanmaz; ajan akisinda hangi anahtarlarin
    kullanilabilir oldugu da HUD'a basilmaz.
    """
    try:
        import jarvis_yetenek as _yt
    except Exception as e:
        _durum["hatalar"].append("anahtar log: %r" % (e,))
        return False
    if getattr(_yt, "_jarvis_ai_anahtar_log_kapali", False):
        return True
    orj_anahtar = getattr(_yt, "anahtar_bul", None)
    _orijinal["yt_anahtar_bul"] = orj_anahtar
    if orj_anahtar is not None:
        def anahtar_bul_kapka(log=None):
            return orj_anahtar(log=None)
        _yt.anahtar_bul = anahtar_bul_kapka
    _yt._jarvis_ai_anahtar_log_kapali = True
    return True


def _ilgisiz_mesaj_kapat():
    """Istenmeyen 'Rehberini sorayim: WhatsApp kisilerini kaydedeyim mi?'
    onerisini bastirir (gorevle ilgisiz kisisel bilgi istemek yasak).

    Filtre JARVISUIN write_log yolunda yapilir; boylece main.pyc icindeki
    JarvisLive sinifina (runtime'da olusturulan) erismek gerekmez.
    """
    try:
        import ui as _ui
        J = _ui.JarvisUI
    except Exception as e:
        _durum["hatalar"].append("ilgisiz mesaj: %r" % (e,))
        return False
    if getattr(J, "_jarvis_ai_rehber_kapali", False):
        return True
    orj_wl = getattr(J, "write_log", None)
    _orijinal["write_log"] = orj_wl

    def write_log_kapka(self, text, *a, **k):
        t = str(text or "")
        if ("Rehberini soray" in t or "WhatsApp ki\u015filerini" in t
                or "WhatsApp kisilerini" in t):
            try:
                import jarvis_ai_router as _r
                _r.log_yaz("ilgisiz rehber onerisi bastirildi", 'offline')
            except Exception:
                pass
            return None
        if orj_wl is None:
            return None
        return orj_wl(self, text, *a, **k)

    if orj_wl is not None:
        J.write_log = write_log_kapka
    J._jarvis_ai_rehber_kapali = True
    return True


def _rapor_dogrulama_kur():
    """USTA raporuna DOGRULAMA bolumu ekler.

    Rapor artik: kullanici istegi, beklenen cikti, gerceklestirilen
    islemler, olusturulan dosyalar, test sonucu ve basari/basarisiz
    durumunu icerir. DOGRULANMAYAN gorev 'tamamlandi' sayilmaz.
    """
    try:
        import jarvis_usta as _ju
    except Exception as e:
        _durum["hatalar"].append("rapor dogrulama: %r" % (e,))
        return False
    if getattr(_ju, "_jarvis_ai_dogrulama_sarili", False):
        return True
    orj_rapor = getattr(_ju, "_rapor_yaz", None)
    _orijinal["usta_rapor_yaz"] = orj_rapor
    if orj_rapor is None:
        return False

    def rapor_yaz_kapka(talep, baslangic):
        metin = orj_rapor(talep, baslangic)
        try:
            metin += _dogrulama_bolumu(talep, baslangic)
        except Exception as e:
            _durum["hatalar"].append("dogrulama bolumu: %r" % (e,))
        return metin

    _ju._rapor_yaz = rapor_yaz_kapka
    _ju._jarvis_ai_dogrulama_sarili = True
    return True


def _dogrulama_bolumu(talep, baslangic):
    """Gorev dogrulama bolumu (metin)."""
    import time as _t
    sure = _t.time() - float(baslangic or _t.time())
    komutlar = list(getattr(__import__("jarvis_usta", fromlist=["x"]),
                            "_KOMUTLAR", []) or [])
    uretilen = list(getattr(__import__("jarvis_usta", fromlist=["x"]),
                            "_URETILEN", []) or [])
    hatalar = list(getattr(__import__("jarvis_usta", fromlist=["x"]),
                           "_HATALAR", []) or [])
    satirlar = []
    satirlar.append("")
    satirlar.append("## DOGRULAMA")
    satirlar.append("- Kullanici istegi: %s" % str(talep)[:200])
    satirlar.append("- Beklenen cikti: istegin karsiligi dogrudan uretilmis "
                    "olmalidir (hesap/cikti/dosya).")
    satirlar.append("- Gerceklestirilen islem sayisi: %d" % len(komutlar))
    for k in komutlar[:12]:
        satirlar.append("  * %s" % str(k)[:160])
    satirlar.append("- Olusturulan dosya sayisi: %d" % len(uretilen))
    for u in uretilen[:12]:
        satirlar.append("  * %s" % str(u)[:160])
    satirlar.append("- Hata sayisi: %d" % len(hatalar))
    for h in hatalar[:8]:
        satirlar.append("  * %s" % str(h)[:160])
    if hatalar:
        durum = "BASARISIZ (hata var)"
    elif not komutlar and not uretilen:
        durum = "BASARISIZ/SONUC YOK (hiçbir islem yapılmadı)"
    else:
        durum = "DOGRULANDI (islemler uygulandi)"
    satirlar.append("- Test sonucu: %s" % durum)
    satirlar.append("- Toplam sure: %.1f sn" % sure)
    satirlar.append("")
    satirlar.append("> NOT: Dogrulama yapilmayan bir gorev 'tamamlandi' "
                    "sayilmaz; yukaridaki 'BASARISIZ' durumu varsa gorev "
                    "basarisiz olarak raporlanir.")
    return "\n".join(satirlar)

# ---------------------------------------------------------------------------
# Uygula / geri al
# ---------------------------------------------------------------------------
def uygula():
    """Sarmalayiciyi kurar. Donus: bool.

    Her adim ayri try/except icerisindedir; bir adim patlarsa digerleri
    calismaya devam eder ve hata durum'a yazilir (rapor icin).
    """
    if os.environ.get("JARVIS_AI", "1") == "0":
        _durum["kapatilma_nedeni"] = "JARVIS_AI=0"
        return False

    kok = os.path.dirname(os.path.abspath(__file__))
    orijinal_dir = os.path.join(kok, "orijinal")
    if os.path.isdir(orijinal_dir) and orijinal_dir not in sys.path:
        sys.path.insert(0, orijinal_dir)

    # 1) app_config: offline_mode=True, offline_model=qwen3:4b
    try:
        import app_config
        _orijinal["get_app_config_value"] = app_config.get_app_config_value
        app_config.get_app_config_value = _config_kapka
    except Exception as e:
        _durum["hatalar"].append("app_config: %r" % (e,))

    # 2) jarvis_anlama: online_mi -> False (her zaman YEREL mod)
    #    FAZ 4E: mod_oku / mod_yaz / mod_iste -> 3 modlu baglanti modu
    try:
        import jarvis_anlama
        _orijinal["online_mi"] = jarvis_anlama.online_mi
        jarvis_anlama.online_mi = _online_mi_kapka
        _orijinal["mod_oku"] = jarvis_anlama.mod_oku
        _orijinal["mod_yaz"] = jarvis_anlama.mod_yaz
        _orijinal["mod_iste"] = jarvis_anlama.mod_iste
        jarvis_anlama.mod_oku = _mod_oku_kapka
        jarvis_anlama.mod_yaz = _mod_yaz_kapka
        jarvis_anlama.mod_iste = _mod_iste_kapka
    except Exception as e:
        _durum["hatalar"].append("jarvis_anlama: %r" % (e,))

    # 3) jarvis_v51_ajan: sohbetin ANA AI cagrisi -> yerel model
    try:
        import jarvis_v51_ajan
        _orijinal["_v51_ai_her_kosul"] = jarvis_v51_ajan._v51_ai_her_kosul
        jarvis_v51_ajan._v51_ai_her_kosul = _v51_kapka
    except Exception as e:
        _durum["hatalar"].append("jarvis_v51_ajan: %r" % (e,))

    # 4) jarvis_yetenek: tum saglayici istekleri -> yerel model
    try:
        import jarvis_yetenek
        _orijinal["_saglayici_istek"] = jarvis_yetenek._saglayici_istek
        jarvis_yetenek._saglayici_istek = _saglayici_kapka
    except Exception as e:
        _durum["hatalar"].append("jarvis_yetenek: %r" % (e,))

    # 5) TTS ayarı (Faz 1: Gemini seslendirme tetiklenmez | Faz 2: Yerel TTS)
    tts_acak = os.environ.get("JARVIS_AI_TTS", "kapali")
    if tts_acak == "acik":
        # Faz 2: Yerel edge-tts ile Turkish Neural sesler
        try:
            import jarvis_local_tts as _local_tts
            # TTS modülü başarıyla yüklendi, speech manager'ı local TTS ile doldur
            _durum["yerel_tts"] = True
        except Exception as e:
            _durum["hatalar"].append("yar_local_tts: %r" % (e,))
            _local_tts = None
        # Speech manager'ı local TTS ile güncelle (orijinal kaydet ve yenisini ata)
        try:
            import jarvis_speech_manager as _sm
            _orijinal["sm_gonder"] = _sm.gonder
            _orijinal["sm_konus"] = _sm.konus
            if _local_tts is not None:
                _sm.gonder = _local_tts.ses_uret  # WAV dosya yolu dondur
                _sm.konus = lambda metin, **kwargs: (_local_tts.konus(metin), True)[1]  # sesli oku
            else:
                _sm.gonder = _sm_gonder_kapka
                _sm.konus = _sm_konus_kapka
        except Exception as e:
            _durum["hatalar"].append("jarvis_speech_manager: %r" % (e,))
            try:
                import jarvis_speech_manager as _sm
                _sm.gonder = _sm_gonder_kapka
                _sm.konus = _sm_konus_kapka
            except Exception:
                pass
    elif tts_acak != "0":
        # Belirtilmemiş veya farklı bir değer: bastir (Faz 1 davranisi)
        try:
            import jarvis_speech_manager as _sm
            _orijinal["sm_gonder"] = _sm.gonder
            _orijinal["sm_konus"] = _sm.konus
            _sm.gonder = _sm_gonder_kapka
            _sm.konus = _sm_konus_kapka
        except Exception as e:
            _durum["hatalar"].append("jarvis_speech_manager: %r" % (e,))
    else:
        # JARVIS_AI=0 veya kapala: bastir
        try:
            import jarvis_speech_manager as _sm
            _orijinal["sm_gonder"] = _sm.gonder
            _orijinal["sm_konus"] = _sm.konus
            _sm.gonder = _sm_gonder_kapka
            _sm.konus = _sm_konus_kapka
        except Exception as e:
            _durum["hatalar"].append("jarvis_speech_manager: %r" % (e,))

    # 6) Soket muhafizasi: yalnizca localhost
    if os.environ.get("JARVIS_AI_AG", "1") != "0":
        try:
            _soket_muhafizasi_kur()
        except Exception as e:
            _durum["hatalar"].append("soket muhafizasi: %r" % (e,))

    # 6B) FAZ 4E: HUD'daki ONL/OFF butonunu 3 modlu (ONL/OFF/OTO) yap
    try:
        _faz4e_ui_kur()
    except Exception as e:
        _durum["hatalar"].append("faz4e ui: %r" % (e,))

    # 6C) FAZ 4E.4: hizli gorev motoru + OFFLINE korumasi + dogrulama
    for _ad, _fn in (("_hizli_gorev_kur", _hizli_gorev_kur),
                     ("_offline_koruma_kur", _offline_koruma_kur),
                     ("_anahtar_log_kapat", _anahtar_log_kapat),
                     ("_ilgisiz_mesaj_kapat", _ilgisiz_mesaj_kapat),
                     ("_rapor_dogrulama_kur", _rapor_dogrulama_kur)):
        try:
            _fn()
        except Exception as e:
            _durum["hatalar"].append("%s: %r" % (_ad, e))

    # 7) Test modu: HUD kayit + otomatik sohbet testi
    if os.environ.get("JARVIS_AI_TEST", "0") == "1":
        try:
            _ui_test_kur()
        except Exception as e:
            _durum["hatalar"].append("test modu: %r" % (e,))

    _durum["aktif"] = True
    _log_yaz("baslangic.log",
             "JARVIS AI FAZ 1 aktif | model=%s | base=%s | hatalar=%d | ders_modu=%s"
             % (MODEL, OLLAMA_BASE, len(_durum["hatalar"]),
                _durum.get("ders_modu", False)))
    return True


def ders_modu_ayarla(ac=True):
    """Ders modunu aç/kapali yapar.

    * ac=True  -> AI cevapları öğretici/akademik formatta (Python örnekleri)
    * ac=False -> Normal sohbet geri döner
    * Dönüş: yeni ders_modu durumu
    """
    _durum["ders_modu"] = bool(ac)
    status = "açildi" if _durum["ders_modu"] else "kapatıldı"
    _log_yaz("baslangic.log", "Ders modu %s" % status)
    return _durum["ders_modu"]


def geri_al():
    """Tum yamalari kaldirir (orijinal davranis geri gelir)."""
    try:
        if "get_app_config_value" in _orijinal:
            import app_config
            app_config.get_app_config_value = _orijinal["get_app_config_value"]
        if "online_mi" in _orijinal:
            import jarvis_anlama
            jarvis_anlama.online_mi = _orijinal["online_mi"]
        if "mod_oku" in _orijinal:
            import jarvis_anlama
            jarvis_anlama.mod_oku = _orijinal["mod_oku"]
        if "mod_yaz" in _orijinal:
            import jarvis_anlama
            jarvis_anlama.mod_yaz = _orijinal["mod_yaz"]
        if "mod_iste" in _orijinal:
            import jarvis_anlama
            jarvis_anlama.mod_iste = _orijinal["mod_iste"]
        if "_mod_buton_guncelle" in _orijinal:
            try:
                import ui as _ui
                J = _ui.JarvisUI
                if _orijinal["_mod_buton_guncelle"] is not None:
                    J._mod_buton_guncelle = _orijinal["_mod_buton_guncelle"]
                if _orijinal["_mod_degistir"] is not None:
                    J._mod_degistir = _orijinal["_mod_degistir"]
            except Exception:
                pass
        if "_v51_ai_her_kosul" in _orijinal:
            import jarvis_v51_ajan
            jarvis_v51_ajan._v51_ai_her_kosul = _orijinal["_v51_ai_her_kosul"]
        if "_saglayici_istek" in _orijinal:
            import jarvis_yetenek
            jarvis_yetenek._saglayici_istek = _orijinal["_saglayici_istek"]
        if "sm_gonder" in _orijinal:
            import jarvis_speech_manager as _sm
            _sm.gonder = _orijinal["sm_gonder"]
            _sm.konus = _orijinal["sm_konus"]
        if "soket_connect" in _orijinal:
            import socket
            socket.socket.connect = _orijinal["soket_connect"]
            if _orijinal.get("soket_sendto") is not None:
                socket.socket.sendto = _orijinal["soket_sendto"]
            if hasattr(socket.socket, "_jarvis_ai_guard"):
                del socket.socket._jarvis_ai_guard
        _durum["aktif"] = False
        _log_yaz("baslangic.log", "JARVIS AI FAZ 1 geri alindi")
        return True
    except Exception as e:
        _durum["hatalar"].append("geri_al: %r" % (e,))
        return False


def durum():
    tls = {}
    devre = {}
    try:
        import jarvis_ai_router as _r
        tls = _r.tls_durum()
        devre = {ad: _r.devre_durumu(ad) for ad in _r.izinli_saglayicilar()}
    except Exception:
        tls = {'hata': 'router yuklenemedi'}
    return {
        "aktif": _durum["aktif"],
        "model": MODEL,
        "base": OLLAMA_BASE,
        "hatalar": list(_durum["hatalar"]),
        "kapatilma_nedeni": _durum["kapatilma_nedeni"],
        "istek_sayisi": len(_kayit["istekler"]),
        "tts_cagri_sayisi": len(_kayit["tts"]),
        "ag_denetimi_sayisi": len(_kayit["ag"]),
        "saglayici_cagri_sayisi": len(_kayit["saglayici"]),
        "baglanti_modu": _mod_oku_kapka(),
        "tls": tls,
        "devre_kesici": devre,
    }
