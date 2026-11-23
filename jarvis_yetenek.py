# -*- coding: utf-8 -*-
"""JARVIS YETENEK KUTUPHANESI (ayri PYZ modulu).

Icindekiler:
  - AI zinciri        : Groq -> OpenRouter -> anahtarsiz genel (Gemini dusunce devreye girer)
  - Web arastirma     : anahtarsiz arama + sayfa metni + AI ozeti
  - Steam             : gercek VDF okuyucu, oyun baslatma, oneriler, ucretsiz oyunlar
  - Indirici          : winget kurulumu, resmi sayfa, URL'den dosya indirme
  - Yasal sinir       : korsan/hile/crack istekleri reddedilir (koda gomulu)
  - Gozlem            : aktif pencere + ekran karesi + ogrenme dosyasi

Bagimliliklar exe icinde mevcut: urllib, json, ssl, ctypes, PIL, requests (varsa).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time

# Respan izleme koprusu: RESPAN_API_KEY varsa LLM cagrilari izlenir; yoksa no-op.
# LLM istemcileri olusturulmadan once BIR KEZ baslatilir (bkz. jarvis_respan.py).
try:
    import jarvis_respan
    jarvis_respan.baslat()
except Exception:
    pass

# ----------------------------------------------------------------------------
# Genel yardimcilar
# ----------------------------------------------------------------------------

_TURKCE_KUCUK = {
    'İ': 'i', 'I': 'i', '\u0130': 'i', '\u0131': 'i',
    'Ş': 's', 'ş': 's', 'Ğ': 'g', 'ğ': 'g', 'Ü': 'u', 'ü': 'u',
    'Ö': 'o', 'ö': 'o', 'Ç': 'c', 'ç': 'c',
}


def _offline_modda_mi_guvenli():
    """OFFLINE modda mi? (mod bilgisi belirsizse FAIL-CLOSED: True).

    GOREV 2.7 / F2: Bu kontrol, mesaj arastirma veya AI saglayici
    zincirine ULAŞMADAN once uygulanir. Mod bilgisi jarvis_anlama.mod_oku()
    uzerinden alinir; sarmalayici bu fonksiyonu router'in gercek mod
    bilgisiyle (jarvis_ai_router) degistirir.
    """
    try:
        import jarvis_anlama as _an
        return str(_an.mod_oku() or '').strip().lower() == 'offline'
    except Exception:
        return True          # mod bilinmiyorsa guvenli tarafa gir


def _yerel_uc_nokta(ad, url) -> bool:
    a = str(ad or '').lower()
    u = str(url or '').lower()
    return ('ollama' in a or 'localhost' in u or '127.0.0.1' in u)


def _bulut_agi_izni_var(ad, url, soru) -> bool:
    """FAZ 2.2B: yerel olmayan her AI istegi merkezi bilete baglidir.

    Bilet yoksa/gecersizse ag istegi HIC hazirlanmaz (fail-closed).
    Yerel Ollama (localhost) bilet gerektirmez.
    """
    if _yerel_uc_nokta(ad, url):
        return True
    try:
        import jarvis_chat_v2_entegrasyon as _e
        b = getattr(_e._ISTEK_BAGLAM, 'bilet', None)
        if not isinstance(b, dict):
            return False
        return bool(_e.yetki_dogrula(
            b, mesaj=soru, mod=str(b.get('mod') or ''),
            kaynak=str(b.get('kaynak') or ''), tuket=False))
    except Exception:
        return False


def tr_kucuk(metin):
    """Turkce uyumlu kucuk harfe cevirir (komut eslesmesi icin)."""
    s = str(metin or '')
    for a, b in _TURKCE_KUCUK.items():
        s = s.replace(a, b)
    return s.lower().strip()


def _kok():
    """Uygulamanin kok klasoru (exe yanindaki config/memory buradan bulunur)."""
    try:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.executable))
    except Exception:
        pass
    return os.getcwd()


def ayar_yolu():
    return os.path.join(_kok(), 'config', 'api_keys.json')


def ayarlar():
    """config/api_keys.json icerigini sozluk olarak dondurur (yoksa bos)."""
    for yol in (ayar_yolu(), os.path.join(os.getcwd(), 'config', 'api_keys.json')):
        try:
            with open(yol, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            continue
    return {}


def depo_klasoru():
    """Saklanan dosyalarin klasoru (OneDrive varsa orasi)."""
    ev = os.path.expanduser('~')
    for ad in ('OneDrive', 'OneDrive - Personal'):
        kok = os.path.join(ev, ad)
        if os.path.isdir(kok):
            hedef = os.path.join(kok, 'JARVIS_Saklanan')
            os.makedirs(hedef, exist_ok=True)
            return hedef
    hedef = os.path.join(ev, 'Documents', 'JARVIS_Saklanan')
    os.makedirs(hedef, exist_ok=True)
    return hedef


def ogrenme_yolu():
    return os.path.join(_kok(), 'memory', 'jarvis_ogrenme.json')


def ogrenme_oku():
    try:
        with open(ogrenme_yolu(), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'hatalar': {}, 'basarili_yamalar': {}, 'arac_tercihi': {}}


def ogrenme_yaz(veri):
    try:
        kok = os.path.dirname(ogrenme_yolu())
        if kok:
            os.makedirs(kok, exist_ok=True)
        with open(ogrenme_yolu(), 'w', encoding='utf-8') as f:
            json.dump(veri, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


# ----------------------------------------------------------------------------
# 1) AI ZINCIRI - Gemini cokerse ucretsiz saglayici devreye girer
# ----------------------------------------------------------------------------

# 100% BEDAVA saglayicilar: ucretsiz katman (Gemini/Groq/OpenRouter) veya
# tamamen anahtarsiz/yerel (Ollama/Pollinations). Varsayilan olarak SADECE
# bunlar kullanilir; ucretli anahtarlar config'te "ucretsiz_only": false
# yapilmadikca devreye girmez.
UCRETSIZ_SAGLAYICILAR = ('gemini', 'groq', 'openrouter', 'ollama',
                       'zai_glm')

# ---------------------------------------------------------------------------
# GOREV 2.7 / F2: KESIN YASAKLI SAGLAYICILAR
# ---------------------------------------------------------------------------
# Pollinations ve diger harici/anahtarsiz bulut yedekleri HICBIR modda
# saglayici olarak kullanilamaz. OFFLINE kontrolunden ONCE uygulanir.
YASAKLI_SAGLAYICILAR = ('pollinations', 'perplexity', 'together', 'fireworks',
                    'xai', 'cohere', 'mistral')

SAGLAYICILAR = (
    # --- 100% bedava (ucretsiz katman, anahtar ucretsiz hesapla alinir) ---
    ('gemini', 'https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s',
     'gemini-3.8-flash', 'gemini_api_key'),
    ('groq', 'https://api.groq.com/openai/v1/chat/completions',
     'llama-3.3-70b-versatile', 'groq_api_key'),
    ('openrouter', 'https://openrouter.ai/api/v1/chat/completions',
     'meta-llama/llama-3.3-70b-instruct:free', 'openrouter_api_key'),
    # --- 100% bedava ve anahtarsiz ---
    ('ollama', 'http://localhost:11434/v1/chat/completions',
     'qwen3:4b', None),
    # --- GOREV 2.8: yeni saglayicilar (OpenAI-uyumlu gercek endpoint) ---
    ('zai_glm', 'https://api.z.ai/api/paas/v4/chat/completions',
     'glm-4-flash', 'z_ai_api_key'),
    ('minimax', 'https://api.minimax.io/v1/chat/completions',
     'MiniMax-M2', 'minimax_api_key'),
    # --- Ucretli (sadece "ucretsiz_only": false ise) ---
    ('deepseek', 'https://api.deepseek.com/chat/completions',
     'deepseek-chat', 'deepseek_api_key'),
    ('anthropic', 'https://api.anthropic.com/v1/messages',
     'claude-3-5-sonnet-latest', 'anthropic_api_key'),
    ('openai', 'https://api.openai.com/v1/chat/completions',
     'gpt-4o-mini', 'openai_api_key'),
)

# Anahtar bulucunun tarayacagi ortam degiskenleri.
_ANAHTAR_ENV = {
    'groq_api_key': ('GROQ_API_KEY',),
    'deepseek_api_key': ('DEEPSEEK_API_KEY',),
    'anthropic_api_key': ('ANTHROPIC_API_KEY', 'CLAUDE_API_KEY'),
    'openai_api_key': ('OPENAI_API_KEY',),
    'openrouter_api_key': ('OPENROUTER_API_KEY',),
    'gemini_api_key': ('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GOOGLE_GENAI_API_KEY'),
}

_OLLAMA_CACHE = {'t': 0.0, 'var': False}
_GEMINI_ERISILEBILIR = {'ok': True, 't': 0.0}
# Ust uste AI hatasinda kisa sureli hizli-basarisiz mod (sohbet kilitlenmesin)
_AI_HATA_SAY = [0]
_AI_BLOK = [0.0]

# Anthropic anahtar havuzu: config'e birden fazla anahtar yazilabilir
# ("anthropic_api_keys": [k1, k2, ...]). Ariza/hatada siradaki anahtara gecilir.
_ANTHROPIC_HAVUZ_I = {'i': 0}


def _anthropic_anahtarlar(ay=None):
    """Config'teki tum Anthropic anahtarlarini sirali dondurur."""
    try:
        ay = ay if ay is not None else ayarlar()
    except Exception:
        ay = {}
    anahtarlar = []
    try:
        liste = ay.get('anthropic_api_keys') or []
        if isinstance(liste, (list, tuple)):
            anahtarlar.extend(str(k).strip() for k in liste if str(k or '').strip())
    except Exception:
        pass
    tek = (ay.get('anthropic_api_key') or '').strip()
    if tek and tek not in anahtarlar:
        anahtarlar.insert(0, tek)
    return anahtarlar


def _anthropic_sonraki_anahtar(ay=None):
    """Havuzdan siradaki (round-robin) anahtari dondurur; yoksa ''."""
    anahtarlar = _anthropic_anahtarlar(ay)
    if not anahtarlar:
        return ''
    i = _ANTHROPIC_HAVUZ_I['i'] % len(anahtarlar)
    _ANTHROPIC_HAVUZ_I['i'] = i + 1
    return anahtarlar[i]

SISTEM_TURKCE = (
    'Sen JARVIS adli Turkce konusan kisisel asistansin. Kullanici Abdulkadir. '
    'Kisa, net ve samimi Turkce cevap ver. Ingilizce yazma. '
    'SORU SORMA, KENDIN YAP: kullanici "oyun yap", "kod yaz", "bana bir X yap" '
    'dediginde "hangi platformda?", "sen mi kod vereyim ben mi powershell yapayim?", '
    '"nasıl yapalim?" gibi secenek sunma. Kendi profesyonellik判断inle platformu '
    'sec (oyun -> web/tarayici, kod -> python, web -> html/js), kodu DOGRUDAN '
    'yaz ve AYAKTA KAL: kullaniciye secim birakma. Soru soracakmis gibi davranma, '
    'eylem al. '
    'Kullanici sana her seyi sorabilir; CEVAPSIZ SORU YOKTUR: bilmezsen en '
    'olasi tahminini veya onerini ver, asla "bilmiyorum" diyerek bossa donme. '
    'Karmasik konularda once kisa cevap, sonra gerekirse adim adim aciklama. '
    'Kullanici bir is yapmani isterse once alinip, yapilabilecek olani '
    'dogrudan, eksiksiz yap; yapamadigini gorurse 1-2 cumleyle nedenini '
    'soyle ve alternatif oner. '
    'Kod iceren her cevapta kodu her zaman uc backtick (```) ile acilip kapanan '
    'blok halinde yaz; blok hemen altinda KOPYALA icin ayrica is yapilmaz, '
    'uygulama kodu kendisi panoya kopyalar. '
    'Yasadisi (hack, korsan indirme, hile) isteklerini reddet ve yasal alternatif oner.'
)


def _json_istek(url, veri, basliklar, zaman=30):
    """Basit JSON POST (urllib; requests varsa onu kullanir)."""
    govde = json.dumps(veri).encode('utf-8')
    h = {'Content-Type': 'application/json'}
    h.update(basliklar or {})
    try:
        import requests
        # TLS sertifika dogrulamasi AKTIF kalir (verify=False YOK).
        r = requests.post(url, data=govde, headers=h, timeout=zaman)
        if r.status_code >= 400:
            raise RuntimeError('HTTP %s: %s' % (r.status_code, r.text[:220]))
        return r.json()
    except ImportError:
        pass
    except Exception as e:
        # SSL/session sorunlarinda urllib + dogrulamasiz baglama dus
        if 'SSL' not in repr(e) and 'session' not in repr(e).lower():
            raise
    import ssl as _ssl
    import urllib.request
    # Varsayilan DOGRULAYAN SSL baglami (check_hostname/verify_mode
    # elle kapatilmaz; CERT_NONE kullanilmaz).
    ctx = _ssl.create_default_context()
    istek = urllib.request.Request(url, data=govde, headers=h, method='POST')
    with urllib.request.urlopen(istek, timeout=zaman, context=ctx) as c:
        return json.loads(c.read().decode('utf-8', 'ignore'))


def _ollama_var(zaman=1.2):
    """Yerel Ollama servisi calisiyor mu? (sonuc 60 sn onbelleklenir)"""
    simdi = time.time()
    if simdi - _OLLAMA_CACHE['t'] < 60:
        return _OLLAMA_CACHE['var']
    var = False
    try:
        import urllib.request
        with urllib.request.urlopen('http://localhost:11434/api/tags', timeout=zaman) as c:
            var = (getattr(c, 'status', 200) == 200)
    except Exception:
        var = False
    _OLLAMA_CACHE['t'] = simdi
    _OLLAMA_CACHE['var'] = var
    return var


# -------------------------------------------------------
# 1.5 API ANAHTARI SIZDIRMA KORUMASI
# -------------------------------------------------------
# ai_saglayicilar() ciktisindaki 4. eleman cozulmus API anahtaridir.
# Bu deger ekrana / loga / GUI'ye yazdirildiginda sizmasin diye kayitlar
# ozel bir tuple sinifi ile dondurulur: indexleme ve unpacking GERCEK
# degeri vermeye devam eder (ic cagiranlar: _saglayici_istek),
# ancak repr/str/f-string/list/dict ciktisinda anahtar MASKELENIR.

_ANAHAR_MASKELI = '<anahtar gizli>'


class SaglayiciKaydi(tuple):
    """(ad, url, model, anahtar) kaydi - anahtar yazdirilirken maskelenir."""

    __slots__ = ()

    def __repr__(self):
        ad, url, model, anahtar = tuple.__iter__(self)
        return "(%r, %r, %r, %r)" % (
            ad, url, model, _ANAHAR_MASKELI if anahtar else anahtar)

    def __str__(self):
        return repr(self)


# ---------------------------------------------------------------------------
# GOREV 2.8: Guvenli (DPAPI) anahtar deposu + beyin sirasi
# ---------------------------------------------------------------------------

def _guvenli_depo_anahtar_var(ad):
    """Saglayicinin anahtari guvenli depoda (DPAPI) kayitli mi?

    Deger COZULMEZ; yalnizca varlik kontrolu yapilir.
    """
    try:
        import jarvis_saglayici_guvenli as _g
        return bool(_g.var_mi(ad))
    except Exception:
        return False


def _guvenli_depo_anahtari(ad):
    """Saglayicinin anahtarini guvenli depodan cozer (yalnizca istek aninda)."""
    try:
        import jarvis_saglayici_guvenli as _g
        return _g.oku(ad)
    except Exception:
        return None


def _beyin_kaydi():
    """Beyin kayit defterini okur (yoksa bos sozluk)."""
    try:
        import jarvis_beyin_kayit as _b
        return _b.yukle()
    except Exception:
        return {}


def _beyin_saglayici_sirasi():
    """Kullanicinin secerligi beyin sirasi (bos ise bos liste)."""
    try:
        veri = _beyin_kaydi()
    except Exception:
        return []
    bl = veri.get('beyinler') or []
    if not bl:
        return []
    sira = []
    for b in bl:
        if not b.get('etkin', True):
            continue
        ad = str(b.get('saglayici') or '').strip().lower()
        if ad and ad not in sira:
            sira.append(ad)
    return sira


def _beyin_onayli(ad):
    """Kullanici bu saglayiciya ACIK ONAY verdi mi?"""
    try:
        veri = _beyin_kaydi()
    except Exception:
        return False
    for b in (veri.get('beyinler') or []):
        if str(b.get('saglayici') or '').lower() == str(ad or '').lower():
            return bool(b.get('kullanici_onayi'))
    return False


def _anahtar_var(anahtar_adi, ay=None):
    """Anahtarin VAR OLUP OLMADIGINI dondurur; DEGERI ASLA dondurmez.

    Anthropic coklu anahtar havuzunda havuz ilerletilmez (sadece varlik
    kontrolu yapilir); gercek anahtar istek aninda ayrica cozulur.
    """
    if not anahtar_adi:
        return True  # anahtarsiz saglayici
    if ay is None:
        ay = ayarlar()
    if anahtar_adi == 'anthropic_api_key':
        if _anthropic_anahtarlar(ay):
            return True
    if (ay.get(anahtar_adi) or '').strip():
        return True
    for e in _ANAHTAR_ENV.get(anahtar_adi, ()):
        if (os.environ.get(e) or '').strip():
            return True
    return False


def _saglayici_anahtari(ad, ay=None):
    """Gercek API anahtarini SADECE istek aninda cozup dondurur.

    Bu deger hicbir liste/sozluk/tuple yapisinda tasinmaz; dogrudan
    HTTP istegine verilir. Anthropic havuzunda round-robin burada ilerler.
    """
    if ay is None:
        ay = ayarlar()
    # GOREV 2.8: Oncelik guvenli DPAPI deposu (kullanicinin kurulumda
    # girdigi anahtar). Ancak deger HICBIR yerde tutulmaz.
    a = _guvenli_depo_anahtari(ad)
    if a:
        return a
    for sad, _surl, _smodel, sanhtar_adi in SAGLAYICILAR:
        if sad != ad:
            continue
        if not sanhtar_adi:
            return None
        if ad == 'anthropic':
            a = _anthropic_sonraki_anahtar(ay)
            if a:
                return a
        a = (ay.get(sanhtar_adi) or '').strip()
        if a:
            return a
        for e in _ANAHTAR_ENV.get(sanhtar_adi, ()):
            a = (os.environ.get(e) or '').strip()
            if a:
                return a
        return None
    return None


def _ai_routing_ayarlari():
    """config/ai_routing.json -> sozluk (yoksa bos).

    GOREV 2.7 / F5: Model tercihleri tek kaynaktan (ai_routing.json) okunsun.
    config/api_keys.json DEGISTIRILMEZ; sadece okunur.
    """
    try:
        kok = os.path.dirname(os.path.abspath(__file__))
        for aday in (os.path.join(kok, 'config', 'ai_routing.json'),
                     os.path.join(os.getcwd(), 'config', 'ai_routing.json')):
            if os.path.isfile(aday):
                with open(aday, 'r', encoding='utf-8') as f:
                    veri = json.load(f)
                if isinstance(veri, dict):
                    return veri
    except Exception:
        pass
    return {}


def ai_saglayicilar():
    """Kullanilabilir saglayici listesi (anahtar yoksa sadece anahtarsizlar)."""
    ay = ayarlar()
    kullanim = None
    try:
        kullanim = ay.get('ai_chain')
    except Exception:
        kullanim = None
    # GOREV 2.7 / F2: yasakli saglayicilar hicbir zaman listeye giremez
    ay_r = _ai_routing_ayarlari()
    sonuc = []
    for ad, url, model, anahtar_adi in SAGLAYICILAR:
        if ad in YASAKLI_SAGLAYICILAR:
            continue
        if anahtar_adi and not _anahtar_var(anahtar_adi, ay):
            # Anahtar yok -> saglayici kullanilamiyor (deger cozulmez)
            # GOREV 2.8: guvenli depoda (DPAPI) anahtari varsa kullanilabilir.
            if not _guvenli_depo_anahtar_var(ad):
                continue
        if ad == 'ollama' and not _ollama_var():
            continue
        # GOREV 2.7 / F5: model tek kaynaktan: config/ai_routing.json
        # (config/api_keys.json uzerine yazilir; yoksa SAGLAYICILAR varsayilani)
        model_kullan = (ay.get('ai_model_' + ad)
                        or ay_r.get('ai_model_' + ad)
                        or model)
        # 4. eleman GERCEK anahtari DEGIL; yalnizca varlik bilgisi:
        #   None -> anahtarsiz saglayici
        #   '<anahtar gizli>' -> anahtarli saglayici (deger gizli)
        maske = _ANAHAR_MASKELI if anahtar_adi else None
        sonuc.append(SaglayiciKaydi((ad, url, model_kullan, maske)))
    # 100% bedava mod (varsayilan): ucretli saglayicilari ele.
    # GOREV 2.7: ucretsiz_only iki kaynaktan okunur
    if ay.get('ucretsiz_only', ay_r.get('ucretsiz_only', True)) is not False:
        # GOREV 2.8: Kullanici acik onay VERDIGI saglayici (beyin kaydi)
        # ucretsiz_only kapali olsa bile kullanilabilir.
        sonuc = [s for s in sonuc
                 if s[0] in UCRETSIZ_SAGLAYICILAR or _beyin_onayli(s[0])]
    if isinstance(kullanim, list) and kullanim:
        sirali = []
        for ad in kullanim:
            for s in sonuc:
                if s[0] == ad:
                    sirali.append(s)
        for s in sonuc:
            if s not in sirali:
                sirali.append(s)
        sonuc = sirali
    # GOREV 2.8: Beyin kaydi varsa KULLANICI ONCELIGI gecerlidir.
    beyin_sirasi = _beyin_saglayici_sirasi()
    if beyin_sirasi:
        sirali = []
        for ad in beyin_sirasi:
            for s in sonuc:
                if s[0] == ad and s not in sirali:
                    sirali.append(s)
        for s in sonuc:
            if s not in sirali:
                sirali.append(s)
        sonuc = sirali
    return sonuc


def _anthropic_istek(url, model, anahtar, soru, sistem, zaman,
                     max_tokens, sicaklik):
    """Tek Anthropic anahtari ile istek atar; hata olursa exception firlatir."""
    basliklar = {'x-api-key': anahtar or '', 'anthropic-version': '2023-06-01'}
    veri = {
        'model': model,
        'max_tokens': int(max_tokens),
        'temperature': float(sicaklik),
        'system': sistem,
        'messages': [{'role': 'user', 'content': str(soru)}],
    }
    cevap = _json_istek(url, veri, basliklar, zaman)
    try:
        return str(cevap['content'][0]['text']).strip()
    except Exception:
        return ''


def _saglayici_istek(ad, url, model, anahtar, soru, sistem=None, zaman=35,
                     max_tokens=1200, sicaklik=0.4):
    """Tek bir saglayiciya istek atar; saglayiciya ozgu govde/cevap formatini bilir."""
    sistem = sistem or SISTEM_TURKCE
    # FAZ 2.2B: merkezi bilet yoksa bulut uc noktasina HIC gidilmez.
    if not _bulut_agi_izni_var(ad, url, soru):
        raise RuntimeError(
            "Merkezi bulut izni yok; istek gonderilmedi.")
    if ad == 'anthropic':
        # Anahtar havuzu: ilk anahtar ile basla; hata olursa siradakini dene.
        havuz = _anthropic_anahtarlar()
        adaylar = [anahtar] if anahtar else []
        for k in havuz:
            if k not in adaylar:
                adaylar.append(k)
        son_hata = None
        for k in (adaylar or ['']):
            try:
                return _anthropic_istek(url, model, k, soru, sistem,
                                        zaman, max_tokens, sicaklik)
            except Exception as e:
                son_hata = e
                continue
        if son_hata is not None:
            raise son_hata
        return ''
    if ad == 'gemini':
        veri = {
            'contents': [{'parts': [{'text': str(soru)}]}],
            'systemInstruction': {'parts': [{'text': sistem}]},
            'generationConfig': {'temperature': float(sicaklik),
                                 'maxOutputTokens': int(max_tokens)},
        }
        aday_modeller = [model, 'gemini-1.5-flash', 'gemini-2.0-flash',
                         'gemini-1.5-flash-latest']
        gorulen = set()
        son_hata = None
        for m in aday_modeller:
            if not m or m in gorulen:
                continue
            gorulen.add(m)
            url2 = url % (m, anahtar or '')
            try:
                cevap = _json_istek(url2, veri, {}, min(zaman, 25))
                try:
                    return str(cevap['candidates'][0]['content']['parts'][0]['text']).strip()
                except Exception:
                    continue
            except Exception as e:
                son_hata = e
                if '404' in repr(e):
                    continue
                if 'SSL' in repr(e) or 'session' in repr(e).lower():
                    # Python SSL oturumu bozuksa curl.exe YEDEGI SADECE config'te
                    # "gemini_curl": true ise denenir (aksi halde bazi AV/EDR
                    # curl.exe'yi engeller ve uygulama kilitlenir).
                    try:
                        _curl_izin = bool(ayarlar().get('gemini_curl', False))
                    except Exception:
                        _curl_izin = False
                    if not _curl_izin:
                        son_hata = e
                        break
                    try:
                        cevap = _gemini_curl(url2, veri, min(zaman, 60))
                        try:
                            return str(cevap['candidates'][0]['content']['parts'][0]['text']).strip()
                        except Exception:
                            continue
                    except Exception as e2:
                        son_hata = e2
                        time.sleep(0.5)
                        continue
                break
        if son_hata is not None:
            raise son_hata
        return ''
    # OpenAI uyumlu (groq, deepseek, openai, openrouter, ollama, pollinations)
    basliklar = {}
    if anahtar:
        basliklar['Authorization'] = 'Bearer ' + anahtar
    if ad == 'openrouter':
        basliklar['HTTP-Referer'] = 'http://localhost/jarvis'
        basliklar['X-Title'] = 'JARVIS'
    # GOREV 2.7 / F2: Pollinations KESINLIKLE KULLANILMAZ.
    # Kontrol, istek HAZIRLANMADAN once yapilir (fail-closed).
    if ad in YASAKLI_SAGLAYICILAR:
        raise RuntimeError(
            "Yasakli saglayici kullanilamaz: %s" % ad)
    # Ollama: yerel API ve Qwen3 dusunme kontrolu
    if ad == 'ollama':
        yerel_url = url.rsplit('/v1/chat/completions', 1)[0] + '/api/chat'
        mesajlar = []
        if sistem:
            mesajlar.append({'role': 'system', 'content': str(sistem)})
        mesajlar.append({'role': 'user', 'content': str(soru)})
        yerel_veri = {
            'model': model,
            'messages': mesajlar,
            'think': False,
            'stream': False,
            'options': {
                'temperature': float(sicaklik),
                'num_predict': int(max_tokens),
            },
        }
        yerel_cevap = _json_istek(yerel_url, yerel_veri, {}, zaman)
        try:
            metin = str(yerel_cevap.get('message', {}).get('content') or '').strip()
        except (AttributeError, TypeError):
            metin = ''
        return metin
    veri = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': sistem},
            {'role': 'user', 'content': str(soru)},
        ],
        'temperature': float(sicaklik),
        'max_tokens': int(max_tokens),
    }
    try:
        cevap = _json_istek(url, veri, basliklar, zaman)
        try:
            metin = str(cevap['choices'][0]['message']['content']).strip()
        except Exception:
            metin = cevap.strip() if isinstance(cevap, str) else ''
        if metin:
            return metin
    except Exception:
        # GOREV 2.7 / F2: Pollinations GET yedegi de kaldirildi.
        raise
    return ''


def _gemini_curl(url, veri, zaman=60):
    """Windows curl.exe ile Gemini (Python SSL 'INVALID_SESSION_ID' icin)."""
    import tempfile
    govde = json.dumps(veri)
    yol = os.path.join(tempfile.gettempdir(), 'jarvis_gemini_govde.json')
    with open(yol, 'w', encoding='utf-8') as f:
        f.write(govde)
    try:
        r = subprocess.run(
            ['curl.exe', '-s', '-S', '-X', 'POST', url,
             '-H', 'Content-Type: application/json',
             '--data-binary', '@' + yol, '--max-time', str(int(zaman))],
            capture_output=True, timeout=zaman + 15,
            encoding='utf-8', errors='replace')
        cikti = (r.stdout or '').strip()
        if not cikti:
            raise RuntimeError('curl bos cevap (kod %s): %s' % (
                r.returncode, (r.stderr or '')[:120]))
        return json.loads(cikti)
    finally:
        try:
            os.remove(yol)
        except Exception:
            pass


_POLL_KILIT = threading.Lock()
_POLL_SON = [0.0]
_POLL_ARALIK = 10.0
_POLL_BLOK = [0.0]
_POLL_CACHE = {}


def _pollinations_istek(sistem, soru, zaman=60, max_tokens=1200, sicaklik=0.4):
    # GOREV 2.7 / F2: Pollinations kalici olarak devre disi.
    raise RuntimeError("Pollinations saglayicisi devre disi birakildi.")
    """Ucretsiz Pollinations: 45 sn'de 1 cevap limitine uyan kuyruk.

    Once GET (ucretsiz katman), olmazsa POST /openai denenir. Ayni soru
    tekrar sorulursa onbellekten doner (limit yakmaz). Limit bloğu varsa
    hizli basarisiz olur (sohbet kilitlenmesin).
    """
    anahtar = str(sistem)[:160] + '|' + str(soru)
    if anahtar in _POLL_CACHE:
        return _POLL_CACHE[anahtar]
    if time.time() < _POLL_BLOK[0]:
        return ''
    with _POLL_KILIT:
        if _POLL_SON[0]:
            gecen = time.time() - _POLL_SON[0]
            if gecen < _POLL_ARALIK:
                time.sleep(_POLL_ARALIK - gecen)
        metin = _pollinations_get_yeni(sistem, soru, zaman)
        if not metin:
            metin = _pollinations_post_yeni(sistem, soru, zaman,
                                            max_tokens, sicaklik)
        _POLL_SON[0] = time.time()
        if not metin:
            _POLL_BLOK[0] = time.time() + 30.0
    if metin:
        if len(_POLL_CACHE) > 64:
            _POLL_CACHE.clear()
        _POLL_CACHE[anahtar] = metin
    return metin or ''


def _pollinations_get_yeni(sistem, soru, zaman=60):
    import urllib.parse
    import urllib.request
    metin = (str(sistem or '') + '\n\n' + str(soru))[:1500]
    adres = ('https://text.pollinations.ai/' +
             urllib.parse.quote(metin, safe='') +
             '?model=openai&referrer=jarvis')
    for deneme in range(2):
        try:
            istek = urllib.request.Request(adres, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Referer': 'http://localhost/jarvis',
                'Accept': 'text/plain'})
            with urllib.request.urlopen(istek, timeout=zaman) as c:
                txt = c.read().decode('utf-8', 'replace').strip()
            if txt and '<!DOCTYPE' not in txt and 'Free limit' not in txt:
                return txt
            m = re.search(r'wait\s+(\d+)\s*seconds', txt)
            bekle = min(60, (int(m.group(1)) if m else 5) + 2)
            time.sleep(bekle)
        except urllib.error.HTTPError as e:
            govde = ''
            try:
                govde = e.read().decode('utf-8', 'replace')
            except Exception:
                pass
            if e.code in (402, 429):
                m = re.search(r'wait\s+(\d+)\s*seconds', govde)
                bekle = min(60, (int(m.group(1)) if m else 5) + 2)
                time.sleep(bekle)
                continue
            return ''
        except Exception:
            time.sleep(2)
            continue
    return ''


def _pollinations_post_yeni(sistem, soru, zaman=60, max_tokens=1200,
                            sicaklik=0.4):
    try:
        import requests
        for deneme in range(2):
            r = requests.post('https://text.pollinations.ai/openai', json={
                'model': 'openai',
                'messages': [
                    {'role': 'system', 'content': sistem or SISTEM_TURKCE},
                    {'role': 'user', 'content': str(soru)},
                ],
                'max_tokens': int(max_tokens),
                'temperature': float(sicaklik),
            }, timeout=zaman)
            if r.status_code == 200:
                try:
                    txt = r.json()['choices'][0]['message']['content']
                    if txt and txt.strip():
                        return txt.strip()
                except Exception:
                    pass
            if r.status_code in (402, 429):
                m = re.search(r'wait\s+(\d+)\s*seconds', r.text)
                time.sleep(min(60, (int(m.group(1)) if m else 5) + 2))
                continue
            break
    except Exception:
        pass
    return ''


def _pollinations_get(sistem, soru, zaman=35):
    # GOREV 2.7 / F2: Pollinations kalici olarak devre disi.
    raise RuntimeError("Pollinations saglayicisi devre disi birakildi.")
    """Anahtarsiz Pollinations GET yedegi (duz metin doner)."""
    import urllib.parse
    import urllib.request
    metin = (str(sistem) + '\n\n' + str(soru))[:6000]
    adres = 'https://text.pollinations.ai/' + urllib.parse.quote(metin, safe='')
    for deneme in range(2):
        try:
            istek = urllib.request.Request(
                adres, headers={'User-Agent': 'JARVIS/1.0',
                                'Referer': 'http://localhost/jarvis'})
            with urllib.request.urlopen(istek, timeout=zaman) as c:
                return c.read().decode('utf-8', 'ignore').strip()
        except Exception:
            if deneme == 0:
                time.sleep(1.5)
    return ''


def ai_sor(soru, sistem=None, zaman=35):
    # GOREV 2.7 / F2: OFFLINE modda bulut saglayici zincirine HIC
    # GIRILMEZ. Kontrol, saglayici listesi taranmadan once yapilir;
    # boylece hicbir harici istek HAZIRLANMAZ.
    if _offline_modda_mi_guvenli():
        return ''
    """Ucretsiz zincirden cevap alir. Hicbiri calismazsa RuntimeError."""
    son_hata = []
    for ad, url, model, _maske in ai_saglayicilar():
        try:
            metin = _saglayici_istek(ad, url, model,
                                      _saglayici_anahtari(ad), soru, sistem, zaman)
            if metin:
                return metin
        except Exception as e:
            son_hata.append('%s: %s' % (ad, str(e)[:90]))
            continue
    if son_hata:
        raise RuntimeError(' | '.join(son_hata))
    raise RuntimeError('Kullanilabilir ucretsiz AI yok (anahtar gerekli: console.groq.com)')


def ai_hazir_mi():
    """AI zinciri su an denemeye deger mi? (limit blogu yoksa True)."""
    return time.time() >= _AI_BLOK[0]


def ai_sor_ex(soru, sistem=None, zaman=45, atla=(), max_tokens=1200, sicaklik=0.4):
    # GOREV 2.7 / F2: OFFLINE modda bulut zincirine girilmez.
    if _offline_modda_mi_guvenli():
        return '', ''
    """Cevap + hangi saglayicidan geldigi. (metin, saglayici) doner."""
    atla = set(atla or ())
    # Ust uste basarisizlikta 2 dk boyunca hizli basarisiz ol (sohbet kilitlenmesin)
    if time.time() < _AI_BLOK[0]:
        return '', 'yerel: AI limitli (2 dk bekleme)'
    son_hata = []
    for ad, url, model, _maske in ai_saglayicilar():
        if ad in atla:
            continue
        try:
            metin = _saglayici_istek(ad, url, model,
                                     _saglayici_anahtari(ad), soru, sistem,
                                     zaman, max_tokens, sicaklik)
            if metin:
                _AI_HATA_SAY[0] = 0
                return metin, ad
        except Exception as e:
            if ad == 'gemini':
                _GEMINI_ERISILEBILIR['ok'] = False
                _GEMINI_ERISILEBILIR['t'] = time.time()
            son_hata.append('%s: %s' % (ad, str(e)[:90]))
            continue
    _AI_HATA_SAY[0] += 1
    if _AI_HATA_SAY[0] >= 2:
        _AI_BLOK[0] = time.time() + 30.0
    return '', (' | '.join(son_hata) if son_hata else '')


def ai_sor_saglayici(ad, soru, sistem=None, zaman=45, max_tokens=1200, sicaklik=0.4):
    """Belirli bir saglayicidan cevap ister (iki AI'yi ayirmak icin)."""
    for s in ai_saglayicilar():
        if s[0] == ad:
            try:
                return _saglayici_istek(s[0], s[1], s[2],
                                        _saglayici_anahtari(s[0]), soru, sistem,
                                        zaman, max_tokens, sicaklik)
            except Exception:
                return ''
    return ''


def _env_dosyasi_oku(yol):
    """Basit .env okuyucu: ANAHTAR=deger satirlari."""
    sonuc = {}
    try:
        with open(yol, 'r', encoding='utf-8', errors='ignore') as f:
            for satir in f:
                satir = satir.strip()
                if not satir or satir.startswith('#') or '=' not in satir:
                    continue
                k, v = satir.split('=', 1)
                sonuc[k.strip().lstrip('export ').strip()] = v.strip().strip('"\'')
    except Exception:
        pass
    return sonuc


def anahtar_bul(log=None):
    """Kullanicinin KENDI API anahtarlarini ortamdan/.env'den bulur ve
    config/api_keys.json'a yazar. Anahtar degerleri asla loglanmaz.

    Donus: bulunan saglayici adlari listesi (ornek ['deepseek', 'groq']).
    """
    def _yaz(m):
        if log:
            try:
                log(m)
            except Exception:
                pass

    ay = ayarlar()
    bulunan = []
    # 1) ortam degiskenleri
    for cfg, envs in _ANAHTAR_ENV.items():
        if (ay.get(cfg) or '').strip():
            continue
        for e in envs:
            v = (os.environ.get(e) or '').strip()
            if v:
                ay[cfg] = v
                bulunan.append(cfg.replace('_api_key', ''))
                break
    # 2) .env dosyalari
    adaylar = [
        os.path.join(os.getcwd(), '.env'),
        os.path.join(_kok(), '.env'),
        os.path.join(os.path.expanduser('~'), '.env'),
        os.path.join(os.path.expanduser('~'), '.config', 'jarvis', '.env'),
    ]
    for yol in adaylar:
        if not os.path.isfile(yol):
            continue
        for k, v in _env_dosyasi_oku(yol).items():
            for cfg, envs in _ANAHTAR_ENV.items():
                if (ay.get(cfg) or '').strip():
                    continue
                if k in envs or k == cfg:
                    if v:
                        ay[cfg] = v
                        bulunan.append(cfg.replace('_api_key', ''))
    # 3) yaygin JSON config dosyalari (kullanicinin kendi araclari)
    json_adaylar = [
        os.path.join(os.path.expanduser('~'), '.config', 'openrouter', 'config.json'),
        os.path.join(os.path.expanduser('~'), '.config', 'groq', 'config.json'),
        os.path.join(os.path.expanduser('~'), '.config', 'deepseek', 'config.json'),
        os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'Code', 'User', 'settings.json'),
    ]
    for yol in json_adaylar:
        try:
            with open(yol, 'r', encoding='utf-8', errors='ignore') as f:
                veri = json.load(f)
        except Exception:
            continue
        for cfg in _ANAHTAR_ENV:
            if (ay.get(cfg) or '').strip():
                continue
            for k, v in (veri or {}).items():
                if cfg in k.lower() and isinstance(v, str) and v.strip():
                    ay[cfg] = v.strip()
                    bulunan.append(cfg.replace('_api_key', ''))
    if bulunan:
        try:
            os.makedirs(os.path.dirname(ayar_yolu()), exist_ok=True)
            with open(ayar_yolu(), 'w', encoding='utf-8') as f:
                json.dump(ay, f, ensure_ascii=False, indent=1)
            _yaz('SYS: API anahtari bulundu ve kaydedildi: ' + ', '.join(sorted(set(bulunan))))
        except Exception as e:
            _yaz('SYS: API anahtari bulundu ama yazilamadi: ' + str(e)[:80])
    else:
        mevcut = [cfg.replace('_api_key', '') for cfg in _ANAHTAR_ENV
                  if (ay.get(cfg) or '').strip()]
        if mevcut:
            _yaz('SYS: Mevcut API anahtarlari kullaniliyor: ' +
                 ', '.join(sorted(mevcut)))
        else:
            _yaz('SYS: Ortamda/.env icinde API anahtari bulunamadi; '
                 'anahtarsiz saglayicilar kullanilacak.')
    return sorted(set(bulunan))


def ai_anahtar_durumu():
    """Insan okuyabilir durum metni ('hangi AI var')."""
    var = [s[0] for s in ai_saglayicilar()]
    eksik = []
    ay = ayarlar()
    for ad, _u, _m, anahtar_adi in SAGLAYICILAR:
        if ad not in UCRETSIZ_SAGLAYICILAR:
            continue
        if anahtar_adi and not (ay.get(anahtar_adi) or '').strip():
            eksik.append(ad)
    metin = 'AI zinciri: ' + (', '.join(var) if var else 'yok')
    if ay.get('ucretsiz_only', True) is not False:
        metin += '\n100% BEDAVA MOD: ACIK (ucretli saglayicilar kapali)'
        metin += '\nKapatmak icin config/api_keys.json icine "ucretsiz_only": false ekle.'
    else:
        metin += '\n100% BEDAVA MOD: KAPALI (ucretli anahtarlar da denenir)'
    metin += ('\nTamamen anahtarsiz: ollama (yerel) - pollinations kalikidir')
    if eksik:
        metin += '\nUcretsiz anahtar bekleyenler: ' + ', '.join(eksik)
        metin += '\nGemini ucretsiz anahtar: https://aistudio.google.com/apikey'
        metin += '\nGroq ucretsiz anahtar: https://console.groq.com/keys'
        metin += '\nOpenRouter ucretsiz anahtar: https://openrouter.ai/keys'
        metin += '\nAnahtarlari config/api_keys.json icine ekleyebilirsin; '
        metin += 'JARVIS ortam degiskenlerini/.env dosyasini da otomatik tarar.'
    if 'ollama' in var:
        metin += '\nYerel Ollama: http://localhost:11434 (ucretsiz, anahtarsiz)'
    return metin


# ----------------------------------------------------------------------------
# 2) WEB ARASTIRMA (anahtarsiz)
# ----------------------------------------------------------------------------

def _html_temizle(html):
    html = re.sub(r'(?is)<(script|style).*?</\1>', ' ', html)
    html = re.sub(r'(?s)<[^>]+>', ' ', html)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&quot;', '"'),
                 ('&#39;', "'"), ('&lt;', '<'), ('&gt;', '>')):
        html = html.replace(a, b)
    return re.sub(r'\s+', ' ', html).strip()


def web_sonuclari(sorgu, adet=5):
    """Anahtarsiz arama (baslik + ozet) listesi.

    NOT: html.duckduckgo.com bot korumasina takiliyor; lite.duckduckgo.com
    POST ile calisiyor. O da bos donerse Vikipedi aramasi devreye girer.
    """
    import urllib.parse
    import urllib.request
    sonuc = []
    try:
        govde = urllib.parse.urlencode({'q': str(sorgu)}).encode('utf-8')
        istek = urllib.request.Request('https://lite.duckduckgo.com/lite/', data=govde, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/124.0 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded'})
        with urllib.request.urlopen(istek, timeout=20) as c:
            html = c.read().decode('utf-8', 'ignore')
        for blok in re.findall(r'(?s)class="result-link"[^>]*>(.*?)</a>', html)[:adet * 2]:
            baslik = _html_temizle(blok)
            if baslik and len(baslik) > 3:
                sonuc.append(baslik)
        for ozet in re.findall(r'(?s)class="result-snippet"[^>]*>(.*?)</td>', html)[:adet]:
            temiz = _html_temizle(ozet)
            if temiz:
                sonuc.append(temiz)
    except Exception:
        pass
    if not sonuc:
        # yedek: Vikipedi aramasi + ozetleri
        try:
            import jarvis_anlama as _an
            for baslik in _an.wiki_ara(sorgu, 'tr', 2) or []:
                sonuc.append(baslik)
                ozet = _an.wiki_ozet(baslik, 'tr')
                if ozet:
                    sonuc.append(ozet[:300])
        except Exception:
            pass
    return [s for s in sonuc if s]


def web_arastir(sorgu):
    """GERCEK arastirma: Vikipedi + arama sonuclari + AI ozeti -> net cevap.

    ONEMLI: Site ACMAZ. Sonuc yoksa "bulunamadi" deyip birakmaz; Vikipedi
    aramasi ve ucretsiz AI zinciriyle cevap uretmeyi dener.
    Ayrica arama sorgusunu temizler: "ara https nedir" -> "https".
    """
    kaynaklar = []
    temiz = str(sorgu or '').strip()
    # OFFLINE mod: internet yok/istenmiyor -> arastirma yapilmaz, durustce soyle.
    try:
        import jarvis_anlama as _an_off
        if not _an_off.online_mi():
            _kb = _an_off._kb_ara(_an_off.fold(temiz))
            if _kb:
                return _kb
            return ('📴 OFFLINE moddasin: internet kullanmiyorum, bu konu yerel bilgi '
                    'kutumda da yok. ONL moduna gec (buton ya da "online mod") ve '
                    'tekrar sor; o zaman arastirip cevaplarim.')
    except Exception:
        pass
    try:
        import jarvis_anlama as _an
        # yerel bilgi kutusu bu soruyu biliyorsa direkt onu ver
        _kb = _an._kb_ara(_an.fold(temiz))
        if _kb:
            return _kb
        _konu = _an.konu_cikar(temiz)
        if _konu and len(_konu) >= 2:
            temiz = _konu
    except Exception:
        pass
    sorgu = temiz
    try:
        import jarvis_anlama as _an
        for baslik in (_an.wiki_ara(sorgu, 'tr', 2) or []):
            ozet = _an.wiki_ozet(baslik, 'tr')
            if ozet:
                kaynaklar.append(ozet)
    except Exception:
        pass
    try:
        kaynaklar.extend(web_sonuclari(sorgu, 6))
    except Exception:
        pass

    ham = '\n'.join('- ' + s for s in kaynaklar[:8] if s)
    if ham:
        try:
            ozet = ai_sor('Su kaynaklardan yararlanarak soruyu Turkce, 3-5 cumlede net '
                          've dogrudan cevapla; kaynakta yoksa uydurma.\n'
                          'Soru: %s\nKaynaklar:\n%s' % (sorgu, ham))
            if ozet:
                return str(ozet).strip()
        except Exception:
            pass
        return 'Arastirma ozeti:\n' + ham

    # Hicbir kaynak yoksa: yerel bilgi kutusu + AI
    try:
        import jarvis_anlama as _an
        cevap = _an.bilgi_ver(sorgu)
        if cevap:
            return cevap
    except Exception:
        pass
    try:
        cevap = ai_sor(sorgu)
        if cevap:
            return str(cevap).strip()
    except Exception:
        pass
    return '"%s" icin kaynak bulunamadi (internet baglantisini kontrol et).' % sorgu


# ----------------------------------------------------------------------------
# 3) STEAM - gercek VDF okuyucu (regex degil)
# ----------------------------------------------------------------------------

def _vdf_ayristir(metin):
    """Valve KeyValues (VDF/ACF) metnini sozluge cevirir.

    Klasik anahtar/blok yigini algoritmasi: kardes bloklar birbirine karismaz
    (eski surumde nested bloklar ust seviye anahtarlari siliyordu).
    """
    kok = {}
    yigin = [kok]
    bekleyen = [None]  # her blok icin 'su anahtari bekliyorum' durumu
    i = 0
    n = len(metin)
    while i < n:
        c = metin[i]
        if c == '"':
            j = i + 1
            parcalar = []
            while j < n:
                if metin[j] == '\\' and j + 1 < n:
                    parcalar.append(metin[j + 1])
                    j += 2
                    continue
                if metin[j] == '"':
                    break
                parcalar.append(metin[j])
                j += 1
            deger = ''.join(parcalar)
            i = j + 1
            if bekleyen[-1] is None:
                bekleyen[-1] = deger
            else:
                yigin[-1][bekleyen[-1]] = deger
                bekleyen[-1] = None
        elif c == '{':
            k = bekleyen[-1] or '_'
            mevcut = yigin[-1].get(k)
            if isinstance(mevcut, dict):
                yeni = mevcut
            else:
                yeni = {}
                yigin[-1][k] = yeni
            bekleyen[-1] = None
            yigin.append(yeni)
            bekleyen.append(None)
            i += 1
        elif c == '}':
            if len(yigin) > 1:
                yigin.pop()
                bekleyen.pop()
            i += 1
        else:
            i += 1
    return kok


def _vdf_oku(yol):
    try:
        with open(yol, 'r', encoding='utf-8', errors='ignore') as f:
            return _vdf_ayristir(f.read())
    except Exception:
        return {}


def steam_klasoru():
    """Steam kurulum klasorunu bulur (registry + bilinen yollar)."""
    try:
        import winreg
        for kok_adi, alt in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam'),
                             (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam')):
            try:
                with winreg.OpenKey(kok_adi, alt) as k:
                    for deger in ('SteamPath', 'InstallPath'):
                        try:
                            yol = winreg.QueryValueEx(k, deger)[0]
                            if yol and os.path.isdir(yol):
                                return os.path.normpath(yol)
                        except Exception:
                            continue
            except Exception:
                continue
    except Exception:
        pass
    for yol in (r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam',
                r'D:\Steam', r'D:\SteamLibrary', r'E:\Steam'):
        if os.path.isdir(yol):
            return yol
    return None


def _kutuphaneler(steam):
    """libraryfolders.vdf uzerinden tum kutuphane diskleri."""
    kutuphaneler = [steam]
    vdf = os.path.join(steam, 'steamapps', 'libraryfolders.vdf')
    veri = _vdf_oku(vdf)
    try:
        alt = veri.get('libraryfolders') or veri.get('LibraryFolders') or {}
        for _k, v in alt.items():
            if isinstance(v, dict):
                yol = v.get('path')
            else:
                yol = v if isinstance(v, str) else None
            if yol:
                yol = yol.replace('\\\\', '\\')
                if os.path.isdir(yol) and yol not in kutuphaneler:
                    kutuphaneler.append(yol)
    except Exception:
        pass
    return kutuphaneler


def _oynama_sureleri(steam):
    """localconfig.vdf'ten appid -> dakika oynama sozlugu."""
    sureler = {}
    try:
        ud = os.path.join(steam, 'userdata')
        if not os.path.isdir(ud):
            return sureler
        for kullanici in os.listdir(ud):
            yol = os.path.join(ud, kullanici, 'config', 'localconfig.vdf')
            if not os.path.isfile(yol):
                continue
            veri = _vdf_oku(yol)
            apps = (((veri or {}).get('UserLocalConfigStore') or {})
                    .get('Software') or {}).get('Valve') or {}
            apps = (apps.get('Steam') or {}).get('apps') or {}
            for appid, bilgi in apps.items():
                if isinstance(bilgi, dict):
                    dk = bilgi.get('Playtime') or bilgi.get('playtime')
                    try:
                        sureler[str(appid)] = int(dk)
                    except Exception:
                        pass
    except Exception:
        pass
    return sureler


def steam_oyunlar():
    """Kurulu Steam oyunlari: [{'appid','ad','boyut','oynama'}]."""
    steam = steam_klasoru()
    if not steam:
        return None
    oyunlar = []
    sureler = _oynama_sureleri(steam)
    for k in _kutuphaneler(steam):
        acf_dir = os.path.join(k, 'steamapps')
        if not os.path.isdir(acf_dir):
            continue
        for ad in sorted(os.listdir(acf_dir)):
            if not ad.lower().startswith('appmanifest_') or not ad.endswith('.acf'):
                continue
            veri = _vdf_oku(os.path.join(acf_dir, ad))
            durum = veri.get('AppState') or {}
            isim = durum.get('name')
            if not isim:
                continue
            appid = str(durum.get('appid') or '')
            try:
                boyut = int(durum.get('SizeOnDisk') or 0) / (1024 ** 3)
            except Exception:
                boyut = 0.0
            kayit = {'appid': appid, 'ad': isim, 'boyut': round(boyut, 2),
                     'oynama': sureler.get(appid, 0), 'kutuphane': k}
            if not any(o['ad'] == isim for o in oyunlar):
                oyunlar.append(kayit)
    oyunlar.sort(key=lambda o: -o.get('oynama', 0))
    return oyunlar


def _sure_metni(dk):
    try:
        dk = int(dk)
    except Exception:
        return 'bilinmiyor'
    if dk <= 0:
        return 'hic oynanmamis'
    if dk < 60:
        return '%d dakika' % dk
    return '%d saat %d dk' % (dk // 60, dk % 60)


def steam_ozet():
    """Kurulu oyunlarin okunabilir listesi."""
    steam = steam_klasoru()
    if not steam:
        return ('Steam bulunamadi. Kurulu degilse kurman gerekir '
                '(winget ile "steam" kurabilirim).')
    oyunlar = steam_oyunlar() or []
    if not oyunlar:
        return 'Steam kutuphanende kurulu oyun gorunmuyor.'
    satirlar = ['Steam kutuphanende %d oyun kurulu:' % len(oyunlar)]
    for o in oyunlar[:20]:
        satirlar.append('  - %s (%.1f GB, oynama: %s)' % (o['ad'], o['boyut'], _sure_metni(o['oynama'])))
    en_cok = [o for o in oyunlar if o.get('oynama')]
    if en_cok:
        satirlar.append('En cok oynadigin: %s (%s)' % (en_cok[0]['ad'], _sure_metni(en_cok[0]['oynama'])))
    return '\n'.join(satirlar)


def steam_oyun_bul(ad):
    """Isim benzerligi ile oyun arar."""
    oyunlar = steam_oyunlar() or []
    hedef = tr_kucuk(ad)
    if not hedef:
        return None
    tam = [o for o in oyunlar if tr_kucuk(o['ad']) == hedef]
    if tam:
        return tam[0]
    kismi = [o for o in oyunlar if hedef in tr_kucuk(o['ad'])]
    if kismi:
        return kismi[0]
    kelimeler = [k for k in re.split(r'\s+', hedef) if len(k) > 3]
    for o in oyunlar:
        for k in kelimeler:
            if k in tr_kucuk(o['ad']):
                return o
    return None


def steam_baslat(ad):
    """Oyunu steam:// ile gercekten baslatir."""
    o = steam_oyun_bul(ad)
    if not o:
        return 'Kutuphanede "%s" adli oyun yok. "steam kutuphanem" dersen hepsini sayarim.' % ad
    if not o.get('appid'):
        return '%s icin appid bulunamadi.' % o['ad']
    try:
        import webbrowser
        ok = False
        try:
            os.startfile('steam://rungameid/%s' % o['appid'])
            ok = True
        except Exception:
            ok = webbrowser.open('steam://rungameid/%s' % o['appid'])
        if ok:
            return '%s baslatiliyor (appid %s). Iyi oyunlar!' % (o['ad'], o['appid'])
        return '%s acilamadi.' % o['ad']
    except Exception as e:
        return 'Baslatma hatasi: %s' % str(e)[:100]


def steam_oner(istek=''):
    """Kurulu oyunlara + ucretsizlere dayali oneri."""
    oyunlar = steam_oyunlar() or []
    parcalar = []
    if oyunlar:
        oynanmis = [o for o in oyunlar if o.get('oynama')]
        oynanmamis = [o for o in oyunlar if not o.get('oynama')]
        if oynanmis:
            parcalar.append('Kutuphanende en cok oynadiklarin: ' +
                            ', '.join('%s (%s)' % (o['ad'], _sure_metni(o['oynama'])) for o in oynanmis[:3]) + '.')
            parcalar.append('Ayni tarz devam edersen %s iyi gider.' % oynanmis[0]['ad'])
        if oynanmamis:
            parcalar.append('Hic acmadiklarin: ' +
                            ', '.join(o['ad'] for o in oynanmamis[:4]) +
                            ' — bunlardan birini denemeye ne dersin?')
    else:
        parcalar.append('Steam kutuphanesi okunamadi, kurulu oyun goremiyorum.')
    ucretsiz = steam_ucretsiz()
    if ucretsiz:
        parcalar.append('Su an ucretsiz oynanabilenler: ' + ', '.join(ucretsiz[:5]))
    return '\n'.join(parcalar) if parcalar else 'Oneri uretemedim.'


def _http_metin(url, zaman=25, basliklar=None):
    import urllib.request
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) JARVIS/1.0'}
    if basliklar:
        h.update(basliklar)
    istek = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(istek, timeout=zaman) as c:
        return c.read().decode('utf-8', 'ignore')


def steam_ucretsiz():
    """Steam'de ucretsiz oynanan populer oyunlar.
    NOT: Steam bu ucu JSON doner; HTML kacisli oldugu icin once JSON'a cevrilir."""
    try:
        ham = _http_metin(
            'https://store.steampowered.com/search/results/?query&start=0&count=20'
            '&maxprice=free&category1=998&infinite=1')
        html = ham
        try:
            veri = json.loads(ham)
            html = veri.get('results_html') or ham
        except Exception:
            pass
        adlar = re.findall(r'<span class="title">([^<]+)</span>', html)
        if adlar:
            return [a.strip() for a in adlar][:8]
        # yedek: appid listesinden isim cikar
        adlar = re.findall(r'<span class="title">([^<\\]+)', html.replace('\\"', '"'))
        return [a.strip() for a in adlar][:8]
    except Exception:
        return []


def epic_ucretsiz():
    """Epic Games'in haftalik ucretsiz oyunlari."""
    try:
        veri = json.loads(_http_metin(
            'https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions'
            '?locale=tr&country=TR&allowCountries=TR'))
        ogeler = (((veri.get('data') or {}).get('Catalog') or {}).get('searchStore') or {}).get('elements') or []
        sonuc = []
        for o in ogeler:
            baslik = o.get('title')
            promosyon = o.get('promotions') or {}
            if baslik and (promosyon.get('promotionalOffers') or promosyon.get('upcomingPromotionalOffers')):
                sonuc.append(baslik)
        return sonuc
    except Exception:
        return []


# ----------------------------------------------------------------------------
# 4) INDIRICI - yasal olanlar (winget / resmi sayfa / URL)
# ----------------------------------------------------------------------------

# Korsan, hile, crack, keygen, torrent -> hicbir zaman indirilmez/kurulmaz.
YASAK_KALIPLAR = (
    r'\bcrack\w*', r'\bkorsan\w*', r'\bkeygen\w*', r'\bpatcher\b', r'\btorrent\w*',
    r'lua\s*tools?', r'luatools', r'\bmod\s*menu\b', r'\bcheat\w*', r'\bhile\w*',
    r'\baimbot\w*', r'\bwallhack\w*', r'\bkeylogger\w*', r'\bddos\w*',
    r'\bphishing\b', r'\boltala\w*', r'\bsifre\s*kir\w*',
    r'bedava\s+(gta|fifa|pes|call of duty|valorant|pubg|minecraft|oyun)',
    r'ucretsiz\s+(gta|fifa|pes|call of duty|valorant|pubg|minecraft)',
    r'\bnitro\s*generator\b', r'\bhesap\s*(cal|çal)\w*',
    r'\bhackle\w*', r'\bhack\w*', r'\bsizma\b', r'\bexploit\w*',
    r'\bparazit\b', r'\bjammer\b',
)

YASAK_CEVAP = (
    'Bunu yapamam Abdulkadir - korsan indirme, hile/crack araci kurma ve baskasinin '
    'sistemine izinsiz erisim yasal degil. Ama su yasal yollarla ayni ihtiyaci karsilarim:\n'
    '  - Steam/Epic ucretsiz oyunlar: "ucretsiz oyunlar" de, listeleyeyim\n'
    '  - Indirimli fiyat takibi: "steam indirim" de, bakayim\n'
    '  - Oyun kurulumu: "steam kur" / "winget ile kur: <program>"'
)


def yasak_mi(metin):
    """True ise istek yasadisi kapsamda (indirme/kurulum denenmez)."""
    k = tr_kucuk(metin)
    for kalip in YASAK_KALIPLAR:
        try:
            if re.search(kalip, k):
                return True
        except Exception:
            continue
    return False


def yasak_aciklama(metin):
    k = tr_kucuk(metin)
    if re.search(r'lua\s*tools?|luatools|mod\s*menu|cheat|hile|aimbot|wallhack', k):
        return ('LuaTools gibi hile/mod araclari GTA gibi oyunlarda yasak ve hesabini '
                'kalici banlatir; kurmam mumkun degil.\n' + YASAK_CEVAP)
    if re.search(r'crack|korsan|keygen|torrent|bedava\s+(gta|fifa|pes|pubg|valorant|minecraft)', k):
        return ('Korsan indirme yapamam: hem yasal degil hem de bilgisayarina zararli '
                'yazilim bulasma riski yuksek.\n' + YASAK_CEVAP)
    return ('Bu istek yasadisi kapsama giriyor (izinsiz erisim/parazit/casus). '
            'Sadece KENDI cihazlarin icin guvenlik kontrolu yapabilirim.\n' + YASAK_CEVAP)


def winget_var():
    try:
        r = subprocess.run(['winget', '--version'], capture_output=True, text=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def winget_ara(ad):
    """winget'te paket arar: [(id, ad, surum)]"""
    if not ad:
        return []
    try:
        r = subprocess.run(['winget', 'search', str(ad), '--accept-source-agreements'],
                           capture_output=True, text=True, timeout=90,
                           encoding='utf-8', errors='ignore')
        satirlar = [s for s in (r.stdout or '').splitlines() if s.strip()]
        sonuc = []
        for s in satirlar:
            if s.startswith('Name') or set(s.strip()) <= set('- '):
                continue
            parcalar = re.split(r'\s{2,}', s.strip())
            if len(parcalar) >= 2 and parcalar[0] and parcalar[0] != 'Name':
                paket_id = parcalar[1] if len(parcalar) > 1 else ''
                surum = parcalar[2] if len(parcalar) > 2 else ''
                sonuc.append((paket_id, parcalar[0], surum))
        return sonuc
    except Exception:
        return []


def winget_kur(ad, log=None, sessiz=True):
    """winget ile kurulum. Uzun surer; cagiran taraf thread icinde calistirmali."""
    def _yaz(m):
        if log:
            try:
                log(m)
            except Exception:
                pass
    if not winget_var():
        return 'winget bulunamadi (Windows 10 1809+ gerekir).'
    adaylar = winget_ara(ad)
    if not adaylar:
        return '"%s" icin winget paketi bulunamadi. Resmi indirme sayfasini acabilirim ("kurulum sayfasi: %s").' % (ad, ad)
    paket = adaylar[0]
    _yaz('SYS: winget -> %s (%s) kuruluyor...' % (paket[1], paket[0]))
    komut = ['winget', 'install', '--id', paket[0], '-e',
             '--accept-package-agreements', '--accept-source-agreements']
    if sessiz:
        komut.append('--silent')
    try:
        surec = subprocess.Popen(komut, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding='utf-8', errors='ignore')
        son_satir = ''
        for satir in surec.stdout or []:
            satir = satir.strip()
            if satir and ('%' in satir or 'instal' in satir.lower() or 'downl' in satir.lower()):
                if satir != son_satir:
                    _yaz('SYS: ' + satir[:150])
                    son_satir = satir
        surec.wait(timeout=1800)
        if surec.returncode == 0:
            return '%s kuruldu.' % paket[1]
        return '%s kurulumu tamamlanmadi (kod %s). Manuel denemek icin: winget install --id %s -e' % (
            paket[1], surec.returncode, paket[0])
    except Exception as e:
        return 'Kurulum hatasi: %s' % str(e)[:150]


KURULUM_SAYFALARI = {
    'steam': 'https://store.steampowered.com/about/',
    'epic': 'https://store.epicgames.com/tr/download',
    'discord': 'https://discord.com/download',
    'chrome': 'https://www.google.com/chrome/',
    'firefox': 'https://www.mozilla.org/tr/firefox/new/',
    'opera': 'https://www.opera.com/tr',
    'brave': 'https://brave.com/download/',
    'vlc': 'https://www.videolan.org/vlc/',
    'spotify': 'https://www.spotify.com/tr/download/windows/',
    'obs': 'https://obsproject.com/tr/download',
    'python': 'https://www.python.org/downloads/windows/',
    'vscode': 'https://code.visualstudio.com/download',
    'code': 'https://code.visualstudio.com/download',
    '7zip': 'https://www.7-zip.org/download.html',
    'winrar': 'https://www.win-rar.com/download.html',
    'gimp': 'https://www.gimp.org/downloads/',
    'blender': 'https://www.blender.org/download/',
    'audacity': 'https://www.audacityteam.org/download/',
    'notepad': 'https://notepad-plus-plus.org/downloads/',
    'anydesk': 'https://anydesk.com/tr/downloads',
    'teamviewer': 'https://www.teamviewer.com/tr/download/windows/',
    'whatsapp': 'https://www.whatsapp.com/download',
    'telegram': 'https://desktop.telegram.org/',
    'zoom': 'https://zoom.us/download',
    'java': 'https://www.java.com/tr/download/',
    'npm': 'https://nodejs.org/tr/download',
    'nodejs': 'https://nodejs.org/tr/download',
    'git': 'https://git-scm.com/download/win',
}


def hile_panosu_ac():
    """HILE PANOSU / WAND ayristigisini acar. Jarvis_yenilik/javvis_plus
    icerisinden cagrilabilir; aslinda hile_panosu.py Python 3.12 ile
    calistirilir."""
    try:
        import jarvis_yenilik as _jy
        if getattr(_jy, 'ile_baslat', None):
            return _jy.ile_baslat()
    except Exception:
        pass
    try:
        import jarvis_plus as _jp
        if getattr(_jp, 'ile_baslat', None):
            return _jp.ile_baslat()
    except Exception:
        pass
    try:
        import subprocess as _sp
        import os as _os
        _repo = _os.path.dirname(_os.path.abspath(__file__))
        _py312 = _os.path.join(_repo, 'tools', 'py312', 'python.exe')
        _hedef = _os.path.join(_repo, 'hile_panosu.py')
        import subprocess as _sp2
        _sp2.Popen([_py312, _hedef], cwd=_repo, creationflags=0x08000000)
        return 'HILE PANOSU acildi (tools/hile_panosu.py).'
    except Exception as e:
        return 'HILE PANOSU acilamadi: ' + repr(e)[:120]


def kurulum_sayfasi(ad):
    """Yazilimin resmi indirme sayfasini acar."""
    k = tr_kucuk(ad)
    hedef = None
    for anahtar, url in KURULUM_SAYFALARI.items():
        if anahtar in k:
            hedef = url
            break
    if not hedef:
        return None
    try:
        import webbrowser
        webbrowser.open(hedef)
        return '%s resmi indirme sayfasi acildi: %s\nKurulumu sen onayla; indirilen dosyayi "\u2026 kur" diye soylersen kurarim.' % (ad, hedef)
    except Exception as e:
        return 'Sayfa acilamadi: %s' % str(e)[:80]


def dosya_indir(url, klasor=None, ilerleme=None):
    """URL'den dosyayi JARVIS_Saklanan'a indirir."""
    import urllib.request
    hedef_klasor = klasor or depo_klasoru()
    os.makedirs(hedef_klasor, exist_ok=True)
    ad = os.path.basename(url.split('?')[0]) or ('indirilen_%s' % time.strftime('%Y%m%d_%H%M%S'))
    hedef = os.path.join(hedef_klasor, ad)
    try:
        istek = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) JARVIS/1.0'})
        with urllib.request.urlopen(istek, timeout=60) as c, open(hedef, 'wb') as f:
            toplam = int(c.headers.get('Content-Length') or 0)
            inen = 0
            while True:
                parca = c.read(262144)
                if not parca:
                    break
                f.write(parca)
                inen += len(parca)
                if ilerleme and toplam:
                    try:
                        ilerleme(inen, toplam)
                    except Exception:
                        pass
        mb = os.path.getsize(hedef) / (1024 * 1024)
        return 'Indirildi: %s (%.1f MB) -> %s' % (ad, mb, hedef)
    except Exception as e:
        return 'Indirme hatasi: %s' % str(e)[:150]


# ----------------------------------------------------------------------------
# 5) GOZLEM (7/24 goz) - aktif pencere, ekran karesi
# ----------------------------------------------------------------------------

def aktif_pencere():
    """On plandaki pencerenin basligi ve sureci."""
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        k = ctypes.windll.kernel32
        h = u.GetForegroundWindow()
        if not h:
            return ('', '')
        uzunluk = u.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(uzunluk + 1)
        u.GetWindowTextW(h, buf, uzunluk + 1)
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        surec = ''
        try:
            k.OpenProcess(0x1000, False, pid.value)
        except Exception:
            pass
        try:
            import psutil
            surec = psutil.Process(pid.value).name()
        except Exception:
            surec = ''
        return (buf.value, surec)
    except Exception:
        return ('', '')


def ekran_fotografi(yol=None):
    """Ekran karesi alir; yol None ise RAM'de PIL goruntusu doner."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        if yol:
            img.save(yol)
            return yol
        return img
    except Exception:
        return None


def ekran_boyut():
    try:
        import ctypes
        u = ctypes.windll.user32
        return (u.GetSystemMetrics(0), u.GetSystemMetrics(1))
    except Exception:
        return (0, 0)


# ----------------------------------------------------------------------------
# 6) MUZIK / MEDYA
# ----------------------------------------------------------------------------

def _medya_tus(kod):
    """Windows medya tusu gonderir (179 = oynat/duraklat, 176/177 = sonraki/onceki)."""
    try:
        import ctypes
        u = ctypes.windll.user32
        u.keybd_event(kod, 0, 0, 0)
        u.keybd_event(kod, 0, 2, 0)
        return True
    except Exception:
        return False


MUZIK_UZANTI = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.wma', '.opus')


def _muzik_dosyalari(sinir=200):
    """Music klasorundeki ses dosyalari (varsa OneDrive muzikleri dahil)."""
    klasorler = [os.path.join(os.path.expanduser('~'), 'Music')]
    try:
        for ad in ('OneDrive', 'OneDrive - Personal'):
            klasorler.append(os.path.join(os.path.expanduser('~'), ad, 'Music'))
    except Exception:
        pass
    bulunan = []
    for klasor in klasorler:
        if not os.path.isdir(klasor):
            continue
        for kok, _d, dosyalar in os.walk(klasor):
            for ad in dosyalar:
                if ad.lower().endswith(MUZIK_UZANTI):
                    bulunan.append(os.path.join(kok, ad))
            if len(bulunan) >= sinir:
                break
        if bulunan:
            break
    return bulunan


def muzik_cal(ne=''):
    """GERCEK muzik calma: Spotify varsa acar ve oynatir; yoksa Music
    klasorundeki parcayi (istenen ada en yakin) varsayilan oynaticida acar.

    Donus: kullaniciya soylenecek kisa metin veya None.
    """
    import subprocess
    istek = (ne or '').strip()
    # 1) Spotify kurulu/oturum acik ise onu kullan
    try:
        os.startfile('spotify:')
        time.sleep(3.0)
        if istek:
            try:
                os.startfile('spotify:search:' + istek)
                time.sleep(2.0)
            except Exception:
                pass
        _medya_tus(179)  # oynat
        return ('🎵 Spotify acildi ve caliyor' + (' — arama: ' + istek if istek else '') + '.')
    except Exception:
        pass
    # 2) Yerel muzik dosyalari
    try:
        dosyalar = _muzik_dosyalari()
        if dosyalar:
            secili = dosyalar[0]
            if istek:
                esles = [d for d in dosyalar if tr_kucuk(istek) in tr_kucuk(os.path.basename(d))]
                if esles:
                    secili = esles[0]
            os.startfile(secili)
            return '🎵 Caliyorum: ' + os.path.basename(secili)
        muzik_klasor = os.path.join(os.path.expanduser('~'), 'Music')
        if os.path.isdir(muzik_klasor):
            os.startfile(muzik_klasor)
            return ('Music klasorunu actim ama icinde ses dosyasi yok. '
                    'Bir sarki atarsan buradan calarim; ya da "spotify kur" diyebilirsin.')
    except Exception as hata:
        return 'Muzik acilamadi: ' + str(hata)[:80]
    # 3) Son care: medya tusu
    if _medya_tus(179):
        return 'Medya oynat/duraklat tusu gonderildi.'
    return None


# ----------------------------------------------------------------------------
# 7) YETENEK YONLENDIRICI - komut_calistir'dan once denenir
# ----------------------------------------------------------------------------

def _uygulama_ac(ad):
    import webbrowser
    k = tr_kucuk(ad)
    siteler = {
        'youtube': 'https://www.youtube.com', 'google': 'https://www.google.com',
        'gmail': 'https://mail.google.com', 'github': 'https://github.com',
        'netflix': 'https://www.netflix.com', 'whatsapp': 'https://web.whatsapp.com',
        'instagram': 'https://www.instagram.com', 'twitter': 'https://twitter.com',
        'x': 'https://x.com', 'tiktok': 'https://www.tiktok.com',
        'linkedin': 'https://www.linkedin.com', 'steam magaza': 'https://store.steampowered.com',
        'epic': 'https://store.epicgames.com/tr', 'trendyol': 'https://www.trendyol.com',
        'hepsiburada': 'https://www.hepsiburada.com', 'twitch': 'https://www.twitch.tv',
        'spotify web': 'https://open.spotify.com',
    }
    for anahtar, url in siteler.items():
        if anahtar in k:
            webbrowser.open(url)
            return 'Acilan site: ' + url
    exeler = {
        'notepad': 'notepad', 'not defteri': 'notepad', 'hesap makinesi': 'calc',
        'hesap makinesı': 'calc', 'calc': 'calc', 'paint': 'mspaint',
        'cizim': 'mspaint', 'komut': 'cmd', 'cmd': 'cmd', 'terminal': 'wt',
        'powershell': 'powershell', 'explorer': 'explorer', 'ayarlar': 'ms-settings:',
        'gorev yoneticisi': 'taskmgr', 'task manager': 'taskmgr',
        'ekran alintisi': 'snippingtool', 'snipping': 'snippingtool',
    }
    for anahtar, komut in exeler.items():
        if anahtar in k:
            try:
                os.startfile(komut)
                return '%s acildi.' % anahtar
            except Exception:
                try:
                    subprocess.Popen(komut, shell=True)
                    return '%s acildi.' % anahtar
                except Exception as e:
                    return 'Acilamadi: %s' % str(e)[:80]
    return None


def komut(metin, log=None):
    """Yetenek katmani: yasadisi istek -> uyari, digerleri -> gercek islem.
    Donus: cevap metni veya None (bu katman cevap vermedi)."""
    m = tr_kucuk(metin)
    if not m or len(m) > 400:
        return None

    def _yaz(s):
        if log:
            try:
                log(s)
            except Exception:
                pass

    # --- 0) YASAL SINIR (her seyden once) ---
    if yasak_mi(m):
        _yaz('YASAK | ' + m[:60])
        return yasak_aciklama(m)

    # --- 0b) SOHBET KAPISI ---
    # Uzun/sohbet cumlelerinde yerel katman kelime avina cikmasin; cevabi
    # uygulamanin kendi AI'si versin. ("... senin zekan nasil bir sey ..."
    # cumlesi yerel bilgi aramasina takilip "kaynak bulamadim" diyordu.)
    try:
        import jarvis_anlama as _an_k
        if not _an_k.komut_uygun(m):
            return None
    except Exception:
        pass

    # --- 0c) MOD: online / offline (buton ile ayni isi yapar) ---
    try:
        import jarvis_anlama as _an_md
        _hedef = _an_md.mod_iste(m)
        if _hedef == 'online':
            _yaz('MOD_ONLINE | ' + m[:50])
            return _an_md.mod_degistir('online')
        if _hedef == 'offline':
            _yaz('MOD_OFFLINE | ' + m[:50])
            return _an_md.mod_degistir('offline')
        if _an_md.mod_komutu_mu(m):
            _yaz('MOD_DURUM | ' + m[:50])
            return _an_md.mod_etiket()
    except Exception:
        pass

    # --- 1) AI anahtar durumu ---
    if re.search(r'(hangi|ne)\s*(ai|yapay zeka)|ai anahtar|ucretsiz ai|ai durum', m):
        return ai_anahtar_durumu()

    # --- 1b) MUZIK / MEDYA ("muzik ac", "undertale muzik cal") ---
    try:
        try:
            import jarvis_anlama as _an_m
            _m_duz = _an_m.duzelt(metin)   # "muzila ac" -> "muzik ac"
        except Exception:
            _m_duz = m
        if (re.search(r'\b(muzik|muzikler|sarki|sarkilar|music)\b', _m_duz)
                and re.search(r'\b(ac|cal|oynat|baslat)\b', _m_duz)):
            parca = re.sub(r'(?i)\b(muzik|müzik|muzikler|sarki|şarkı|sarkilar|music|cal|çal|'
                           r'oynat|ac|aç|baslat|başlat|lutfen|lütfen|jarvis|bana|bir|tane|'
                           r'muzigi|müziği)\b', ' ', metin)
            parca = re.sub(r'\s+', ' ', parca).strip(' -:.')
            if len(parca) > 60:
                parca = ''
            try:
                import jarvis_anlama as _an_m2
                parca = _an_m2.duzelt(parca) or parca
            except Exception:
                pass
            _yaz('MUZIK | ' + (parca or 'genel'))
            _m = muzik_cal(parca)
            if _m:
                return _m
    except Exception:
        pass

    # --- 2) Arastirma (uzun fiiller once; ayirici sart, 'arastirma' yi yemesin) ---
    arama = re.match(r'^(?:arastir|araştır|arastır|webde ara|internette ara|google\'?da ara|ara)'
                     r'(?:\s+|\s*:\s*)(.+)$', m)
    if arama:
        _yaz('ARASTIRMA | ' + arama.group(1)[:60])
        return web_arastir(arama.group(1))
    if m.startswith('arastir:') or m.startswith('ara:'):
        return web_arastir(metin.split(':', 1)[-1].strip())

    # --- 3) Steam ---
    if re.search(r'steam|oyun', m):
        if re.search(r'ucretsiz oyun|bedava oyun|free oyun', m):
            liste = steam_ucretsiz()
            epic = epic_ucretsiz()
            cevaplar = []
            if liste:
                cevaplar.append('Steam ucretsizler:\n  - ' + '\n  - '.join(liste))
            if epic:
                cevaplar.append('Epic haftalik ucretsiz:\n  - ' + '\n  - '.join(epic))
            if cevaplar:
                return '\n'.join(cevaplar)
            return 'Ucretsiz oyun listesi alinamadi (internet?).'
        if re.search(r'indirim|kampanya|fiyat', m):
            liste = steam_ucretsiz()
            return ('Steam indirim/ucretsiz taramasi: ' +
                    (', '.join(liste[:6]) if liste else 'liste alinamadi'))
        baslat = re.search(r'(?:baslat|oyna|ac)\s*[:\-]?\s*(.+)$', m)
        if baslat and re.search(r'baslat|oyna', m):
            aday = baslat.group(1).strip(' :')
            if aday and len(aday) > 1:
                return steam_baslat(aday)
        if re.search(r'kutuphane|oyunum|oyunlar\w*|nel(er)?\s*var|ne\s+var|listele|goster|bak', m):
            return steam_ozet()
        if re.search(r'oner|tavsiye', m):
            return steam_oner(m)
    if 'steam kur' in m or ('steam' in m and 'kur' in m and 'kutuphane' not in m):
        sayfa = kurulum_sayfasi('steam')
        return sayfa or 'Steam kurulum sayfasi acilamadi.'

    # --- 4) Indirme / kurulum ---
    kur = re.search(r'(?:winget ile|paket ile|otomatik)\s*(?:kur|yukle)[:\s]*(.+)$', m)
    if not kur:
        kur = re.search(r'(?:kur|yukle|kurulum)\s*[:\-]?\s*(.+)$', m)
    if kur and ('kur' in m or 'yukle' in m):
        aday = kur.group(1).strip(' :.,')
        if aday and len(aday) > 1 and not re.search(r'kendini|bilgisayar|sistemi', aday):
            _yaz('KURULUM | ' + aday[:60])
            return winget_kur(aday, log=log)
    sayfa = re.search(r'(?:kurulum|indirme)\s*(?:sayfasi|sayfası|linki)\s*[:\-]?\s*(.+)$', m)
    if sayfa:
        aday = sayfa.group(1).strip(' :.')
        c = kurulum_sayfasi(aday)
        return c or ('%s icin bilinen resmi sayfa yok. Tam adini yaz: '
                     '"kurulum sayfasi: blender".' % aday)

    # --- 5) URL indirme ---
    url = re.search(r'https?://\S+', metin)
    if url and re.search(r'indir|kaydet|sakla|cek', m):
        return dosya_indir(url.group(0))

    # --- 6) Uygulama/site acma (SADECE acik komut: "X ac" / "ac X") ---
    # ONEMLI: Sorular asla site acmaz. "saat kac" gibi sozler yanlislikla
    # "ac" sanilip uygulama acmasin diye kelime siniri + soru kontrolu var.
    try:
        import jarvis_anlama as _an6
        _soru6 = _an6.soru_mu(m)
    except Exception:
        _an6 = None
        _soru6 = False
    if not _soru6:
        ac = re.match(r'^(?:ac|aç|baslat|başlat)\s*[:\-]?\s*(.+)$', m)
        if not ac:
            ac = re.match(r'^(.+?)\s+(?:ac|aç|baslat|başlat)$', m)
        if ac:
            aday = ac.group(1).strip(' :.')
            if 1 < len(aday) <= 40 and not re.search(r'\b(ne|nedir|nasil|nasıl|kac|kaç|mi|mı)\b', aday):
                if _an6 is not None:
                    try:
                        aday = _an6.duzelt(aday)
                    except Exception:
                        pass
                cevap = _uygulama_ac(aday)
                if cevap:
                    return cevap

    # --- 7) Beceri raporu ---
    if re.search(r'(kac|kaç)\s*komut|kac yetenek|ne yapabilirsin', m):
        return beceri_raporu()

    # --- 7b) AKILLI NIYET (esnek yakalama) ---
    # "oyunumda ne var", "7/24 izliyor musun", "unutkan misin" gibi sozler
    # cevabini yerel olarak bildigimiz NIYETLER; arastirmaya (Wikipedia'ya)
    # dusmeden once burada yakalanir.
    try:
        # HILE PANOSU / WAND eastidi (sadece cevrim disi tek kisilik oyun).
        try:
            import jarvis_yenilik as _jy
            if getattr(_jy, 'hile_panosu_ac', None):
                _jy.hile_panosu_ac()
                return None
        except Exception:
            pass

        import jarvis_plugin as _jp0
        _th_f = getattr(_jp0, '_akilli_tahmin', None)
        if _th_f:
            _th = _th_f(m)
            if _th:
                _yaz('NIYET | ' + m[:60])
                return _th
    except Exception:
        pass

    # --- 8) ANLAMA: SORU ise arastir ve GERCEK cevap ver (site ACMAZ) ---
    try:
        import jarvis_anlama as _an8
        # "ram ne kadar" gibi OLCUM sorulari sozluk tarifi degil gercek veri
        # ister; cevabi plugin/main tarafi (sistem metrigi) verir.
        if _an8.metrik_mi(m):
            return None
        _cvp = _an8.cevapla(metin, log=_yaz)
        if _cvp:
            _yaz('ANLAMA | ' + m[:60])
            return _cvp
    except Exception:
        pass
    return None


def beceri_raporu():
    """Gercek sayilabilir yetenek raporu (+ temsili komut uzayi)."""
    satirlar = ['Yetenek durumum:']
    satirlar.append('  - Ucretsiz AI zinciri: ' + (', '.join(s[0] for s in ai_saglayicilar()) or 'anahtar yok'))
    st = steam_klasoru()
    oyunlar = steam_oyunlar() if st else None
    satirlar.append('  - Steam: ' + ('%d oyun okundu' % len(oyunlar) if oyunlar else 'bulunamadi'))
    satirlar.append('  - winget: ' + ('hazir' if winget_var() else 'yok'))
    try:
        import jarvis_komut_motoru as _km
        satirlar.append('  - Komut motoru: %s islevsel komut' % _km.islevsel_sayi())
        satirlar.append('  - Temsili komut uzayi: %s' % _km.temsili_sayi_metni())
    except Exception:
        satirlar.append('  - Komut motoru: yuklenemedi')
    sayi = sum(len(v) for v in (ogrenme_oku() or {}).values())
    satirlar.append('  - Ogrenme kaydi: %d' % sayi)
    return '\n'.join(satirlar)
