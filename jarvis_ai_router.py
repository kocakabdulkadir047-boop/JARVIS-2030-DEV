# -*- coding: utf-8 -*-
"""jarvis_ai_router — FAZ 4A guvenli otomatik AI saglayici yoneticisi
(FAZ 4D duzeltmeleri ile).

SAĞLAYICI GÜVENLİĞİ
    İzinli (sadece bunlar):  gemini, groq, openrouter
    Kesinlikle devre disi:     openai, anthropic/claude, deepseek,
                               pollinations ve izin listesinde olmayan
                               TUM diger saglayicilar.
    * Ucretli model veya ucretli API uc noktasi KULLANILMAZ.
    * OpenRouter icin sadece ':free' ile biten model kimliklerine izin verilir.
    * Ucretsiz katman garantisi VERILMEZ; saglayicinin kendi ucretlendirme
      ve kota kosullari kullanici tarafindan dogrulanmalidir.

FAZ 4D DUZELTMELERI
    1) ANAHTAR KAYNAKLARI: api_keys.json birden fazla aday yoldan aranir;
       ilk BOS OLMAYAN deger kullanilir. (EXE kendi yanindaki dosyada
       bos anahtar varken proje kokundeki gecerli anahtar kullanilmiyordu.)
    2) MODEL TERCİHI: api_keys.json icindeki 'ai_model_<saglayici>'
       de dikkate alinir.
    3) HTTP HATA SINIFLANDIRMA: 401/403/404/429/5xx, zaman asimi, DNS ve
       TLS hatalari ayri kategorilerle ayirt edilir.
    4) TEKNIK LOG: router.log'a deneme/sonuc/hata yazilir. API anahtari,
       Authorization/x-goog-api-key basligi, istek govdesi ve sohbet
       icerigi ASLA yazilmaz.
    5) SAGLIK ONBELLEGI: hata kategorisine gore kisa sureli devre disi kalma.
    6) INTERNET KONTROLU: 5 sn zaman asimi, DNS/connect ayrimi, sonuc
       loglanir.

AG GÜVENLİĞİ
    * Ag erisimi sadece izinli saglayici alan adlarina ve loopback'e aciktir.
    * DNS cozumlemesi, IP kontrolu ve izinli alan adi dogrulamasi yapilir.
    * DNS cozumlemesi basarisiz olursa baglanti reddedilir.
    * TLS sertifika dogrulamasi AKTIF kalir (verify=False / CERT_NONE yok).

API ANAHTARLARI
    * Mevcut okuma yontemi korunur: jarvis_yetenek.ayarlar()
      (config/api_keys.json) - bu dosya OKUNMAZ/YAZILMAZ.
    * Anahtar degerleri ASLA loglanmaz, ASLA hata mesajina girmez
      (Gemini'de baslik olarak gonderilir, URL'ye eklenmez).
"""
from __future__ import annotations

import http.client
import json
import os
import random
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request

SURUM = 'v3'

# ---------------------------------------------------------------------------
# FAZ 4E: BAGLANTI MODU (ONLINE / OFFLINE / OTOMATIK)
# ---------------------------------------------------------------------------
#: OTOMATIK -> internet varsa bulut saglayicilari, yoksa yerel model
#: ONLINE   -> internet probu ATLANIR, bulut saglayicilari dogrudan denenir
#: OFFLINE  -> tum bulut istekleri devre disi, dogrudan yerel model
MOD_OTO = 'auto'
MOD_ONLINE = 'online'
MOD_OFFLINE = 'offline'

#: Buton sirasinda gosterilen siralama (auto -> online -> offline -> auto)
MODLAR = (MOD_OTO, MOD_ONLINE, MOD_OFFLINE)

MOD_ETIKET = {
    MOD_OTO: 'OTOMATIK (internet varsa bulut, yoksa yerel model)',
    MOD_ONLINE: 'ONLINE (internet probu atlanir, bulut saglayicilari denenir)',
    MOD_OFFLINE: 'OFFLINE (internet gerekmez, dogrudan yerel model)',
}

#: HUD butonunda gosterilen kisa metin (btn_w=30px -> 3 karakter!)
MOD_KISA = {MOD_OTO: 'OTO', MOD_ONLINE: 'ONL', MOD_OFFLINE: 'OFF'}

#: HUD buton rengi (aktif mod acikça anlasilsin diye)
MOD_RENK = {MOD_OTO: '#00ff88', MOD_ONLINE: '#00e5ff', MOD_OFFLINE: '#ffaa00'}

#: Mod normalizasyonunda kabul edilen yazimlar
MOD_ESLENSIZ = {
    'online': MOD_ONLINE, 'onlayn': MOD_ONLINE, 'cevrimici': MOD_ONLINE,
    'cevrim ici': MOD_ONLINE, 'on line': MOD_ONLINE, 'bagli': MOD_ONLINE,
    'offline': MOD_OFFLINE, 'oflayn': MOD_OFFLINE, 'cevrimdisi': MOD_OFFLINE,
    'cevrim disi': MOD_OFFLINE, 'of line': MOD_OFFLINE, 'bagimsiz': MOD_OFFLINE,
    'auto': MOD_OTO, 'oto': MOD_OTO, 'otomatik': MOD_OTO,
    'automatik': MOD_OTO, 'automatic': MOD_OTO,
}

# ---------------------------------------------------------------------------
# FAZ 4E.2: GECICI HATA YONETIMI + DEVRE KESICI + ISTEK CAKISMASI
# ---------------------------------------------------------------------------
#: Gecici hatalar: kontrollu olarak TEKRAR DENENIR (503/500/502/504,
#: gecici zaman asimi, baglanti hatasi).
GECICI_TURLER = ('sunucu', 'zaman', 'baglanti')

#: Devre kesici acisinda GECICI sayilan hatalar (kota dahil: kotanin
#: kendi bekleme politikasi vardir ama gecici bir durumdur).
DEVRE_GECICI_TURLER = GECICI_TURLER + ('kota',)

#: Kalici hatalar: TEKRAR DENENMEZ (401/403 yapilandirma, 404 model, vs.)
KALICI_TURLER = ('yetki', 'model', 'istek', 'anahtar', 'dns', 'tls')

#: Toplam deneme sayisi (gecici hata icin en fazla 3)
RETRY_MAX_DENEME = 3
#: Artan bekleme araliklari (sn) - 1. denemeden sonra 2 sn, sonra 5 sn
RETRY_BEKLEME_SN = (2.0, 5.0, 10.0)
#: Kucuk rastgele fark orani (+/- %25) - thundering herd onlemi
RETRY_JITTER = 0.25
#: Tek bekleme tavani (sn) - gereksiz uzun bekleme olmasin
RETRY_TEK_TAVAN = 20.0
#: Toplam bekleme tavani (sn)
RETRY_TOPLAM_TAVAN = 25.0
#: Saglayici basina toplam sure butcesi (sn) - gereksiz uzun bekleme olmaz
RETRY_TOPLAM_BUDGE_SN = 90.0

#: FAZ 4E.3: BULUT ISTEGI BASINA KESIN TIMEOUT
#: Bulut saglayicilari icin zaman asimi, cagiranin 'zaman' degeriyle DEGIL,
#: saglayicinin kendi 'timeout_s' degeriyle belirlenir. (Cagiranin 'zaman'
#: degeri YEREL model icindir: qwen3:4b 90-230 sn surebilir.)
BULUT_TIMEOUT_TAVAN = 45.0
BULUT_TIMEOUT_ASGARI = 5.0

#: HTTP 429 (kota / hiz siniri) icin AYRI politika
KOTA_RETRY_MAX = 2
KOTA_BEKLEME_SN = (5.0, 12.0)
#: Retry-After basligi degerinin uygulanabilecegi en fazla sure (sn)
KOTA_RETRY_AFTER_TAVAN = 30.0

#: Devre kesici bekleme suresi (ardisik basarisizliga gore, sn)
DEVRE_BEKLEME_SN = (15.0, 30.0, 60.0, 120.0)
DEVRE_BEKLEME_TAVAN = 120.0

#: Devam eden istegin en fazla yasam suresi (sn)
UCUS_TAVAN = 300.0
#: Yinelenen (ayni) istek icin beklenecek en fazla sure (sn)
UCUS_BEKLEME_TAVAN = 120.0

#: Saglayici gosterim adlari (kullanici mesajlari icin)
SAGLAYICI_AD = {'gemini': 'Gemini', 'groq': 'Groq',
                 'openrouter': 'OpenRouter'}

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------
IZINLI_SAGLAYICILAR = ('gemini', 'groq', 'openrouter')

YASAKLI_SAGLAYICILAR = (
    'openai', 'anthropic', 'claude', 'deepseek', 'pollinations',
    'perplexity', 'mistral', 'cohere', 'together', 'fireworks', 'xai',
)

YEREL_SAGLAYICI = 'ollama'
YEREL_TABAN = 'http://localhost:11434'

#: Ucretsiz katman uyarisi (kullaniciya acikca belirtilir).
UCRETSIZ_UYARI = (
    "Ucretsiz katman kosullari saglayiciya ve modele gore degisir; JARVIS bunu "
    "DOGRULAMAZ. Ucretlendirme/kota kosullarini kullanici dogrulamalidir."
)

#: Izinli alan adlari (soket muhafizasi bunlari kullanir).
IZINLI_ALAN_ADLARI = (
    'generativelanguage.googleapis.com',   # Gemini
    'api.groq.com',                        # Groq
    'openrouter.ai',                       # OpenRouter
)

#: Hata kategorisine gore saglayici devre disi kalma suresi (sn).
VARSAYILAN_KATEGORI_TTL = {
    'yetki': 60.0,      # 401/403 -> anahtar/kota; 1 dk sonra tekrar dene
    'model': 60.0,      # 404 -> model adi yanlis; 1 dk sonra tekrar dene
    'kota': 20.0,       # 429 -> hizli tekrar dene
    'zaman': 20.0,      # timeout
    'baglanti': 15.0,   # baglanti hatasi
    'dns': 15.0,        # DNS hatasi
    'tls': 60.0,        # TLS dogrulama hatasi
    'tls_zincir': 60.0,  # sertifika zinciri guvenilmiyor
    'tls_suresi': 60.0,  # sertifika suresi gecersiz
    'tls_sunucu_adi': 60.0,  # sunucu adi eslesmedi
    'tls_ca_yok': 300.0,     # CA dosyasi bulunamadi (uzun sure bekle)
    'tls_baglanti': 15.0,    # TLS handshake/oturum hatasi
    'tls_mudahale': 300.0,   # proxy/guvenlik yazilimi mudahalesi
    'sunucu': 20.0,     # 5xx
    'istek': 20.0,      # 4xx
    'hata': 20.0,        # diger
    'varsayilan': 30.0,
}

#: FAZ 4E.1: KAPATILMIS / EMEKLI MODELLER.
#: Bu modeller artik API'de bulunmuyor; kullanici tercihi olsalar bile
#: guncel kararli modele OTOMATIK olarak gecilir (loglanarak).
#: Gemini ONLINE modunda ILK denenecek modeldir.
ESKIMIS_MODELLER = (
    'gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-1.5-flash-001',
    'gemini-1.5-pro', 'gemini-1.5-pro-latest',
    'gemini-2.0-flash', 'gemini-2.0-flash-001',
    'gemini-2.0-flash-lite', 'gemini-2.0-flash-lite-001',
)

#: FAZ 4E.4.2: ONLINE/AOTO modunda deneme sırasındaki PRIORITET.
#: Gemini her zaman ilk denenecek model; sonradan groq/openrouter.
DENEME_SIRASI = ('gemini', 'groq', 'openrouter')

VARSAYILAN_SAGLAYICILAR = (
    {
        'name': 'gemini',
        'enabled': True,
        'url': ('https://generativelanguage.googleapis.com/v1beta/models/'
                '%s:generateContent'),
        # FAZ 4E.1: gemini-2.0-flash 1 Haziran 2026'da KAPATILDI.
        # Guncel kararli GA model: gemini-3.8-flash (2 Eylul 2026).
        'model': 'gemini-3.8-flash',
        'model_yedekleri': ('gemini-3.6-flash', 'gemini-3.5-flash-lite'),
        'model_env': 'ai_model_gemini',
        'key_field': 'gemini_api_key',
        'env_keys': ('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GOOGLE_GENAI_API_KEY'),
        'max_tokens': 1200,
        'temperature': 0.4,
        'timeout_s': 25,
        'style': 'gemini',
    },
    {
        'name': 'groq',
        'enabled': True,
        'url': 'https://api.groq.com/openai/v1/chat/completions',
        'model': 'llama-3.3-70b-versatile',
        'model_env': 'ai_model_groq',
        'key_field': 'groq_api_key',
        'env_keys': ('GROQ_API_KEY',),
        'max_tokens': 1200,
        'temperature': 0.4,
        'timeout_s': 25,
        'style': 'openai',
    },
    {
        'name': 'openrouter',
        'enabled': True,
        'url': 'https://openrouter.ai/api/v1/chat/completions',
        'model': 'meta-llama/llama-3.3-70b-instruct:free',
        'model_env': 'ai_model_openrouter',
        'key_field': 'openrouter_api_key',
        'env_keys': ('OPENROUTER_API_KEY',),
        'max_tokens': 1200,
        'temperature': 0.4,
        'timeout_s': 30,
        'style': 'openai',
        'free_suffix': ':free',
    },
)

# ---------------------------------------------------------------------------
# Runtime durumu
# ---------------------------------------------------------------------------
_durum = {
    'internet': None,          # True / False / None (henuz bilinmiyor)
    'internet_t': 0.0,
    'internet_not': '',        # probe sonucu aciklamasi
    'saglik': {},             # ad -> devre kesici kaydi
    'son_saglayici': None,
    'son_model': None,
    'son_zaman': 0.0,
    'sayac': {'bulut': 0, 'yerel': 0, 'hata': 0, 'atlanan': 0,
              'tekrar': 0, 'iptal': 0, 'yinelenen': 0},
    'son_mod_degis': {},
    'uyari': [UCRETSIZ_UYARI],
}

#: Onbellek: birden fazla anahtar (eski tek yuva yerine).
#: Boylece es zamanli iki farkli istek birbirinin sonucunu EZMEZ.
_memo = {}
_MEMO_SURE = 5.0
_MEMO_ADET = 20

#: Devam eden istekler: anahtar -> kayit
_ucus = {}
_ucus_kilit = threading.Lock()
_api_cache = {'t': 0.0, 'liste': []}


class RouterHatasi(Exception):
    """Yonlendirme hatasi. tur: internet|anahtar|model|saglayici|yetki|kota|
    zaman|dns|tls|baglanti|sunucu|istek|hata|iptal|hepsi"""

    def __init__(self, mesaj, tur='saglayici', http_kod=None,
                 retry_after=None):
        super().__init__(mesaj)
        self.tur = tur
        self.http_kod = http_kod
        #: HTTP 429 Retry-After (sn) - kota bekleme politikasi icin
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# Teknik log (anahtar / govde / sohbet icerigi ASLA yazilmaz)
# ---------------------------------------------------------------------------
def log_yaz(satir, tur='olay'):
    """Teknik log -> jarvis_ai_faiz1/router.log

    API anahtari, Authorization / x-goog-api-key basligi, istek govdesi
    ve sohbet mesaji ASLA yazilmaz.
    """
    try:
        kok = os.path.join(_kok(), 'jarvis_ai_faiz1')
        os.makedirs(kok, exist_ok=True)
        with open(os.path.join(kok, 'router.log'), 'a', encoding='utf-8') as f:
            f.write('%s [%-8s] %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'),
                                         str(tur)[:8], str(satir)[:280]))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Yapilandirma
# ---------------------------------------------------------------------------
def _kok():
    try:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.executable))
    except Exception:
        pass
    return os.getcwd()


def _ayar_yolu():
    adaylar = [
        os.path.join(_kok(), 'config', 'ai_routing.json'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     'config', 'ai_routing.json'),
    ]
    for y in adaylar:
        try:
            if os.path.isfile(y):
                return y
        except Exception:
            continue
    return adaylar[0]


def ayarlar():
    """config/ai_routing.json -> sozluk (yoksa varsayilanlar)."""
    veri = {}
    try:
        with open(_ayar_yolu(), 'r', encoding='utf-8') as f:
            veri = json.load(f)
        if not isinstance(veri, dict):
            veri = {}
    except Exception:
        veri = {}
    return veri


# ---------------------------------------------------------------------------
# FAZ 4E: BAGLANTI MODU YONETIMI
# ---------------------------------------------------------------------------
# Mod dosyasi AYRI bir dosyada tutulur; config/api_keys.json'A DOKUNULMAZ.
#   birincil : <exe_kok>/config/jarvis_bag_mod.json
#   eski     : <exe_kok>/config/jarvis_mod.json  (jarvis_anlama'nin dosyasi)
# Geriye donuk uyumluluk:
#   * yeni dosya yoksa eski dosya okunur
#       - eski 'offline' -> 'offline'  (kullanicinin acik tercihi korunur)
#       - eski 'online'  -> 'auto'     (yeni varsayilan)
#   * hicbir dosya yoksa varsayilan 'auto' (OTOMATIK)
#   * mod yazilirken eski dosyaya da ayna yazilir (eski surumler tutarli)

_mod_durum = {'deger': None}


def mod_normalize(deger):
    """Serbest metni ('online'/'offline'/'auto'/Turkce yazim) moda cevirir.

    Donus: 'online' | 'offline' | 'auto' | None (gecersizse None)
    """
    s = str(deger or '').strip().lower()
    if not s:
        return None
    if s in MOD_ESLENSIZ:
        return MOD_ESLENSIZ[s]
    return None


def mod_dosyasi():
    """Birincil mod dosyasi yolu (api_keys.json DEGIL)."""
    return os.path.join(_kok(), 'config', 'jarvis_bag_mod.json')


def _eski_mod_dosyalari():
    """jarvis_anlama'nin kullandigi eski mod dosyasi (tek yol)."""
    return [os.path.join(_kok(), 'config', 'jarvis_mod.json')]


def _mod_dosya_oku(yol):
    try:
        if not os.path.isfile(yol):
            return None
        with open(yol, 'r', encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def mod_oku(zorla_yenile=False):
    """Aktif baglanti modu: 'auto' | 'online' | 'offline'.

    Varsayilan: OTOMATIK.
    """
    if not zorla_yenile and _mod_durum.get('deger') in MODLAR:
        return _mod_durum['deger']
    deger = None
    veri = _mod_dosya_oku(mod_dosyasi())
    if veri is not None:
        deger = mod_normalize(veri.get('mod'))
    if deger is None:
        # Geriye donuk uyumluluk: eski jarvis_mod.json
        for yol in _eski_mod_dosyalari():
            eski = _mod_dosya_oku(yol)
            if eski is None:
                continue
            ham = str(eski.get('mod') or '').strip().lower()
            if ham == 'offline':
                deger = MOD_OFFLINE
            else:
                deger = MOD_OTO
            break
    if deger is None:
        deger = MOD_OTO
    _mod_durum['deger'] = deger
    return deger


def mod_yaz(deger):
    """Modu kalici olarak yazar. Donus: yeni mod ('auto'|'online'|'offline')."""
    m = mod_normalize(deger)
    if m is None:
        return None
    eski = _mod_durum.get('deger')
    _mod_durum['deger'] = m
    if eski and eski != m:
        _mod_degisti(eski, m)
    zaman = int(time.time())
    # 1) Birincil dosya (api_keys.json DEGIL)
    try:
        yol = mod_dosyasi()
        klasor = os.path.dirname(yol)
        if klasor:
            os.makedirs(klasor, exist_ok=True)
        with open(yol, 'w', encoding='utf-8') as f:
            json.dump({'mod': m, 'zaman': zaman}, f,
                      ensure_ascii=False, indent=2)
    except Exception as e:
        log_yaz('mod yazilamadi: %r' % (e,), 'mod')
    # 2) Eski dosyaya ayna (eski surumler tutarli kalsin)
    try:
        for yol in _eski_mod_dosyalari():
            with open(yol, 'w', encoding='utf-8') as f:
                json.dump({'mod': MOD_OFFLINE if m == MOD_OFFLINE else MOD_ONLINE,
                           'zaman': zaman}, f, ensure_ascii=False, indent=2)
            break
    except Exception:
        pass
    log_yaz('baglanti modu degisti: %s' % m, 'mod')
    return m


def _mod_degisti(eski, yeni):
    """Baglanti modu degisti: aktif BULUT gorevlerini durdur.

    OFFLINE'a gecildiginde devam eden bulut tekrarlari durdurulur; boylece
    'ONLINE basladik, sonra OFFLINE secildi' durumunda yeni bulut istegi
    gonderilmez. Kullanici bilgilendirilir.
    """
    if yeni != MOD_OFFLINE:
        log_yaz('baglanti modu degisti: %s -> %s (aktif bulut gorevleri '
                'devam ediyor)' % (eski, yeni), 'mod')
        return 0
    durdurulan = []
    with _gorev_kilit:
        for gid, rec in list(_gorev['aktif'].items()):
            rec['mod_durdu'].set()
            durdurulan.append(gid)
    log_yaz('baglanti modu degisti: %s -> OFFLINE | %d aktif bulut gorevi '
            'durduruldu (%s)' % (eski, len(durdurulan),
                                  ', '.join(durdurulan) or '-'), 'mod')
    _durum['son_mod_degis'] = {'eski': eski, 'yeni': yeni,
                               'durdurulan': len(durdurulan),
                               'gorevler': list(durdurulan)}
    return len(durdurulan)


def mod_degis_bilgisi():
    """Son mod degisliginin ozeti (kullanici bilgilendirmesi icin)."""
    return dict(_durum.get('son_mod_degis') or {})


def mod_sonraki(deger=None):
    """Siradaki mod (auto -> online -> offline -> auto)."""
    m = mod_normalize(deger) or mod_oku()
    try:
        i = MODLAR.index(m)
    except ValueError:
        i = 0
    return MODLAR[(i + 1) % len(MODLAR)]


def mod_oto_mi():
    return mod_oku() == MOD_OTO


def mod_online_mi():
    return mod_oku() == MOD_ONLINE


def mod_offline_mi():
    return mod_oku() == MOD_OFFLINE


def mod_durumu():
    """HUD/teknik log icin mod bilgisi (gizli bilgi YOK)."""
    m = mod_oku()
    return {'mod': m, 'etiket': MOD_ETIKET.get(m, m),
            'kisa': MOD_KISA.get(m, '?'), 'renk': MOD_RENK.get(m, '#ffffff')}


def saglayici_tanimlari():
    """Aktif saglayici tanimlari (config + varsayilan birlestirilir).

    FAZ 4E.4.2: SIRALAMA BURADA DEGIL. Deneme sirasi `_sorgula_ana`
    icinde `DENEME_SIRASI`'na gore yapilir (Gemini her zaman ilk
    denenir). Burada tanimlar YALNIZCA listelenir; yapilandirma
    dosyasinda olmayan saglayici tanimi (model/timeout bilgisi)
    kaybolmamalidir.
    """
    ay = ayarlar()
    liste = ay.get('providers')
    if not isinstance(liste, list) or not liste:
        liste = list(VARSAYILAN_SAGLAYICILAR)
    sonuc = []
    for t in liste:
        if not isinstance(t, dict):
            continue
        ad = str(t.get('name') or '').strip().lower()
        if not ad:
            continue
        if ad not in IZINLI_SAGLAYICILAR:
            continue
        t = dict(t)
        t['name'] = ad
        t.setdefault('enabled', True)
        t.setdefault('style', 'openai')
        t.setdefault('max_tokens', 1200)
        t.setdefault('temperature', 0.4)
        t.setdefault('timeout_s', 25)
        t.setdefault('model', '')
        sonuc.append(t)
    return sonuc


def izinli_saglayicilar():
    return [t['name'] for t in saglayici_tanimlari() if t.get('enabled')]


def _deneme_sirasina_gore(tanimlar):
    """Saglayici tanimlarini DENEME_SIRASI'na gore siralar.

    FAZ 4E.4.2: GEMINI her zaman ILK denenecek saglayicidir.
    * DENEME_SIRASI'da olan saglayicilar: sira numarasina gore once.
    * Listede olmayan saglayicilar: en sona (kendi siralari korunur).
    * `sorted` kararlidir (stable): esit sirali ogeler sirayi korur.
    """
    sira = {}
    for i, ad in enumerate(DENEME_SIRASI):
        sira[ad] = i
    son = len(DENEME_SIRASI)
    return sorted(list(tanimlar or []),
                  key=lambda t: sira.get(str(t.get('name') or ''), son))


def izinli_mi(ad):
    a = str(ad or '').strip().lower()
    if a in YASAKLI_SAGLAYICILAR:
        return False
    return a in IZINLI_SAGLAYICILAR


def model_izinli_mi(ad, model):
    """OpenRouter'da model kimligi ':free' ile BITMEK ZORUNDA."""
    a = str(ad or '').strip().lower()
    if not izinli_mi(a):
        return False
    m = str(model or '').strip()
    if not m:
        return False
    if a == 'openrouter':
        return m.lower().endswith(':free')
    return True


def ucretsiz_uyari():
    return UCRETSIZ_UYARI


# ---------------------------------------------------------------------------
# API anahtarlari (FAZ 4D-1: birden fazla kaynak)
# ---------------------------------------------------------------------------
def _api_dosya_yollari():
    """api_keys.json olasi dosya yollari (etiket, yol)."""
    yollar = []
    kok = None
    try:
        if getattr(sys, 'frozen', False):
            kok = os.path.dirname(os.path.abspath(sys.executable))
        else:
            kok = os.getcwd()
    except Exception:
        kok = os.getcwd()
    if kok:
        yollar.append(('calisma_dizini',
                       os.path.join(kok, 'config', 'api_keys.json')))
    try:
        mod = os.path.dirname(os.path.abspath(__file__))
        yollar.append(('modul_dizini',
                       os.path.join(mod, 'config', 'api_keys.json')))
    except Exception:
        pass
    # EXE dist_JARVIS_AI\config ise, bir ustteki proje kok config'i de
    # taranir (kullanici anahtari oraya yazmis olabilir).
    if kok:
        try:
            ust = os.path.dirname(kok)
            if ust and os.path.isdir(ust) and \
                    os.path.isfile(os.path.join(ust, 'config',
                                                'api_keys.json')):
                yollar.append(('ust_dizin',
                               os.path.join(ust, 'config', 'api_keys.json')))
        except Exception:
            pass
    # tekrarlari at
    benzersiz = []
    gorulen = set()
    for etiket, y in yollar:
        if y in gorulen:
            continue
        gorulen.add(y)
        benzersiz.append((etiket, y))
    return benzersiz


def _api_ayarlari_adaylari():
    """api_keys.json aday icerikleri: [(etiket, sozluk)].

    Mevcut okuma yontemi (jarvis_yetenek.ayarlar()) ONCE denenir; ardindan
    diger aday dosyalar taranir. Anahtar DEGERI burada gosterilmez.
    """
    simdi = time.time()
    if _api_cache['liste'] and (simdi - _api_cache['t']) < 30.0:
        return _api_cache['liste']
    liste = []
    # 1) Mevcut yontem (korunur)
    try:
        import jarvis_yetenek as yt
        ay = yt.ayarlar()
        if isinstance(ay, dict) and ay:
            liste.append(('jarvis_yetenek.ayarlar()', ay))
    except Exception:
        pass
    # 2) Diger aday dosyalar
    for etiket, yol in _api_dosya_yollari():
        try:
            if not os.path.isfile(yol):
                continue
            with open(yol, 'r', encoding='utf-8') as f:
                ay = json.load(f)
            if isinstance(ay, dict) and ay:
                liste.append((etiket, ay))
        except Exception:
            continue
    _api_cache['t'] = simdi
    _api_cache['liste'] = liste
    return liste


def _anahtar_sec(degerler):
    """[(etiket, deger)] listesinden en uygun olani secer.

    Oncelik:
      1) MAKUL gorunen (>= 20 karakter, ASCII) ilk aday
         -> EXE yanindaki dosyada 1 karakterlik bozuk bir anahtar
            varken proje kokundeki gecerli anahtar secilir.
      2) Yoksa en uzun bos olmayan deger.
    Donus: (etiket, deger) veya None.
    """
    dolu = [(e, v) for e, v in degerler if v and str(v).strip()]
    if not dolu:
        return None
    for e, v in dolu:
        s = str(v).strip()
        if len(s) >= 20 and s.isascii():
            return e, s
    return max(dolu, key=lambda x: len(str(x[1]).strip()))


def anahtar_bul(tanim, kaynak_adi=None):
    """Saglayici tanimindan API anahtari (deger ASLA loglanmaz).

    Oncelik: 1) ortam degiskenleri  2) api_keys.json aday dosyalari
    (bos OLMAYAN ve makul gorunen ilk deger).
    """
    ad = str(tanim.get('name') or '')
    for e in (tanim.get('env_keys') or ()):
        try:
            v = (os.environ.get(e) or '').strip()
        except Exception:
            v = ''
        if v:
            if kaynak_adi is not None:
                kaynak_adi.append('ortam:%s' % str(e))
            return v
    alan = str(tanim.get('key_field') or '').strip()
    if not alan:
        return ''
    adaylar = []
    for etiket, ay in _api_ayarlari_adaylari():
        try:
            v = str(ay.get(alan) or '').strip()
        except Exception:
            v = ''
        if v:
            adaylar.append((etiket, v))
    secim = _anahtar_sec(adaylar)
    if secim is None:
        return ''
    if kaynak_adi is not None:
        kaynak_adi.append('dosya:%s' % secim[0])
    return secim[1]


def model_tercihi_kontrol(tanim, ay=None):
    """Kullanici model tercihi denetimi (FAZ 4E.1).

    * Gecerli ve desteklenen ozel tercih  -> KORUNUR
    * Kapatilmis/eme kli model tercihi     -> guncel kararli modele
      OTOMATIK olarak yukseltilir (loglanir)
    * Tercih yoksa                       -> saglayici varsayilani

    Donus: {'tercih', 'kullanilan', 'eskimis', 'not'}
    """
    ad = str(tanim.get('name') or '')
    alan = 'ai_model_' + ad
    varsayilan = str(tanim.get('model') or '').strip()
    tercih = ''
    try:
        v = str((ay or {}).get(alan) or '').strip()
    except Exception:
        v = ''
    kaynak = 'ai_routing.json'
    if not v:
        for _etiket, api_ay in _api_ayarlari_adaylari():
            try:
                v = str(api_ay.get(alan) or '').strip()
            except Exception:
                v = ''
            if v:
                tercih = v
                kaynak = 'api_keys.json'
                break
    else:
        tercih = v
    if not tercih:
        return {'tercih': '', 'kullanilan': varsayilan, 'eskimis': False,
                'kaynak': 'varsayilan',
                'not': 'kullanici tercihi yok; varsayilan kullanildi'}
    if tercih.lower() in ESKIMIS_MODELLER:
        return {'tercih': tercih, 'kullanilan': varsayilan, 'eskimis': True,
                'kaynak': kaynak,
                'not': ('kullanici model tercihi emekli/kapatilmis (%s); '
                        'guncel model kullanildi (%s)' % (tercih,
                                                           varsayilan))}
    return {'tercih': tercih, 'kullanilan': tercih, 'eskimis': False,
            'kaynak': kaynak, 'not': 'kullanici tercihi gecerli, korundu'}


def _model_bul(tanim, ay=None):
    """Kullanilacak model kimligi (bkz. model_tercihi_kontrol).

    FAZ 4E.1: Kullanici tercihi KAPATILMIS/EMEKLI bir model ise
    (ornek gemini-1.5-flash, gemini-2.0-flash) guncel kararli modele
    OTOMATIK gecilir ve bu durum loglanir. Gecerli ve desteklenen
    ozel tercihler KORUNUR.
    """
    sonuc = model_tercihi_kontrol(tanim, ay)
    if sonuc['eskimis']:
        log_yaz(sonuc['not'], 'model')
    return sonuc['kullanilan']


def _model_adaylari(tanim, secilen):
    """Denenecek model listesi: secilen + saglayici yedekleri.

    Model bulunamazsa (404) siradaki model denenir; boylece hatali model
    yuzunden saglayici kalici olarak devre disi birakilmaz.
    """
    liste = [secilen]
    for m in (tanim.get('model_yedekleri') or ()):
        m = str(m or '').strip()
        if m and m not in liste:
            liste.append(m)
    return liste


# ---------------------------------------------------------------------------
# Ag yardimcilari
# ---------------------------------------------------------------------------
def _yerel_mi(host):
    if not isinstance(host, str) or host == "":
        return True
    h = host.strip("[]").lower()
    return h in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or \
        h.startswith("127.")


def izinli_alan_adlari():
    """Soket muhafizasinin kullanacagi izinli alan adlari (kucuk harf)."""
    adlar = set(IZINLI_ALAN_ADLARI)
    for t in saglayici_tanimlari():
        if not t.get('enabled'):
            continue
        u = str(t.get('url') or '')
        try:
            from urllib.parse import urlparse
            ag = urlparse(u).hostname
            if ag:
                adlar.add(ag.lower())
        except Exception:
            continue
    return adlar


def alan_adi_izinli_mi(host):
    h = str(host or '').strip().lower().rstrip('.')
    if not h:
        return False
    if _yerel_mi(h):
        return True
    return h in izinli_alan_adlari()


def _internet_probe():
    """İnternet var mı? (sadece izinli alan adlarina TCP 443 denemesi).

    DNS hatasi ile baglanti hatasi AYRI kaydedilir.
    """
    dns_hata = []
    bag_hata = []
    for ad in sorted(izinli_alan_adlari()):
        if _yerel_mi(ad):
            continue
        s = None
        try:
            s = socket.create_connection((ad, 443), timeout=5.0)
            _durum['internet_not'] = 'erişilebilir: %s' % ad
            return True
        except socket.gaierror as e:
            dns_hata.append('%s:%s' % (ad, str(e)[:60]))
            continue
        except socket.timeout:
            bag_hata.append('%s:zaman asimi' % ad)
            continue
        except OSError as e:
            bag_hata.append('%s:%s' % (ad, str(e)[:60]))
            continue
        except Exception as e:
            bag_hata.append('%s:%s' % (ad, str(e)[:60]))
            continue
        finally:
            try:
                if s is not None:
                    s.close()
            except Exception:
                pass
    if dns_hata:
        _durum['internet_not'] = 'DNS cozumlemesi basarisiz (%s)' % \
                                ', '.join(dns_hata[:2])
    elif bag_hata:
        _durum['internet_not'] = 'baglanti kurulamadi (%s)' % \
                                ', '.join(bag_hata[:2])
    else:
        _durum['internet_not'] = 'izinli saglayici alan adi yok'
    return False


def internet_var(zorla_yenile=False):
    """İnternet erişimi var mı? (kısa süreli önbellekli)"""
    ay = ayarlar()
    sure = float(ay.get('internet_check_interval_s') or 60.0)
    simdi = time.time()
    if not zorla_yenile and _durum['internet'] is not None and \
            (simdi - _durum['internet_t']) < sure:
        return bool(_durum['internet'])
    var = False
    try:
        var = bool(_internet_probe())
    except Exception as e:
        _durum['internet_not'] = 'probe hatasi: %s' % str(e)[:80]
        var = False
    _durum['internet'] = var
    _durum['internet_t'] = simdi
    log_yaz('internet kontrolu: %s (%s)'
            % ('VAR' if var else 'YOK', _durum['internet_not']), 'internet')
    return var


# ---------------------------------------------------------------------------
# HTTP (TLS dogrulamasi AKTIF, hata siniflandirmali)
# ---------------------------------------------------------------------------
#: Guvenilir CA paketi (certifi) - PyInstaller ile birlikte paketlenir.
_CACERT_ADI = 'cacert.pem'


def _cacert_yollari():
    """Guvenilir CA dosyasi arama yollari (guvenilir kaynaklar only)."""
    yollar = []
    try:
        import certifi
        yollar.append(certifi.where())
    except Exception:
        pass
    try:
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            yollar.append(os.path.join(meipass, 'certifi', _CACERT_ADI))
            yollar.append(os.path.join(meipass, _CACERT_ADI))
            # Eski FAZ 4E.1 yerlesimi (klasor icinde) - savunmaci arama
            yollar.append(os.path.join(meipass, '_cacert.pem', _CACERT_ADI))
    except Exception:
        pass
    try:
        yollar.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'certifi', _CACERT_ADI))
    except Exception:
        pass
    try:
        ca = ssl.get_default_verify_paths().cafile
        if ca:
            yollar.append(ca)
    except Exception:
        pass
    temiz = []
    for y in yollar:
        if y and y not in temiz:
            temiz.append(y)
    return temiz


def _cacert_bul():
    """Mevcut guvenilir CA dosyasi yolunu dondurur (yoksa None)."""
    for y in _cacert_yollari():
        try:
            if os.path.isfile(y) and os.path.getsize(y) > 1000:
                return y
        except Exception:
            continue
    return None


def _ssl_baglam():
    """Dogrulayan SSL baglami (verify=False / CERT_NONE YOK).

    * verify_mode = CERT_REQUIRED, check_hostname = True (DAIMA ACIK)
    * Windows CA deposu bos kalirsa guvenilir CA paketi (certifi) yuklenir.
      Boylece PyInstaller/frozen ortamda da dogrulama KAYBOLMAZ.
    """
    baglam = ssl.create_default_context()
    try:
        if len(baglam.get_ca_certs()) == 0:
            yol = _cacert_bul()
            if yol:
                baglam.load_verify_locations(cafile=yol)
                log_yaz('CA deposu bos; guvenilir CA paketi yuklendi: %s'
                        % os.path.basename(yol), 'tls')
    except Exception as e:
        log_yaz('CA paketi yuklenemedi: %r' % (e,), 'tls')
    return baglam


def tls_durum():
    """TLS/CA durumu (gizli bilgi YOK) - teknik tani icin."""
    baglam = ssl.create_default_context()
    ca_sayi = 0
    try:
        ca_sayi = len(baglam.get_ca_certs())
    except Exception:
        pass
    paket = _cacert_bul()
    return {
        'ssl_surumu': ssl.OPENSSL_VERSION,
        'verify_mode': str(baglam.verify_mode),
        'verify_kodu': int(baglam.verify_mode),
        'check_hostname': bool(baglam.check_hostname),
        'ca_sayisi': ca_sayi,
        'ca_paketi': os.path.basename(paket) if paket else None,
        'ca_paketi_var': bool(paket),
        'varsayilan_ca_yolu': ssl.get_default_verify_paths().cafile,
        'tls_dogrulama': 'aktif (verify=False / CERT_NONE kullanilmaz)',
    }


def _adres_sirala(sonuc):
    """getaddrinfo sonucunu IPv4-oncelikli sirala.

    TLS DOGRULMASI DEGISTIRILMEZ; yalnizca IP ailesi DENEME SIRASI degisir.
    (Bazi aglarda IPv6 uclari TLS el sikmasini bozuyor.)
    """
    try:
        v4 = [r for r in (sonuc or ()) if r[0] == socket.AF_INET]
        rest = [r for r in (sonuc or ()) if r[0] != socket.AF_INET]
        return (v4 + rest) if v4 else list(sonuc or ())
    except Exception:
        return list(sonuc or ())


#: Zorlanacak IP ailesi (thread-local; aile denemesi icin)
_aile_durum = threading.local()

#: getaddrinfo yamasinin kurulum durumu
_gai_durum = {'kurulu': False}


def _getaddrinfo_ipv4_kur():
    """getaddrinfo'yi IPv4-oncelikli yapar (IDEMPOTENT).

    * TLS dogrulama, sertifika dogrulama, hostname kontrolu DEGISTIRILMEZ.
    * Yalnizca IP ailelerinin DENEME SIRASI degisir.
    * main.pyc'nin '_ipv4_once' yamasindan BAGIMSIZ calisir; boylece router
      kendi bulut baglantisindan tek basina sorumludur.
    """
    if _gai_durum['kurulu']:
        return True
    try:
        orj = socket.getaddrinfo
        if getattr(orj, '_jarvis_ai_router_v4', False):
            _gai_durum['kurulu'] = True
            return True

        def getaddrinfo(host, port, *a, **k):
            sonuc = orj(host, port, *a, **k)
            aile = getattr(_aile_durum, 'aile', None)
            if aile is not None:
                sec = [r for r in (sonuc or ()) if r[0] == aile]
                return sec or list(sonuc or ())
            return _adres_sirala(sonuc)

        getaddrinfo._jarvis_ai_router_v4 = True
        socket.getaddrinfo = getaddrinfo
        _gai_durum['kurulu'] = True
        return True
    except Exception as e:
        log_yaz('getaddrinfo IPv4 onceligi kurulamadi: %r' % (e,), 'tls')
        return False


def _http_kategori(kod):
    """HTTP durum kodu -> (kategori, aciklama)."""
    if kod == 401:
        return 'yetki', 'API anahtari gecersiz veya yetkisiz'
    if kod == 403:
        return 'yetki', 'erisim reddedildi (kota veya yetki)'
    if kod == 404:
        return 'model', 'model veya uc nokta bulunamadi'
    if kod == 429:
        return 'kota', 'kota asildi (rate limit)'
    if 500 <= kod < 600:
        return 'sunucu', 'saglayici sunucusu hatasi'
    if 400 <= kod < 500:
        return 'istek', 'istek reddedildi'
    return 'hata', 'beklenmeyen HTTP durumu'


#: TLS hata siniflari (ayri raporlanir; gizli bilgi icermez)
TLS_KATEGORI = {
    'tls_zincir': 'sertifika zinciri guvenilmiyor',
    'tls_suresi': 'sertifika suresi gecersiz',
    'tls_sunucu_adi': 'sunucu adi eslesmedi',
    'tls_ca_yok': 'CA dosyasi bulunamadi',
    'tls_baglanti': 'TLS baglantisi kurulamadi',
    'tls_mudahale': 'proxy veya guvenlik yazilimi mudahalesi suphesi',
    'tls': 'TLS dogrulama hatasi',
}


def _tls_hata_sinifla(hata):
    """SSL hatasini ayrintili guvenli kategoriye cevirir.

    Donus: (kategori, aciklama). API anahtari / sohbet / sertifika verisi
    ASLA yazilmaz; sadece hata sinifi ve kisa aciklama kullanilir.
    """
    kod = getattr(hata, 'verify_code', None)
    mesaj = str(hata)
    al = mesaj.lower()
    try:
        if kod is not None:
            if int(kod) == 10:
                return 'tls_suresi', 'sertifika suresi gecersiz'
            if int(kod) == 62:
                return 'tls_sunucu_adi', 'sunucu adi eslesmedi'
            if int(kod) in (18, 19, 20, 21, 22, 23, 24):
                return 'tls_zincir', 'sertifika zinciri guvenilmiyor'
    except Exception:
        pass
    if 'hostname mismatch' in al or 'not valid for' in al or \
            'no appropriate commonname' in al:
        return 'tls_sunucu_adi', 'sunucu adi eslesmedi'
    if 'expired' in al or 'not yet valid' in al or 'certificate has expired' \
            in al:
        return 'tls_suresi', 'sertifika suresi gecersiz'
    if 'unable to get local issuer' in al or 'self signed' in al or \
            'self-signed' in al or 'unable to verify' in al:
        return 'tls_zincir', 'sertifika zinciri guvenilmiyor'
    if 'no ca' in al or 'ca certificates' in al or 'no certificates' in al:
        return 'tls_ca_yok', 'CA dosyasi bulunamadi'
    if 'wrong version number' in al or 'unexpected eof' in al or \
            'record layer failure' in al or 'unknown protocol' in al or \
            'unsupported protocol' in al or 'tlsv1 alert' in al or \
            'decryption failed' in al:
        return 'tls_mudahale', ('proxy veya guvenlik yazilimi mudahalesi '
                               'suphesi')
    if 'invalid session id' in al or 'session' in al or \
            'handshake' in al:
        return 'tls_baglanti', ('TLS oturum/handshake hatasi (IP ailesi veya '
                                 'arakatman sorunu olabilir)')
    return 'tls', 'TLS dogrulama hatasi'


def http_post(url, veri, basliklar=None, zaman=25):
    """JSON POST (TLS dogrulamasi AKTIF, aile-seviyesi tekrarli).

    * Once IPv4 denenir, sonra IPv6 (IPv6 TLS arizalari nedeniyle).
      Boylece bir adresin TLS hatasi tum istegi oldurmez.
    * HTTP hatalari siniflandirilir. Hata GOVDESI ASLA loglanmaz (anahtar
      veya hassas veri icerebilir); yalnizca durum kodu ve kisa aciklama
      kullanilir.
    """
    govde = json.dumps(veri).encode('utf-8')
    h = {'Content-Type': 'application/json'}
    h.update(basliklar or {})
    istek = urllib.request.Request(url, data=govde, headers=h)
    baglam = _ssl_baglam()
    _getaddrinfo_ipv4_kur()

    son_hata = None
    for aile in (socket.AF_INET, socket.AF_INET6):
        _aile_durum.aile = aile
        try:
            with urllib.request.urlopen(istek, timeout=zaman,
                                       context=baglam) as yanit:
                return json.loads(yanit.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as e:
            # HTTP durum kodu IP ailesiyle ilgili DEGIL -> tekrar deneme.
            kod = int(getattr(e, 'code', 0) or 0)
            tur, aciklama = _http_kategori(kod)
            # 429 kota: Retry-After basligini (varsa) al - kota bekleme
            # politikasi icin kullanilir. Baslik degeri loglanmaz.
            retry_after = None
            if kod == 429:
                try:
                    hdr = getattr(e, 'headers', None)
                    if hdr is not None:
                        v = hdr.get('Retry-After')
                        if v:
                            retry_after = float(v)
                except Exception:
                    retry_after = None
            raise RouterHatasi("HTTP %d: %s" % (kod, aciklama), tur,
                               http_kod=kod, retry_after=retry_after)
        except urllib.error.URLError as e:
            sebep = getattr(e, 'reason', None)
            metin = str(sebep or e)
            al = metin.lower()
            if isinstance(sebep, (socket.timeout, TimeoutError)) or \
                    'timed out' in al or 'timeout' in al:
                raise RouterHatasi("zaman asimi (%d sn)" % zaman, 'zaman')
            if isinstance(sebep, (ssl.SSLError, ssl.CertificateError)):
                son_hata = e
                continue          # diger IP ailesiyle tekrar dene
            if 'certificate' in al or 'ssl' in al or 'tls' in al:
                son_hata = e
                continue          # diger IP ailesiyle tekrar dene
            if 'getaddrinfo' in al or 'name or service not known' in al or \
                    'nodename' in al or 'name resolution' in al:
                raise RouterHatasi("DNS cozumlemesi basarisiz", 'dns')
            son_hata = e
            continue              # baglanti hatasi: diger aileyi dene
        except (socket.timeout, TimeoutError):
            raise RouterHatasi("zaman asimi (%d sn)" % zaman, 'zaman')
        except ssl.SSLError as e:
            son_hata = e
            continue
        except Exception as e:
            raise RouterHatasi("istek hatasi: %s" % str(e)[:110], 'hata')
        finally:
            _aile_durum.aile = None

    # Her iki aile de basarisiz: son hatayi guvenle siniflandir.
    sebep = getattr(son_hata, 'reason', None) if son_hata is not None else None
    metin = str(sebep or son_hata or '')
    al = metin.lower()
    if isinstance(sebep, (ssl.SSLError, ssl.CertificateError)) or \
            'certificate' in al or 'ssl' in al or 'tls' in al:
        tur, aciklama = _tls_hata_sinifla(sebep or metin)
        raise RouterHatasi("TLS hatasi: %s" % aciklama, tur)
    if 'getaddrinfo' in al or 'name or service not known' in al:
        raise RouterHatasi("DNS cozumlemesi basarisiz", 'dns')
    raise RouterHatasi("baglanti hatasi: %s" % metin[:110], 'baglanti')


# ---------------------------------------------------------------------------
# Saglayici istekleri
# ---------------------------------------------------------------------------
def _gecmis_ciftleri(gecmis):
    """Gecmisi model mesajlarina (rol/icerik) cevir.

    Iki bicimi kabul eder:
      * HUD bicimi  : ['Kullanici: ...', 'JARVIS: ...']
      * Model bicimi: [{'role': 'user', 'content': '...'}]
    """
    cikti = []
    for g in (gecmis or []):
        if isinstance(g, dict):
            rol = str(g.get('role') or 'user')
            icerik = str(g.get('content') or '')
            if icerik:
                cikti.append({'role': rol, 'content': icerik})
            continue
        s = str(g)
        if s.startswith('Kullanıcı: '):
            cikti.append({'role': 'user', 'content': s[len('Kullanıcı: '):]})
        elif s.startswith('Kullanici: '):
            cikti.append({'role': 'user', 'content': s[len('Kullanici: '):]})
        elif s.startswith('JARVIS: '):
            cikti.append({'role': 'assistant',
                          'content': s[len('JARVIS: '):]})
    return cikti


def _mesajlari(soru, sistem=None, gecmis=None):
    """Sistem + gecmis + soru -> OpenAI uyumlu mesaj listesi."""
    m = []
    s = str(sistem or '').strip()
    if s:
        m.append({'role': 'system', 'content': s})
    m.extend(_gecmis_ciftleri(gecmis))
    m.append({'role': 'user', 'content': str(soru or '')})
    return m


def _gemini_istek(tanim, model, anahtar, soru, sistem, gecmis, zaman,
                  max_tokens, sicaklik):
    url = str(tanim.get('url') or '') % model
    icerik = []
    for g in _gecmis_ciftleri(gecmis):
        rol = str(g.get('role') or 'user')
        ic = str(g.get('content') or '')
        if not ic:
            continue
        icerik.append({'role': 'model' if rol == 'assistant' else 'user',
                        'parts': [{'text': ic}]})
    icerik.append({'role': 'user', 'parts': [{'text': str(soru or '')}]})
    veri = {
        'contents': icerik,
        'generationConfig': {
            'temperature': float(sicaklik),
            'maxOutputTokens': int(max_tokens),
        },
    }
    s = str(sistem or '').strip()
    if s:
        veri['systemInstruction'] = {'parts': [{'text': s}]}
    # Anahtar BASLIKTA gider -> URL/loglara sizmaz.
    cevap = http_post(url, veri, {'x-goog-api-key': anahtar}, zaman)
    try:
        return str(cevap['candidates'][0]['content']['parts'][0]['text']).strip()
    except Exception:
        return ''


def _openai_istek(tanim, model, anahtar, soru, sistem, gecmis, zaman,
                  max_tokens, sicaklik):
    veri = {
        'model': model,
        'messages': _mesajlari(soru, sistem, gecmis),
        'max_tokens': int(max_tokens),
        'temperature': float(sicaklik),
    }
    basliklar = {'Authorization': 'Bearer ' + str(anahtar)}
    cevap = http_post(str(tanim.get('url') or ''), veri, basliklar, zaman)
    try:
        return str(cevap['choices'][0]['message']['content']).strip()
    except Exception:
        return ''


def saglayici_istegi(tanim, model, anahtar, soru, sistem=None, gecmis=None,
                      zaman=None, max_tokens=None, sicaklik=None):
    """Tek bir IZINLI saglayiciya istek atar. Donus: cevap metni.

    FAZ 4E.3: Zaman asimi cagiranin 'zaman' parametresinden DEGIL,
    saglayicinin kendi 'timeout_s' degerinden alinir ve BULUT_TIMEOUT_TAVAN
    ile sinirlanir. (Cagiranin 'zaman' degeri YEREL model butcesidir;
    300 sn olmasi bulut istegini 5 dakika blokluyordu.)
    """
    ad = str(tanim.get('name') or '')
    if not izinli_mi(ad):
        raise RouterHatasi(
            "Izin listesinde olmayan saglayici reddedildi: %s" % ad, 'saglayici')
    if not model_izinli_mi(ad, model):
        raise RouterHatasi(
            "Model bu saglayici icin ucretsiz/kullanilabilir degil: %s/%s"
            % (ad, model), 'model')
    if not anahtar:
        raise RouterHatasi("API anahtari yok: %s" % ad, 'anahtar')
    try:
        z = int(tanim.get('timeout_s') or 25)
    except Exception:
        z = 25
    z = max(BULUT_TIMEOUT_ASGARI, min(z, BULUT_TIMEOUT_TAVAN))
    mt = int(max_tokens or tanim.get('max_tokens') or 1200)
    st = float(sicaklik if sicaklik is not None
               else tanim.get('temperature') or 0.4)
    stil = str(tanim.get('style') or 'openai')
    if stil == 'gemini':
        return _gemini_istek(tanim, model, anahtar, soru, sistem, gecmis,
                             z, mt, st)
    return _openai_istek(tanim, model, anahtar, soru, sistem, gecmis,
                         z, mt, st)


# ---------------------------------------------------------------------------
# Saglik onbellegi (kategoriye gore kisa sureli devre disi kalma)
# ---------------------------------------------------------------------------
def _kategori_ttl(tur=None):
    ay = ayarlar()
    tablo = ay.get('provider_health_ttl_by_category')
    if isinstance(tablo, dict):
        try:
            v = float(tablo.get(tur or 'varsayilan') or 0)
            if v > 0:
                return v
        except Exception:
            pass
    try:
        v = float(ay.get('provider_health_ttl_s') or 0)
        if v > 0:
            return v
    except Exception:
        pass
    return VARSAYILAN_KATEGORI_TTL.get(tur or 'varsayilan', 30.0)


def saglik(ad):
    return dict(_durum['saglik'].get(ad) or {})


def devre_durumu(ad):
    """Devre kesici durumu (kullanici mesaji icin de kullanilir).

    durum: 'kapali' (normal) | 'acik' (gecici olarak devre disi) |
            'yarim' (bekleme bitti, tek deneme hakki var)
    """
    rec = _durum['saglik'].get(ad) or {}
    bas = float(rec.get('acik_baslangic') or rec.get('t') or 0.0)
    gecen = time.time() - bas
    kalan = float(rec.get('acik_kalan') or 0.0) - gecen
    return {
        'ad': ad,
        'durum': rec.get('durum') or 'kapali',
        'basarisiz': int(rec.get('basarisiz') or 0),
        'kalan_sn': round(max(0.0, kalan), 1),
        'son_hata': rec.get('hata') or '',
        'son_tur': rec.get('tur') or '',
        'http_kod': rec.get('http_kod'),
    }


def _saglik_basari(ad):
    """Basarili istek -> devre kesici kapanir, hata sayaci sifirlanir."""
    _durum['saglik'][ad] = {'ok': True, 't': time.time(), 'hata': '',
                             'tur': '', 'ttl': 0.0, 'basarisiz': 0,
                             'durum': 'kapali', 'acik_kalan': 0.0,
                             'acik_baslangic': 0.0, 'http_kod': None}


def _saglik_hata(ad, tur=None, hata='', http_kod=None):
    """Basarisiz istek -> devre kesici guncellenir.

    * Gecici hata  -> artan bekleme (15/30/60/120 sn), 'acik' durum
    * Kalici hata  -> yapilandirma beklemesi (kategori TTL'i)
    Basarisizlik sayaci artar; basarida sifirlanir.
    """
    rec = dict(_durum['saglik'].get(ad) or {})
    n = int(rec.get('basarisiz') or 0) + 1
    tur = str(tur or rec.get('tur') or 'hata')
    if tur in DEVRE_GECICI_TURLER:
        bekleme = DEVRE_BEKLEME_SN[min(n - 1, len(DEVRE_BEKLEME_SN) - 1)]
        bekleme = min(bekleme, DEVRE_BEKLEME_TAVAN)
    else:
        bekleme = float(_kategori_ttl(tur))
    now = time.time()
    _durum['saglik'][ad] = {'ok': False, 't': now, 'hata': str(hata or '')[:200],
                             'tur': tur, 'ttl': bekleme, 'basarisiz': n,
                             'durum': 'acik', 'acik_kalan': bekleme,
                             'acik_baslangic': now, 'http_kod': http_kod}
    return bekleme


def _saglik_guncelle(ad, ok, hata='', tur=None):
    """Uyumluluk sarmalayicisi (eski cagri imzasi)."""
    if ok:
        _saglik_basari(ad)
    else:
        _saglik_hata(ad, tur=tur, hata=hata)


def _saglik_uygun(ad):
    """Saglayici su an denenmeye uygun mu?

    * Gecici hata  -> devre kesici: bekleme bittiyse 'yarim' (tek deneme)
    * Kalici hata  -> kategori TTL'i kadar bekle
    * Basarili      -> her zaman uygun
    """
    rec = _durum['saglik'].get(ad)
    if not rec:
        return True
    if rec.get('ok'):
        return True
    tur = str(rec.get('tur') or '')
    bas = float(rec.get('acik_baslangic') or rec.get('t') or 0.0)
    gecen = time.time() - bas
    if tur in DEVRE_GECICI_TURLER:
        bekleme = float(rec.get('acik_kalan') or 0.0)
        if gecen < bekleme:
            return False
        # Bekleme bitti -> YARIM ACIK: tek deneme hakki verilir.
        rec['durum'] = 'yarim'
        return True
    ttl = float(rec.get('ttl') or 0.0) or _kategori_ttl(tur)
    return gecen > ttl


# ---------------------------------------------------------------------------
# FAZ 4E.2: Gecici hata yeniden deneme yardimcilari
# ---------------------------------------------------------------------------
def bekleme_suresi(deneme_no, tur='sunucu', retry_after=None):
    """Artan bekleme araligi + kucuk rastgele fark.

    HTTP 429 (kota) icin AYRI politika kullanilir.
    """
    tablo = KOTA_BEKLEME_SN if tur == 'kota' else RETRY_BEKLEME_SN
    i = max(0, min(int(deneme_no) - 1, len(tablo) - 1))
    bekleme = float(tablo[i])
    fark = bekleme * RETRY_JITTER
    bekleme += random.uniform(-fark, fark)
    if tur == 'kota':
        bekleme = min(bekleme, KOTA_RETRY_AFTER_TAVAN)
    else:
        bekleme = min(bekleme, RETRY_TEK_TAVAN)
    bekleme = max(0.5, bekleme)
    if retry_after:
        # Retry-After (kota/hiz siniri) BEKLEME ALT SINIRIDIR.
        try:
            bekleme = max(bekleme, float(retry_after))
        except Exception:
            pass
    return round(bekleme, 2)


def uyku_ile(iptal, saniye):
    """Iptal edilebilir bekleme.

    Donus: True (suresi doldu) | False (iptal edildi)
    """
    if saniye is None or saniye <= 0:
        return True
    bitis = time.time() + float(saniye)
    while True:
        if iptal is not None:
            try:
                if iptal.is_set():
                    return False
            except Exception:
                pass
        kalan = bitis - time.time()
        if kalan <= 0:
            return True
        time.sleep(min(0.25, kalan))


def _hata_ozeti(tur):
    """Hata turunun kisa kullanici dilindeki aciklamasi (HUD metni)."""
    return {
        'sunucu': 'sunucu hatası veriyor',
        'zaman': 'zaman aşımına uğradı',
        'baglanti': 'bağlantı kurulamadı',
        'dns': 'adres çözümlenemedi',
        'tls': 'TLS doğrulama hatası veriyor',
        'tls_zincir': 'sertifika zinciri hatası veriyor',
        'tls_suresi': 'sertifika süresi geçersiz',
        'tls_sunucu_adi': 'sunucu adı eşleşmedi',
        'tls_ca_yok': 'CA dosyası bulunamadı',
        'tls_baglanti': 'TLS bağlantısı kurulamadı',
        'tls_mudahale': 'TLS bağlantısı engellendi (proxy/güvenlik yazılımı '
                       'şüphesi)',
        'yetki': 'API anahtarı reddedildi',
        'model': 'model bulunamadı',
        'kota': 'kota sınırına takıldı',
        'istek': 'istek reddedildi',
    }.get(tur, 'yanıt veremedi')


def aktif_model_bilgisi():
    """ONLINE/AUTO modunda kullanilacak ILK model bilgisi (HUD icin).

    FAZ 4E.4.2 §1: "Kullaniciya aktif model gosterilsin."
    Donus: {'saglayici','model','kaynak','mod','bulut_acik'} veya None.
    """
    try:
        mod = mod_oku()
        if mod == MOD_OFFLINE:
            return {'saglayici': YEREL_SAGLAYICI, 'model': 'qwen3:4b',
                    'kaynak': kaynak_etiketi(YEREL_SAGLAYICI, 'qwen3:4b'),
                    'mod': mod, 'bulut_acik': False}
        ay = ayarlar()
        tanimlar = _deneme_sirasina_gore(saglayici_tanimlari())
        for t in tanimlar:
            if not t.get('enabled'):
                continue
            if not izinli_mi(t.get('name')):
                continue
            model = _model_bul(t, ay)
            if not model:
                continue
            return {'saglayici': t['name'], 'model': model,
                    'kaynak': kaynak_etiketi(t['name'], model),
                    'mod': mod, 'bulut_acik': True}
    except Exception:
        pass
    return None


def _saglayici_adi(ad):
    return SAGLAYICI_AD.get(str(ad or ''), str(ad or ''))


def kaynak_etiketi(saglayici, model=None):
    """Cevabin GERCEK kaynagi (kullaniciya gosterilecek etiket).

    FAZ 4E.4.2 §5: Yerel modelin cevabi GEMINI CEVABI GIBI GOSTERILMEZ.
    * Gemini  -> 'Gemini 3.8-flash'
    * Ollama  -> 'Ollama Qwen3:4b'
    * Digeri  -> '<Saglayici> <model>'
    """
    ad = str(saglayici or '').strip().lower()
    if ad == YEREL_SAGLAYICI:
        return 'Ollama Qwen3:4b'
    if ad == 'gemini':
        m = str(model or '').strip()
        return 'Gemini %s' % (m.replace('gemini-', '') if m else '3.8-flash')
    if ad:
        return '%s %s' % (_saglayici_adi(ad), str(model or '').strip())
    return 'bilinmiyor'


def hata_mesaji(ad, tur, http_kod=None):
    """Kullaniciya gosterilecek tek satirlik hata aciklamasi."""
    ozet = _hata_ozeti(tur)
    if http_kod:
        return "%s şu anda %s (HTTP %d)" % (_saglayici_adi(ad), ozet,
                                            int(http_kod))
    return "%s şu anda %s" % (_saglayici_adi(ad), ozet)


# ---------------------------------------------------------------------------
# FAZ 4E.2: Istek cakismasi (yinelenen istek onleme + iptal)
# ---------------------------------------------------------------------------
def istek_anahtari(metin, mod=None, ders_modu=False):
    """Ayni sohbet icin ayni istegi tanimlayan anahtar."""
    m = ' '.join(str(metin or '').strip().lower().split())
    return '%s|%s|%s' % (m[:160], mod or mod_oku(),
                         'ders' if ders_modu else 'normal')


def _ucus_al(anahtar):
    """Ucus kaydini al. Donus: (kayit, sahip_mi).

    Ayni anahtarla devam eden bir istek varsa sahip_mi=False doner;
    cagiran taraf mevcut istegin sonucunu bekler.
    """
    with _ucus_kilit:
        # Kaynak tüketimi: tamamlanmis/eskimiş kayitlar temizlenir.
        simdi = time.time()
        for k, rec in list(_ucus.items()):
            bitti = rec['olay'].is_set()
            yas = simdi - float(rec.get('baslangic') or 0.0)
            if bitti or yas > UCUS_TAVAN:
                _ucus.pop(k, None)
        rec = _ucus.get(anahtar)
        if rec is not None:
            yas = time.time() - float(rec.get('baslangic') or 0.0)
            if (not rec['olay'].is_set()) and yas < UCUS_TAVAN:
                return rec, False
        rec = {'olay': threading.Event(), 'iptal': threading.Event(),
               'sonuc': None, 'hata': None, 'baslangic': time.time(),
               'sahip': threading.get_ident()}
        _ucus[anahtar] = rec
        return rec, True


def istek_iptal(anahtar=None):
    """Devam eden istegi iptal eder.

    * anahtar verilirse yalniz o istek,
    * verilmezse TUM devam eden istekler iptal edilir.
    Donus: iptal edilen istek sayisi.
    """
    n = 0
    with _ucus_kilit:
        for k, rec in list(_ucus.items()):
            if anahtar is not None and k != anahtar:
                continue
            try:
                rec['iptal'].set()
                n += 1
            except Exception:
                continue
    if n:
        log_yaz('istek iptal edildi: %d istek' % n, 'iptal')
    return n


def devam_eden_istekler():
    """Devam eden isteklerin sayisi (tanilama)."""
    with _ucus_kilit:
        return len([r for r in _ucus.values() if not r['olay'].is_set()])


# ---------------------------------------------------------------------------
# FAZ 4E.3: GOREV (TASK) YASAM DONGUSU
# ---------------------------------------------------------------------------
#: Her istek benzersiz bir gorev kimligi alir; baslangic/deneme/basari/
#: hata/iptal/bitis kayitlari router.log'a yazilir. Boylece bir istegin
#: NEREDE durdugu (asama gecislerinde) kanitlanabilir.
_gorev = {'sayac': 0, 'aktif': {}}
_gorev_kilit = threading.Lock()

#: Yerel model (Ollama) eszamanlilik siniri. 4 GB / GTX 1650 makinede
#: es zamanli 2 istek modeli bos yazdiriyor -> tek istek siraya girer.
_yerel_kilit = threading.Semaphore(1)


def gorev_id_uret():
    """Benzersiz gorev kimligi (g000001, g000002, ...)."""
    with _gorev_kilit:
        _gorev['sayac'] += 1
        return "g%06d" % _gorev['sayac']


def gorev_baslat(gorev_id, mod=None, tur='sohbet'):
    """Gorev baslangic kaydi (kimlik + iptal + mod olaylari)."""
    with _gorev_kilit:
        _gorev['aktif'][gorev_id] = {
            'bas': time.time(), 'mod': mod, 'tur': tur,
            'iptal': threading.Event(), 'mod_durdu': threading.Event(),
            'terminal': False, 'faz': 'basladi'}
    log_yaz('gorev basladi: id=%s mod=%s tur=%s' % (gorev_id, mod, tur),
            'gorev')
    return gorev_id


def gorev_kayit(gorev_id):
    """Gorev kaydini dondurur (yoksa None)."""
    with _gorev_kilit:
        rec = _gorev['aktif'].get(gorev_id)
        return dict(rec) if rec else None


def gorev_iptal_iste(gorev_id, neden='kullanici iptali'):
    """Tek bir gorevi iptal et (olay bayragi)."""
    with _gorev_kilit:
        rec = _gorev['aktif'].get(gorev_id)
        if not rec:
            return False
        rec['iptal'].set()
    log_yaz('gorev iptal istendi: id=%s (%s)' % (gorev_id, neden),
            'gorev')
    return True


def gorev_mod_durdur(gorev_id, neden='mod degisti'):
    """Gorevin BULUT fazini durdur (yerel modele gecis icin)."""
    with _gorev_kilit:
        rec = _gorev['aktif'].get(gorev_id)
        if not rec:
            return False
        rec['mod_durdu'].set()
    log_yaz('gorev bulut fazi durduruldu: id=%s (%s)' % (gorev_id, neden),
            'gorev')
    return True


def gorev_bulut_aktif(gorev_id):
    """Gorevin bulut fazi devam edebilir mi? (ONLINE/OFFLINE kontrolu)"""
    if not gorev_id:
        return True
    rec = gorev_kayit(gorev_id)
    if not rec:
        return True
    if rec.get('mod_durdu') is not None and rec['mod_durdu'].is_set():
        return False
    return True


def gorev_dene(gorev_id, saglayici, model=None, deneme=1, max_deneme=1):
    """Gorev deneme kaydi."""
    log_yaz('gorev deneme: id=%s saglayici=%s model=%s deneme=%d/%d'
            % (gorev_id, saglayici, model, deneme, max_deneme), 'gorev')


def _terminal_mi(gorev_id):
    """Gorev zaten terminal duruma gecti mi?"""
    with _gorev_kilit:
        rec = _gorev['aktif'].get(gorev_id)
        return bool(rec and rec.get('terminal'))


def _terminal_ayarla(gorev_id, tur):
    """Terminal durumu bir kez kur. Donus: True (bu cagri sahibi)."""
    with _gorev_kilit:
        rec = _gorev['aktif'].get(gorev_id)
        if not rec or rec.get('terminal'):
            return False
        rec['terminal'] = True
        rec['terminal_tur'] = tur
    return True


def gorev_basarili(gorev_id, saglayici, model=None, sure=0.0):
    """Gorev basari kaydi (TEK terminal durum garantisi)."""
    if not _terminal_ayarla(gorev_id, 'basarili'):
        return False
    log_yaz('gorev basarili: id=%s saglayici=%s model=%s sure=%.1f sn'
            % (gorev_id, saglayici, model, sure), 'gorev')
    return True


def gorev_hata(gorev_id, saglayici=None, tur='', mesaj='', sure=0.0):
    """Gorev hata kaydi (anahtar/sohbet icerigi YOK)."""
    if not _terminal_ayarla(gorev_id, 'hata'):
        return False
    log_yaz('gorev hata: id=%s saglayici=%s tur=%s sure=%.1f sn | %s'
            % (gorev_id, saglayici, tur, sure, str(mesaj)[:120]), 'gorev')
    return True


def gorev_iptal(gorev_id):
    """Gorev iptal kaydi (TEK terminal durum garantisi)."""
    if not _terminal_ayarla(gorev_id, 'iptal'):
        return False
    log_yaz('gorev iptal: id=%s' % gorev_id, 'gorev')
    return True


def gorev_bitti(gorev_id, sonuc='ok', sure=0.0):
    """Gorev bitis kaydi (terminal durum zaten ayarlandiysa tekrar edilmez)."""
    with _gorev_kilit:
        rec = _gorev['aktif'].pop(gorev_id, None)
    log_yaz('gorev bitti: id=%s sonuc=%s sure=%.1f sn'
            % (gorev_id, sonuc, sure), 'gorev')
    return rec is not None


def gorev_sure(gorev_id):
    with _gorev_kilit:
        rec = _gorev['aktif'].get(gorev_id) or {}
    return time.time() - float(rec.get('bas') or time.time())


def gorev_kapat():
    """Uygulama kapanirken calisan gorevleri guvenle yonet.

    * Aktif gorevler iptal edilir (iptal kaydi yazilir).
    * Devam eden ag istekleri iptal edilir.
    * Sonuc router.log'a yazilir (dosya aninda kapatilir -> kaybolmaz).
    """
    with _gorev_kilit:
        aktif = list(_gorev['aktif'].keys())
    for gid in aktif:
        gorev_iptal(gid)
    n = istek_iptal()
    with _gorev_kilit:
        _gorev['aktif'].clear()
    log_yaz('uygulama kapaniyor: %d aktif gorev iptal edildi, '
            '%d ag istegi sonlandirildi' % (len(aktif), n), 'kapanis')
    return len(aktif)


def _ucus_temizle():
    """Ucus kayitlarini temizler (kaynak tüketimi)."""
    with _ucus_kilit:
        n = len(_ucus)
        _ucus.clear()
        return n


# ---------------------------------------------------------------------------
# Ana yonlendirme
# ---------------------------------------------------------------------------
def _memo_kontrol(anahtar):
    """Onbellekten sonuc (coklu anahtar destekli)."""
    rec = _memo.get(anahtar)
    if not rec:
        return None
    if (time.time() - float(rec.get('t') or 0.0)) >= _MEMO_SURE:
        _memo.pop(anahtar, None)
        return None
    return rec.get('sonuc')


def _memo_yaz(anahtar, sonuc):
    """Onbellege yaz (en fazla _MEMO_ADET kayit tutulur)."""
    if len(_memo) >= _MEMO_ADET:
        eski = sorted(_memo.items(), key=lambda kv: float(kv[1].get('t') or 0))
        for k, _v in eski[:len(_memo) - _MEMO_ADET + 1]:
            _memo.pop(k, None)
    _memo[anahtar] = {'sonuc': sonuc, 't': time.time()}


def _yerel_cevap(soru, gecmis=None, zaman=None, ders_modu=False):
    """Yerel Ollama'ya yonlendir (sarmalayicinin yerel_cevap'i)."""
    import jarvis_ai_sarmalayici as sarm
    return sarm.yerel_cevap(soru, sistem=None, gecmis=gecmis,
                            zaman=int(zaman or 300), ders_modu=ders_modu)


def _bildir(bildirim, mesaj, gorev_id=None):
    """Kullanici bildirimini gonderir; gorev kimligi varsa eklenir."""
    if bildirim is None:
        return
    try:
        bildirim(mesaj, gorev_id)
        return
    except TypeError:
        pass
    except Exception:
        return
    try:
        bildirim(mesaj)
    except Exception:
        pass


def _saglayici_dene(tanim, ad, model, anahtar, metin, sistem, gecmis, zaman,
                    max_tokens, sicaklik, bildirim=None, iptal=None,
                    gorev_id=None):
    """Tek saglayiciyi dener (model yedekleri + gecici hata retry).

    Donus: (cevap, kullanilan_model, hata_tur, hata_mesaj, http_kod,
            tekrar_sayisi)
    """
    adaylar = _model_adaylari(tanim, model)
    cevap = ''
    kullanilan = model
    tekrar = 0
    son_hata = None
    for mi, denenen in enumerate(adaylar):
        # Model yedekleri: YALNIZCA 404 (model) hatasinda sonraki modele gecilir.
        # Gecici/kalici diger hatalarda model yedekleri denenmez.
        deneme_no = 0
        model_degisti = False
        baslangic = time.time()
        while True:
            deneme_no += 1
            if iptal is not None:
                try:
                    if iptal.is_set():
                        gorev_iptal(gorev_id or '-')
                        return ('', kullanilan, 'iptal', 'Istek iptal edildi.',
                                None, tekrar)
                except Exception:
                    pass
            # FAZ 4E.4.1: gorev iptali (kullanici) ve MOD DEGISIMI kontrolu.
            # Her bulut denemesinden once yeniden bakilir; OFFLINE'a
            # gecildiginde MUTLAK yeni bulut istegi gonderilmez.
            rec = gorev_kayit(gorev_id) if gorev_id else None
            if rec is not None:
                ev = rec.get('iptal')
                if ev is not None and ev.is_set():
                    gorev_iptal(gorev_id)
                    return ('', kullanilan, 'iptal', 'Istek iptal edildi.',
                            None, tekrar)
                ev = rec.get('mod_durdu')
                if ev is not None and ev.is_set():
                    log_yaz('gorev bulut fazi birakildi: id=%s (mod degisti)'
                            % gorev_id, 'gorev')
                    return ('', kullanilan, 'mod_durdu',
                            'Baglanti modu degisti; bulut istegi durduruldu.',
                            None, tekrar)
            gorev_dene(gorev_id or '-', ad, denenen, deneme_no,
                       _retry_max_icin(deneme_no))
            log_yaz('saglayici denemesi: %s model=%s kaynak=%s'
                    % (ad, denenen, '-'), 'deneme')
            try:
                cevap = saglayici_istegi(tanim, denenen, anahtar, metin,
                                         sistem=sistem, gecmis=gecmis,
                                         zaman=zaman,
                                         max_tokens=max_tokens,
                                         sicaklik=sicaklik)
                son_hata = None
                break
            except RouterHatasi as e:
                son_hata = e
                if e.tur == 'model' and mi < len(adaylar) - 1:
                    log_yaz('model bulunamadi (404), sonraki model '
                            'denenecek: %s -> %s'
                            % (denenen, adaylar[mi + 1]), 'model')
                    model_degisti = True
                    break
                # Gecici hata -> kontrollu tekrar (429 kota icin ayri politika)
                if (e.tur in GECICI_TURLER or e.tur == 'kota') and \
                        deneme_no < _retry_max(e) and \
                        (time.time() - baslangic) < RETRY_TOPLAM_BUDGE_SN:
                    bekleme = bekleme_suresi(deneme_no, e.tur,
                                             _retry_after(e))
                    tekrar += 1
                    _durum['sayac']['tekrar'] += 1
                    log_yaz('gecici hata, tekrar denenecek: %s model=%s '
                            'tur=%s http=%s | %d/%d deneme, %.1f sn bekleniyor'
                            % (ad, denenen, e.tur, e.http_kod or '-',
                               deneme_no, _retry_max(e), bekleme), 'tekrar')
                    _bildir(bildirim,
                            '%s. Tekrar deniyorum.'
                            % hata_mesaji(ad, e.tur, e.http_kod), gorev_id)
                    if not uyku_ile(iptal, bekleme):
                        return ('', kullanilan, 'iptal',
                                'Istek iptal edildi.', None, tekrar)
                    continue
                break
            except Exception as e:
                son_hata = e
                break
        if cevap:
            return (cevap, denenen, None, '', None, tekrar)
        if not model_degisti:
            # Gecici/kalici hata: sonraki MODEL denemesi yapilmaz.
            break
    if son_hata is None:
        return ('', kullanilan, 'hata', 'Bos cevap alindi.', None, tekrar)
    if isinstance(son_hata, RouterHatasi):
        return ('', kullanilan, son_hata.tur, str(son_hata),
                son_hata.http_kod, tekrar)
    return ('', kullanilan, 'hata', repr(son_hata)[:140], None, tekrar)


def _retry_max(hata):
    """Hataya gore azami deneme sayisi."""
    tur = getattr(hata, 'tur', '') or ''
    if tur == 'kota':
        return KOTA_RETRY_MAX
    if tur in GECICI_TURLER:
        return RETRY_MAX_DENEME
    return 1                       # kalici hata: TEKRAR YOK


def _retry_max_icin(deneme_no):
    """Log icin azami deneme sayisi (hata turune gore)."""
    return RETRY_MAX_DENEME


def _retry_after(hata):
    """HTTP Retry-After / kota bilgisi (varsa)."""
    for ad in ('retry_after', 'retry_after_s'):
        v = getattr(hata, ad, None)
        if v:
            return v
    return None


def sorgula(soru, sistem=None, gecmis=None, zaman=None, max_tokens=None,
            sicaklik=None, ders_modu=False, yerel_fallback=None,
            zorla_yenile=False, bildirim=None, iptal=None):
    """Otomatik yonlendirme.

    FAZ 4E.2:
      * Gecici hatalarda (503/500/502/504, zaman asimi, baglanti) en fazla
        3 deneme, artan bekleme + kucuk rastgele fark, iptal edilebilir.
      * 429 (kota) icin ayri bekleme politikasi.
      * 401/403/404 gibi kalici hatalar TEKRAR DENENMEZ.
      * Devre kesici: gecici hata sonrasi gecici devre disi, bekleme bitince
        yarim acik (tek deneme), basarida kapanir.
      * Yinelenen istek onleme + iptal.
      * Kullaniciya dogru bilgi (bildirim geri cagrisi ile).

    Donus: {'cevap','saglayici','model','internet','mod','bildirim',...}
    """
    metin = str(soru or '').strip()
    if not metin:
        raise RouterHatasi("Soru metni bos.", 'saglayici')

    mod = mod_oku()
    anahtar_memo = istek_anahtari(metin, mod, ders_modu)
    memo = _memo_kontrol(anahtar_memo)
    if memo is not None:
        return dict(memo)

    # FAZ 4E.3: benzersiz gorev kimligi + yasam dongusu kayitlari
    gorev_id = gorev_id_uret()
    gorev_baslat(gorev_id, mod, 'ders' if ders_modu else 'sohbet')

    # --- FAZ 4E.2: yinelenen istek onleme -------------------------------
    ucus, sahip = _ucus_al(anahtar_memo)
    if not sahip:
        # Ayni istek zaten calisiyor -> sonucu bekle (yinelenmeyi onle)
        _durum['sayac']['yinelenen'] += 1
        log_yaz('ayni istek zaten calisiyor, sonuc bekleniyor (gorev=%s)'
                % gorev_id, 'cakisma')
        try:
            if ucus['olay'].wait(UCUS_BEKLEME_TAVAN):
                if ucus.get('sonuc') is not None:
                    gorev_bitti(gorev_id, 'yinelenen-varis')
                    return dict(ucus['sonuc'])
                if ucus.get('hata'):
                    gorev_bitti(gorev_id, 'yinelenen-hata')
                    raise RouterHatasi(ucus['hata'], 'iptal')
        except RouterHatasi:
            raise
        except Exception:
            pass
        # Bekleme bitti: kendi istegini yeni baslat
        ucus, sahip = _ucus_al(anahtar_memo + '#yeni')
        anahtar_memo = anahtar_memo + '#yeni'

    def _bitir(sonuc=None, hata=None):
        try:
            if sonuc is not None:
                ucus['sonuc'] = sonuc
            if hata is not None:
                ucus['hata'] = hata
            ucus['olay'].set()
        except Exception:
            pass

    try:
        return _sorgula_ana(metin, sistem, gecmis, zaman, max_tokens,
                             sicaklik, ders_modu, yerel_fallback,
                             zorla_yenile, bildirim, iptal, anahtar_memo,
                             _bitir, gorev_id)
    except Exception as e:
        _bitir(hata=str(e))
        gorev_hata(gorev_id, None, 'iptal' if 'iptal' in str(e) else 'hata',
                   str(e), gorev_sure(gorev_id))
        gorev_bitti(gorev_id, 'hata', gorev_sure(gorev_id))
        raise


def _sorgula_ana(metin, sistem, gecmis, zaman, max_tokens, sicaklik,
                 ders_modu, yerel_fallback, zorla_yenile, bildirim, iptal,
                 anahtar_memo, _bitir, gorev_id=None):
    """sorgula() govdesi (ayri fonksiyon: yinelenen istek yonetimi icin)."""
    ay = ayarlar()
    mod = mod_oku()
    bulut_acik = bool(ay.get('cloud_enabled', True))
    log_yaz('bulut sistemi: %s' % ('ACIK' if bulut_acik else 'KAPALI'), 'sistem')

    # --- FAZ 4E: BAGLANTI MODU KARARI --------------------------------------
    # ONLINE  : internet probu ATLANIR, bulut saglayicilari dogrudan denenir.
    #           (Internetin gercekten calistigi DOGRULANMAMAZ / iddia edilmez.)
    #           Gemini ONLINE modunda ILK denenecek model (FAZ 4E.4.2).
    # OFFLINE : tum bulut istekleri devre disi, prob yapilmaz, dogrudan yerel.
    # OTOMATIK: internet varsa bulut (Gemini oncelikli), yoksa yerel model.
    if mod == MOD_OFFLINE:
        bulut_acik = False
        log_yaz('baglanti modu OFFLINE: tum bulut istekleri devre disi; '
                'internet probu yapilmadi; dogrudan yerel model', 'mod')
    elif mod == MOD_ONLINE:
        log_yaz('baglanti modu ONLINE: internet probu ATLANDI; izinli bulut '
                'saglayicilari dogrudan denenecek (internetin calistigi '
                'dogrulanmaz). Gemini ONLINE modunda ILK denenecek model.',
                'mod')
    else:
        log_yaz('baglanti modu OTOMATIK: internet algilamasi yapilacak', 'mod')

    internet_var_mi = False
    if bulut_acik:
        if mod == MOD_ONLINE:
            internet_var_mi = True       # prob tamamen atlanir
            log_yaz('internet kontrolu: ATLANDI (ONLINE modu) -> dogrudan '
                    'bulut saglayicilari', 'internet')
        else:
            internet_var_mi = bool(internet_var(zorla_yenile))
            if not internet_var_mi:
                log_yaz('internet yok -> dogrudan yerel modele', 'gecis')
    else:
        log_yaz('bulut kapali (OFFLINE modu veya cloud_enabled=false) -> '
                'dogrudan yerel modele', 'gecis')

    bulut_basarisiz = []          # [(ad, tur, mesaj, http_kod)]
    bulut_yapilandirilmadi = []   # [(ad, neden)]

    if bulut_acik and internet_var_mi:
        # FAZ 4E.4.2: ONLINE/AOTO modunda GEMINI ONCE denenecek.
        # Siralama DENEME_SIRASI'na gore yapilir (saglayici tanimlari
        # bozulmaz; sadece deneme sirasi degisir).
        sirali = _deneme_sirasina_gore(saglayici_tanimlari())
        log_yaz('bulut deneme sirasi: %s'
                % ', '.join(t['name'] for t in sirali), 'sistem')
        for tanim in sirali:
            ad = tanim['name']
            if not tanim.get('enabled'):
                continue
            if not izinli_mi(ad):
                continue
            # --- FAZ 4E.2: devre kesici kontrolu --------------------------
            if not _saglik_uygun(ad):
                d = devre_durumu(ad)
                log_yaz('saglayici atlandi (devre kesici acik, %.0f sn '
                        'kaldi): %s | %s' % (d['kalan_sn'], ad,
                                             d['son_hata'][:90]), 'atla')
                _durum['sayac']['atlanan'] += 1
                bulut_yapilandirilmadi.append(
                    (ad, 'devre kesici (%.0f sn)' % d['kalan_sn']))
                continue
            model = _model_bul(tanim, ay)
            if not model_izinli_mi(ad, model):
                log_yaz('saglayici reddedildi (model ucretsiz degil): '
                        '%s model=%s' % (ad, model), 'red')
                _saglik_hata(ad, tur='model', hata='model ucretsiz degil')
                continue
            kaynak = []
            anahtar = anahtar_bul(tanim, kaynak)
            if not anahtar:
                log_yaz('saglayici atlandi (API anahtari yok): %s' % ad, 'atla')
                _durum['sayac']['atlanan'] += 1
                bulut_yapilandirilmadi.append((ad, 'yapilandirilmamis'))
                continue
            t0 = time.time()
            (cevap, kullanilan, hata_tur, hata_mesaj, http_kod,
             tekrar) = _saglayici_dene(
                tanim, ad, model, anahtar, metin, sistem, gecmis, zaman,
                max_tokens, sicaklik, bildirim=bildirim, iptal=iptal,
                gorev_id=gorev_id)
            if hata_tur == 'iptal':
                _durum['sayac']['iptal'] += 1
                log_yaz('istek iptal edildi: %s (gorev=%s)' % (ad, gorev_id),
                        'iptal')
                gorev_iptal(gorev_id or '-')
                raise RouterHatasi("Istek iptal edildi.", 'iptal')
            if hata_tur == 'mod_durdu':
                # Bulut fazi mod degisimi nedeniyle birakildi; bu bir
                # SAGLAYICI HATASI DEGILDIR -> yerel modele gecilir.
                log_yaz('gorev bulut fazi durduruldu, yerel modele geciyor: '
                        'id=%s saglayici=%s' % (gorev_id, ad), 'gorev')
                _bildir(bildirim,
                        '%s bulut isteği durduruldu (bağlantı modu '
                        'değişti). Yerel modele geçiyorum.'
                        % _saglayici_adi(ad), gorev_id)
                break
            if cevap:
                _saglik_basari(ad)
                _durum['sayac']['bulut'] += 1
                _durum['son_saglayici'] = ad
                _durum['son_model'] = kullanilan
                _durum['son_zaman'] = time.time()
                log_yaz('saglayici basarili: %s model=%s sure=%.1f sn'
                        % (ad, kullanilan, time.time() - t0), 'sonuc')
                gorev_basarili(gorev_id or '-', ad, kullanilan,
                               time.time() - t0)
                gorev_bitti(gorev_id or '-', 'basarili', gorev_sure(gorev_id))
                sonuc = {'cevap': cevap, 'saglayici': ad, 'model': kullanilan,
                         'internet': bool(_durum['internet']), 'mod': mod,
                         'gorev_id': gorev_id,
                         'bildirim': '', 'bulut_basarisiz': [],
                         'bulut_yapilandirilmadi': [], 'yerel_donus': False,
                         'tekrar': tekrar,
                         'kaynak': kaynak_etiketi(ad, kullanilan)}
                _memo_yaz(anahtar_memo, sonuc)
                _bitir(sonuc=sonuc)
                return sonuc
            # Basarisiz
            bekleme = _saglik_hata(ad, tur=hata_tur, hata=hata_mesaj,
                                   http_kod=http_kod)
            log_yaz('saglayici hata: %s model=%s tur=%s http=%s | %s'
                    % (ad, kullanilan, hata_tur, http_kod or '-',
                       hata_mesaj), 'hata')
            gorev_hata(gorev_id or '-', ad, hata_tur, hata_mesaj,
                       time.time() - t0)
            if hata_tur:
                bulut_basarisiz.append((ad, hata_tur, hata_mesaj, http_kod))
            continue

    # Yerel model (son cay)
    bildirim_mesaji = _yerel_bildirimi(bulut_basarisiz, bulut_yapilandirilmadi,
                                        mod)
    if bildirim_mesaji:
        log_yaz('kullanici bilgilendirmesi [gorev=%s]: %s'
                % (gorev_id, bildirim_mesaji), 'bildirim')
        _bildir(bildirim, bildirim_mesaji, gorev_id)
    log_yaz('yerel modele dusuluyor (ollama/qwen3:4b) [gorev=%s]' % gorev_id,
            'gecis')
    gorev_dene(gorev_id or '-', YEREL_SAGLAYICI, 'qwen3:4b', 1, 1)
    try:
        # FAZ 4E.4.1: yerel model eszamanlilik siniri (4 GB makinede
        # es zamanli 2 istek modeli bos yazdiriyordu).
        with _yerel_kilit:
            if yerel_fallback is not None:
                cevap = yerel_fallback(metin, gecmis=gecmis, zaman=zaman,
                                       ders_modu=ders_modu)
            else:
                cevap = _yerel_cevap(metin, gecmis=gecmis, zaman=zaman,
                                     ders_modu=ders_modu)
    except Exception as e:
        _durum['sayac']['hata'] += 1
        log_yaz('yerel model hatasi [gorev=%s]: %s' % (gorev_id, repr(e)[:140]),
                'hata')
        raise RouterHatasi(
            "Bulut saglayicilari ve yerel model cevap veremedi. "
            "Ollama calisiyor mu? (localhost:11434, model qwen3:4b). "
            "Son hata: %s" % (str(e)[:140]), 'hepsi')
    cevap = str(cevap or '').strip()
    if not cevap:
        _durum['sayac']['hata'] += 1
        log_yaz('yerel model bos cevap dondurdu', 'hata')
        raise RouterHatasi(
            "Yerel model bos cevap dondurdu. Ollama calisiyor mu? "
            "(localhost:11434, model qwen3:4b)", 'hepsi')
    _durum['sayac']['yerel'] += 1
    _durum['son_saglayici'] = YEREL_SAGLAYICI
    _durum['son_model'] = 'qwen3:4b'
    _durum['son_zaman'] = time.time()
    log_yaz('yerel model basarili (ollama/qwen3:4b) [gorev=%s]' % gorev_id,
            'sonuc')
    gorev_basarili(gorev_id or '-', YEREL_SAGLAYICI, 'qwen3:4b',
                   gorev_sure(gorev_id))
    gorev_bitti(gorev_id or '-', 'yerel', gorev_sure(gorev_id))
    sonuc = {'cevap': cevap, 'saglayici': YEREL_SAGLAYICI,
             'model': 'qwen3:4b', 'internet': bool(_durum['internet']),
             'mod': mod, 'bildirim': bildirim_mesaji, 'gorev_id': gorev_id,
             'bulut_basarisiz': bulut_basarisiz,
             'bulut_yapilandirilmadi': bulut_yapilandirilmadi,
             'yerel_donus': bool(bildirim_mesaji),
             'tekrar': 0,
             'kaynak': kaynak_etiketi(YEREL_SAGLAYICI, 'qwen3:4b')}
    _memo_yaz(anahtar_memo, sonuc)
    _bitir(sonuc=sonuc)
    return sonuc


def _yerel_bildirimi(basarisiz, yapilandirilmadi, mod):
    """Yerel modele dusulurken kullaniciya gosterilecek aciklama.

    OFFLINE modda kullanici yerel modeli kendisi sectigi icin uyari
    uretilmez (yalnizca bulut denemesi oldugunda bildirilir).
    """
    if not basarisiz and not yapilandirilmadi:
        return ''
    parcalar = []
    for ad, tur, mesaj, kod in basarisiz:
        parcalar.append(hata_mesaji(ad, tur, kod))
    yapilandirilmayan = []
    for ad, neden in yapilandirilmadi:
        if neden == 'yapilandirilmamis':
            yapilandirilmayan.append(_saglayici_adi(ad))
        else:
            yapilandirilmayan.append("%s (%s)" % (_saglayici_adi(ad), neden))
    if parcalar:
        ilk = parcalar[0]
        ek = (", ".join(parcalar[1:]) if len(parcalar) > 1 else '')
        mesaj = "%s. " % ilk
        if ek:
            mesaj += "%s. " % ek
    else:
        mesaj = ""
    if yapilandirilmayan:
        mesaj += "%s yapılandırılmamış. " % " ve ".join(yapilandirilmayan)
    mesaj += "Şimdilik yerel modele geçiyorum."
    return mesaj



# ---------------------------------------------------------------------------
# Durum / tani
# ---------------------------------------------------------------------------
def durum():
    """Teknik durum (API anahtari ve sohbet icerigi YOK)."""
    ay = ayarlar()
    _mod = mod_oku()
    return {
        'surum': SURUM,
        'aktif': True,
        'mod': _mod,
        'mod_etiket': MOD_ETIKET.get(_mod, _mod),
        'internet': _durum['internet'],
        'internet_known': _durum['internet'] is not None,
        'internet_not': _durum['internet_not'],
        'bulut_acik': bool(ay.get('cloud_enabled', True)),
        'izinli_saglayicilar': list(IZINLI_SAGLAYICILAR),
        'yasakli_saglayicilar': list(YASAKLI_SAGLAYICILAR),
        'aktif_saglayicilar': izinli_saglayicilar(),
        'saglik': {ad: saglik(ad) for ad in izinli_saglayicilar()},
        'devre_kesici': {ad: devre_durumu(ad) for ad in izinli_saglayicilar()},
        'devam_eden_istek': devam_eden_istekler(),
        'retry': {
            'max_deneme': RETRY_MAX_DENEME,
            'bekleme_sn': list(RETRY_BEKLEME_SN),
            'jitter': RETRY_JITTER,
            'kota_max_deneme': KOTA_RETRY_MAX,
            'kota_bekleme_sn': list(KOTA_BEKLEME_SN),
            'devre_bekleme_sn': list(DEVRE_BEKLEME_SN),
        },
        'son_saglayici': _durum['son_saglayici'],
        'son_model': _durum['son_model'],
        'deneme_sirasi': list(DENEME_SIRASI),
        'aktif_model': aktif_model_bilgisi(),
        'sayac': dict(_durum['sayac']),
        'ucretsiz_uyari': UCRETSIZ_UYARI,
        'tls_dogrulama': 'aktif (verify=False / CERT_NONE kullanilmaz)',
        'tls': tls_durum(),
        'izinli_alan_adlari': sorted(izinli_alan_adlari()),
    }


def reset():
    """Onbellekleri temizle (saglik + internet + memo + api adaylari)."""
    _durum['internet'] = None
    _durum['internet_t'] = 0.0
    _durum['internet_not'] = ''
    _durum['saglik'].clear()
    _memo.clear()
    _api_cache['t'] = 0.0
    _api_cache['liste'] = []
    with _ucus_kilit:
        for rec in _ucus.values():
            try:
                rec['olay'].set()
            except Exception:
                pass
        _ucus.clear()


def mod_reset():
    """Mod onbelleğini temizle (bir sonraki mod_oku() dosyadan okur)."""
    _mod_durum['deger'] = None
