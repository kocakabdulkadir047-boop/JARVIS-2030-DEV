#!/usr/bin/env python
"""CloudEngineV2 - GERCEK saglayici arayuzu (mock kaldirildi).

ONLINE modu : FAZ 2 ucretsiz zinciri
              (OpenRouter -> Gemini -> GLM-4-Flash -> Groq).
OFFLINE modu: Dogrudan yerel Ollama (http://localhost:11434/api/chat),
              model qwen3:4b.
AUTO modu   : Once ucretsiz bulut zinciri; tumu basarisizsa yerel Ollama.

Ollama yanitindaki `thinking` ve `content` alanlari ayristirilir;
kullaniciya yalnizca gercek icerik (content) dondurulur.
"""

from __future__ import annotations

from typing import Optional, Dict, Any
import inspect
import json
import re
import threading
import time
import urllib.request
import urllib.error

# -------------------------------------------------------
# 1. SAGLAYICI SIRASI ve CONFIG
# -------------------------------------------------------

# ONLINE modunda deneme sirasi
CLAUDE_SONNET = "claude"
GEMINI = "gemini"
GROQ = "groq"
OPENROUTER = "openrouter"
ZAI_GLM = "zai_glm"
# Anahtarsiz gercek bulut saglayici (jarvis_yetenek zincirinde mevcut);

try:
    import jarvis_model_yonetici as _MY
except Exception:
    _MY = None

# GPT/OpenAI KESINLIKLE KAPALI
BLOCKED_PROVIDERS = {
    "openai",
    "gpt",
    "anthropic",
    "claude",
    "pollinations",
    "perplexity",
    "mistral",
    "cohere",
    "together",
    "fireworks",
    "xai",
    "deepseek",
}

# Guvenli saglayicilar (sadece bunlar kullanilacak)
SAFE_PROVIDERS = [GEMINI, GROQ, OPENROUTER, ZAI_GLM]

# -------------------------------------------------------
# 2. YEREL LLAMA.CPP / QWEN AYARLARI
# -------------------------------------------------------

# Eski OLLAMA_* degisken adlari, mevcut cagri noktalarini bozmamak
# icin uyumluluk amaciyla korunmustur. Artik Ollama kullanilmaz.
OLLAMA_BASE = "http://127.0.0.1:9931"
OLLAMA_HEALTH_URL = OLLAMA_BASE + "/health"
OLLAMA_TAGS_URL = OLLAMA_BASE + "/v1/models"
OLLAMA_URL = OLLAMA_BASE + "/v1/chat/completions"
OLLAMA_MODEL = "qwen35-local"
OLLAMA_ZAMAN_ASIMI = 240.0
OLLAMA_TAGS_ZAMAN_ASIMI = 5.0

# Sohbet icin sistem mesaji (Turkce JARVIS kimligi)
_SISTEM_MESAJI = (
    "Sen JARVIS adli Turkce yapay zeka asistanisin. "
    "Kisa, net ve dostane yanitlar ver. Gereksiz uzun aciklamadan kacin. "
    "Yanitini dogrudan yaz; dusuncelerini ayri alanda tut. "
    "Bu konusmanin onceki turlari rol etiketleriyle verilebilir: "
    "'user' satirlari KULLANICININ kendi mesajlaridir, "
    "'assistant' satirlari SENIN onceki cevaplarindir; ikisini karistirma. "
    "'Bir onceki mesajimda ne soyledim?' gibi sorularda kullanicinin "
    "EN SON 'user' mesajindaki ifadeyi aktar. "
    "'Sen ne cevap vermistin?' gibi sorularda senin onceki "
    "'assistant' cevabini aktar. "
    "Kullanici gecmisteki belirli bir mesaji veya cevabi sorarsa "
    "once ilgili mesaji dogru aktar. "
    "Kullanici yalnizca ne soylendigini soruyorsa gereksiz yorum, "
    "tahmin veya celiskili aciklama ekleme. "
    "Alintinin kesinliginden emin degilsen bunu acikca belirt. "
    "Gecmiste bulunmayan bir bilgi sorulursa uydurma; "
    "bu konusmada gecmedigini acikca soyle."
)


def gecmis_destekli(fn) -> bool:
    """Cagrilan katman `gecmis` parametresini kabul ediyor mu?

    Acik parametre yoksa **kwargs da yeterlidir.
    """
    try:
        parametreler = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    if 'gecmis' in parametreler:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD
               for p in parametreler.values())


def _gecmis_mesajlari(gecmis) -> tuple:
    """Gecmisi (ozet, mesajlar) olarak ayirir; ozet sistem mesajina katilir."""
    ozet = []
    mesajlar = []
    for girdi in gecmis or []:
        rol = ''
        icerik = ''
        if isinstance(girdi, dict):
            rol = str(girdi.get('role') or 'user').strip().lower()
            icerik = str(girdi.get('content') or '').strip()
        else:
            metin = str(girdi or '').strip()
            if metin.startswith('Kullanıcı: ') or metin.startswith('Kullanici: '):
                rol, icerik = 'user', metin.split(': ', 1)[1].strip()
            elif metin.startswith('JARVIS: '):
                rol, icerik = 'assistant', metin[len('JARVIS: '):].strip()
        if not icerik:
            continue
        if rol == 'system':
            ozet.append(icerik)
        elif rol in ('user', 'assistant'):
            mesajlar.append({'role': rol, 'content': icerik})
    return ozet, mesajlar

# Ollama varlik kontrolu onbellegi (30 sn)
_OLLAMA_CACHE = {"t": 0.0, "var": False}
_OLLAMA_CACHE_ARALIK = 30.0

# 16 GB RAM ve qwen3:4b icin: ayni anda TEK yerel cikarim.
_YEREL_CIKARIM_KILIT = threading.Lock()


def _bulut_yetki_gecerli(message: str, mode: str, yetki,
                         kaynak: Optional[str], *, tuket: bool) -> bool:
    """FAZ 2.2A son ag kapisi: HMAC bilet + oturum + kaynak + mod + mesaj.

    Entegrasyon modulu yuklenemezse veya bilet yoksa FAIL-CLOSED.
    """
    if not isinstance(yetki, dict) or not kaynak:
        return False
    try:
        from jarvis_chat_v2_entegrasyon import yetki_dogrula
        return bool(yetki_dogrula(
            yetki, mesaj=message, mod=mode, kaynak=kaynak, tuket=tuket))
    except Exception:
        return False


def _ollama_var() -> bool:
    """Yerel llama.cpp sunucusu ve beklenen Qwen modeli hazir mi? (30 sn onbellek)"""
    now = time.time()
    if now - _OLLAMA_CACHE["t"] < _OLLAMA_CACHE_ARALIK:
        return _OLLAMA_CACHE["var"]

    var = False
    try:
        with urllib.request.urlopen(
            OLLAMA_HEALTH_URL, timeout=OLLAMA_TAGS_ZAMAN_ASIMI
        ) as c:
            saglik = json.loads(c.read().decode("utf-8", "ignore"))

        if str(saglik.get("status", "")).lower() == "ok":
            with urllib.request.urlopen(
                OLLAMA_TAGS_URL, timeout=OLLAMA_TAGS_ZAMAN_ASIMI
            ) as c:
                veri = json.loads(c.read().decode("utf-8", "ignore"))

            modeller = [
                str(m.get("id", ""))
                for m in veri.get("data", [])
                if isinstance(m, dict)
            ]
            var = OLLAMA_MODEL in modeller
    except Exception:
        var = False

    _OLLAMA_CACHE["t"] = now
    _OLLAMA_CACHE["var"] = var
    return var




def _ollama_var_soft() -> bool:
    """Ollama varligini AG CAGIRMADAN raporlar (GOREV 2.7 / AŞAMA 5).

    Mod sorgusu gibi "aninda cevap" gerektiren yollarda ag gecikmesi
    olmasin diye: yalnizca ONBELLEKTEKI son bilgi kullanilir.
    Onbellek bos ise (ilk cagri) bilinmiyor -> False doner ve ag denenmez.
    """
    try:
        if _OLLAMA_CACHE.get('t'):
            return bool(_OLLAMA_CACHE.get('var'))
    except Exception:
        pass
    return False
def _metni_temizle(metin: str) -> str:
    """Qwen3 content alanina sizan think bloklarini temizler."""
    if not metin:
        return ""
    metin = re.sub(
        r" absorbed\s*",
        "",
        metin,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return metin.strip()


# -------------------------------------------------------
# 3. CLOUD ENGINE SINIFI
# -------------------------------------------------------

class CloudEngine:
    """Gercek saglayici arayuzu (mock yok)."""

    def __init__(self):
        # FAZ 2: ucretsiz coklu model yoneticisi (OpenRouter -> Gemini ->
        # GLM-4-Flash -> Groq). Ucretli modele gecis yapilmaz.
        self.provider_order: list[str] = list(
            getattr(_MY, 'SAGLAYICI_SIRASI',
                    (OPENROUTER, GEMINI, ZAI_GLM, GROQ)))
        self.blocked: set[str] = BLOCKED_PROVIDERS.copy()

    def _yonetici(self):
        if _MY is None:
            return None
        try:
            return _MY.get_yonetici()
        except Exception:
            return None

    @staticmethod
    def _yonetici_calistir(yonetici, message, *, mode, yetki, kaynak,
                           gecmis):
        kw = dict(sistem=_SISTEM_MESAJI, zaman=60, max_tokens=1200,
                  sicaklik=0.6, mode=mode, yetki=yetki, kaynak=kaynak)
        if gecmis and gecmis_destekli(yonetici.calistir):
            kw['gecmis'] = gecmis
        return yonetici.calistir(message, **kw)

    def _aktif_beyin(self) -> tuple[Optional[str], str]:
        """Secili beyni (saglayici, model) dondur; yoksa (None, '')."""
        try:
            import jarvis_beyin_kayit as _bk
            b = _bk.aktif_beyin() or {}
            if not b.get('etkin', True):
                return None, ''
            ad = str(b.get('saglayici') or '').strip().lower()
            model = str(b.get('model') or '').strip()
            if ad:
                return ad, model
        except Exception:
            pass
        return None, ''

    @staticmethod
    def _hata_kodu(tur: str) -> str:
        return {
            'anahtar': 'NO_KEY',
            'yetki': 'AUTH',
            'kota': 'RATE_LIMIT',
            'model': 'MODEL_NOT_FOUND',
            'zaman': 'TIMEOUT',
            'dns': 'NETWORK',
            'baglanti': 'NETWORK',
            'tls': 'TLS',
            'tls_zincir': 'TLS',
            'tls_suresi': 'TLS',
            'tls_sunucu_adi': 'TLS',
            'tls_ca_yok': 'TLS',
            'tls_baglanti': 'TLS',
            'tls_mudahale': 'TLS',
            'sunucu': 'HTTP_5XX',
            'online_bekle': 'NO_PROVIDER',
            'istek': 'PROVIDER_ERROR',
            'saglayici': 'PROVIDER_ERROR',
            'hata': 'PROVIDER_ERROR',
            'hepsi': 'PROVIDER_ERROR',
            'iptal': 'CANCELLED',
        }.get(str(tur or ''), 'PROVIDER_ERROR')

    @staticmethod
    def _hata_metni(kod: str) -> str:
        return {
            'NO_KEY': 'API anahtari yok veya cozulemedi.',
            'AUTH': 'Yetki reddedildi (401/403).',
            'RATE_LIMIT': 'Kota/hiz siniri.',
            'MODEL_NOT_FOUND': 'Model bulunamadi (404).',
            'TIMEOUT': 'Zaman asimi.',
            'NETWORK': 'Ag baglantisi kurulamadi.',
            'TLS': 'TLS/sertifika hatasi.',
            'HTTP_5XX': 'Saglayici sunucu hatasi.',
            'NO_PROVIDER': 'Saglayici yanit vermedi.',
            'CANCELLED': 'Istek iptal edildi.',
            'NO_ACTIVE_BRAIN': 'Aktif beyin tanimli degil.',
            'MODE_OFFLINE': 'ONLINE mod gerekli; bulut cagrisi yapilmadi.',
            'MODE_INVALID': 'Gecersiz baglanti modu.',
            'NOT_APPROVED': 'Bulut izni yok; istek aga gonderilmedi.',
            'OLLAMA_DOWN': 'Yerel Qwen sunucusu calismiyor veya model yuklu degil.',
            'OLLAMA_EMPTY': 'Yerel model bos yanit dondurdu.',
            'ROUTER_IMPORT': 'AI yonlendirici yuklenemedi.',
            'EMPTY_RESPONSE': 'Saglayici bos yanit dondurdu.',
            'NO_FREE_PROVIDER': 'Dogrulanmis ucretsiz saglayici kalmadi.',
            'FREE_CATALOG_UNAVAILABLE': 'OpenRouter ucretsiz katalogu dogrulanamadi.',
            'FREE_MODEL_UNVERIFIED': 'Ucretsiz dogrulanmamis model reddedildi.',
        }.get(str(kod or ''), 'Saglayici hatasi.')

    @classmethod
    def _saglayici_durumu(cls, kod: str, *, provider=None, model=None,
                          attempted=None, errors=None, mode=None) -> Dict[str, Any]:
        durum_tipleri = ('NO_KEY', 'MODE_OFFLINE', 'NO_ACTIVE_BRAIN',
                         'MODE_INVALID', 'NOT_APPROVED', 'NO_FREE_PROVIDER',
                         'FREE_CATALOG_UNAVAILABLE')
        return {
            'provider': provider,
            'model': model,
            'success': False,
            'response': None,
            'result_type': 'provider_status' if kod in durum_tipleri
                           else 'connection_error',
            'error': cls._hata_metni(kod),
            'error_code': kod,
            'attempted': list(attempted or []),
            'errors': list(errors or []),
            'mode': mode,
        }

    # --- Ana islem metodu ---

    def infer(self, message: str, *, mode: str = "online",
              yetki: Optional[Dict[str, Any]] = None,
              kaynak: Optional[str] = None,
              gecmis: Optional[list] = None) -> Dict[str, Any]:
        """
        Saglayiciya gercek istek gonder.

        mode: online, offline, auto
        gecmis: oturumun onceki turlari (role/content); ayni gecmis model
                rotasyonu sirasinda AYNEN korunur.
        FAZ 2.2A: online/auto icin gecerli tek kullanimlik yetki bileti
        ZORUNLUDUR; bilet burada (ag cagrisindan hemen once) tuketilir.
        Donen dict: {provider, model, success, result_type, response,
                     error, error_code, attempted, errors, mode}
        """
        mode = str(mode or '').strip().lower()

        # OFFLINE modunda: dogrudan yerel Ollama (bulut izni gerekmez)
        if mode == "offline":
            yerel = self.infer_local(message, gecmis=gecmis)
            yerel["mode"] = "offline"
            return yerel

        # ONLINE/AUTO: bulut kullanilacaksa son guvenlik kapisi.
        # Burada yalnizca erken kontrol; bilet gercek ag isteginden
        # hemen once (yonetici/`_try_providers` icinde) TUKETILIR.
        if mode in ("online", "auto") and not _bulut_yetki_gecerli(
                message, mode, yetki, kaynak, tuket=False):
            return self._saglayici_durumu(
                'NOT_APPROVED', attempted=[], errors=[], mode=mode)

        aktif_ad, aktif_model = self._aktif_beyin()
        yonetici = self._yonetici()

        # ONLINE: FAZ 2 ucretsiz coklu model zinciri.
        if mode == "online":
            if aktif_ad == "ollama":
                return self._saglayici_durumu(
                    'MODE_OFFLINE', provider=aktif_ad, model=aktif_model,
                    attempted=[], errors=[], mode=mode)
            if yonetici is not None:
                # FAZ 2.2B: bilet tuketimi ModelYonetici.calistir icinde,
                # ilk gercek saglayici isteginden hemen once yapilir.
                sonuc = self._yonetici_calistir(
                    yonetici, message, mode="online", yetki=yetki,
                    kaynak=kaynak, gecmis=gecmis)
                sonuc["mode"] = "online"
                return sonuc
            if not aktif_ad:
                return self._saglayici_durumu(
                    'NO_ACTIVE_BRAIN', attempted=[], errors=[], mode=mode)
            return self._try_providers(
                message, [aktif_ad], aktif_model, sadece=True,
                mode="online", yetki=yetki, kaynak=kaynak, gecmis=gecmis)

        # AUTO: once ucretsiz bulut zinciri, sonra yerel model.
        if mode == "auto":
            if yonetici is not None:
                cloud_result = self._yonetici_calistir(
                    yonetici, message, mode="auto", yetki=yetki,
                    kaynak=kaynak, gecmis=gecmis)
            elif aktif_ad != "ollama":
                cloud_result = self._try_providers(
                    message, [aktif_ad], aktif_model, sadece=True,
                    mode="auto", yetki=yetki, kaynak=kaynak, gecmis=gecmis)
            else:
                cloud_result = self._saglayici_durumu(
                    'MODE_OFFLINE', provider=aktif_ad, model=aktif_model,
                    attempted=[], errors=[], mode="auto")
            if cloud_result.get("success"):
                cloud_result["mode"] = "auto"
                return cloud_result
            if str(cloud_result.get("error_code") or '') == 'NOT_APPROVED':
                cloud_result["mode"] = "auto"
                return cloud_result
            onceki_attempted = cloud_result.get("attempted", [])
            onceki_errors = cloud_result.get("errors", [])
            yerel = self.infer_local(message, gecmis=gecmis)
            yerel["mode"] = "auto"
            yerel["attempted"] = list(onceki_attempted) + list(
                yerel.get("attempted", []))
            yerel["errors"] = list(onceki_errors) + list(
                yerel.get("errors", []))
            if not yerel.get("success"):
                yerel["error"] = (
                    "AUTO: Ucretsiz bulut saglayicilari ve yerel Ollama basarisiz"
                )
                yerel["result_type"] = "connection_error"
                yerel["error_code"] = yerel.get("error_code") or "PROVIDER_ERROR"
            return yerel

        return self._saglayici_durumu(
            'MODE_INVALID', attempted=[], errors=[], mode=mode)

    # --- Yerel Qwen API cagrisi ---

    def infer_local(self, message: str,
                    gecmis: Optional[list] = None) -> Dict[str, Any]:
        """Yerel Qwen sunucusuna ayni anda yalnizca tek istek gider; digerleri bekler."""
        with _YEREL_CIKARIM_KILIT:
            if gecmis and gecmis_destekli(self._infer_local_govde):
                return self._infer_local_govde(message, gecmis=gecmis)
            return self._infer_local_govde(message)

    def _infer_local_govde(self, message: str,
                           gecmis: Optional[list] = None) -> Dict[str, Any]:
        """Dogrudan yerel llama.cpp Qwen modeliyle gercek yanit al."""
        result: Dict[str, Any] = {
            "provider": "llama-cpp-local",
            "model": OLLAMA_MODEL,
            "success": False,
            "result_type": "connection_error",
            "response": None,
            "error": None,
            "error_code": None,
            "attempted": ["llama-cpp-local"],
            "errors": [],
            "mode": "local",
        }
        if not _ollama_var():
            result["error_code"] = "OLLAMA_DOWN"
            result["errors"] = [{"saglayici": "llama-cpp-local",
                                 "kod": "OLLAMA_DOWN", "http": None}]
            result["error"] = self._hata_metni("OLLAMA_DOWN")
            return result

        ozet, mesajlar = _gecmis_mesajlari(gecmis)
        sistem = _SISTEM_MESAJI
        if ozet:
            sistem = sistem + "\n\n" + "\n\n".join(ozet)
        govde = json.dumps({
            "model": OLLAMA_MODEL,
            "messages": [{"role": "system", "content": sistem}]
                        + mesajlar
                        + [{"role": "user", "content": message}],
            "stream": False,
            "options": {"temperature": 0.6},
        }).encode("utf-8")

        t0 = time.time()
        try:
            istek = urllib.request.Request(
                OLLAMA_URL,
                data=govde,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(
                istek, timeout=OLLAMA_ZAMAN_ASIMI
            ) as c:
                veri = json.loads(c.read().decode("utf-8", "ignore"))
        except Exception:
            _OLLAMA_CACHE["var"] = False
            _OLLAMA_CACHE["t"] = 0.0
            result["error_code"] = "OLLAMA_DOWN"
            result["errors"] = [{"saglayici": "llama-cpp-local",
                                 "kod": "OLLAMA_DOWN", "http": None}]
            result["error"] = self._hata_metni("OLLAMA_DOWN")
            return result

        # OpenAI uyumlu llama.cpp yanitindan yalnizca message.content alinir.
        # reasoning / thinking alanlari kullanici yaniti olarak ASLA kullanilmaz.
        choices = veri.get("choices") or []
        msg = (choices[0].get("message") or {}) if choices and isinstance(choices[0], dict) else {}
        icerik = _metni_temizle(str(msg.get("content") or ""))
        if not icerik:
            result["error_code"] = "OLLAMA_EMPTY"
            result["errors"] = [{"saglayici": "llama-cpp-local",
                                 "kod": "OLLAMA_EMPTY", "http": None}]
            result["error"] = self._hata_metni("OLLAMA_EMPTY")
            return result

        result["success"] = True
        result["result_type"] = "answer"
        result["response"] = icerik
        result["total_response_ms"] = int((time.time() - t0) * 1000)
        return result

    # --- Ic metot: bulut saglayicilarini sirayla dene ---

    def _mevcut_saglayicilar(self) -> set:
        """jarvis_yetenek zincirinde kullanilabilir bulut saglayicilari."""
        try:
            import jarvis_yetenek as _yt
            return {str(s[0]).lower() for s in _yt.ai_saglayicilar()}
        except Exception:
            return set()

    def _try_providers(
        self, message: str, order: list[str], model: Optional[str] = None,
        *, sadece: bool = False, mode: str = "online",
        yetki: Optional[Dict[str, Any]] = None,
        kaynak: Optional[str] = None,
        gecmis: Optional[list] = None
    ) -> Dict[str, Any]:
        """Secili saglayiciyi dene; durum metnini asla yanit sayma.

        FAZ 2.2A: bilet burada, router cagrisindan hemen once tuketilir.
        Dogrudan cagri veya gecersiz bilet FAIL-CLOSED'dir.
        """
        if not _bulut_yetki_gecerli(
                message, mode, yetki, kaynak, tuket=True):
            return self._saglayici_durumu(
                'NOT_APPROVED', model=model, attempted=[], errors=[],
                mode=mode)
        attempted: list[str] = []
        errors: list[Dict[str, Any]] = []
        try:
            import jarvis_ai_router as _R
        except Exception:
            return self._saglayici_durumu(
                'ROUTER_IMPORT', model=model, attempted=attempted,
                errors=errors, mode=mode)

        for provider in order:
            provider = str(provider or "").strip().lower()
            if not provider or provider in self.blocked:
                continue
            attempted.append(provider)
            try:
                sonuc = _R.sorgula(
                    message,
                    sistem=_SISTEM_MESAJI,
                    zaman=60,
                    max_tokens=1200,
                    sicaklik=0.6,
                    saglayici=provider,
                    model=(str(model or '').strip() or None),
                    sadece_saglayici=bool(sadece),
                    gecmis=gecmis,
                )
            except _R.RouterHatasi as e:
                kod = self._hata_kodu(getattr(e, 'tur', ''))
                errors.append({"saglayici": provider, "kod": kod,
                               "http": getattr(e, 'http_kod', None)})
                if sadece:
                    break
                continue
            except Exception:
                kod = "PROVIDER_ERROR"
                errors.append({"saglayici": provider, "kod": kod,
                               "http": None})
                if sadece:
                    break
                continue

            cevap = str((sonuc or {}).get('cevap') or '').strip()
            if not cevap:
                kod = "EMPTY_RESPONSE"
                errors.append({"saglayici": provider, "kod": kod,
                               "http": None})
                if sadece:
                    break
                continue
            return {
                "provider": (sonuc or {}).get('saglayici') or provider,
                "model": (sonuc or {}).get('model') or (model or None),
                "success": True,
                "result_type": "answer",
                "response": cevap,
                "error": None,
                "error_code": None,
                "attempted": attempted,
                "errors": errors,
                "mode": mode,
                "request_id": (sonuc or {}).get('gorev_id'),
                "total_response_ms": 0,
            }

        kod = errors[-1]["kod"] if errors else "NO_PROVIDER"
        return self._saglayici_durumu(
            kod,
            provider=(order[0] if order else None),
            model=model or None,
            attempted=attempted,
            errors=errors,
            mode=mode,
        )

    # --- Yardimcilar ---

    @staticmethod
    def is_blocked(provider: str) -> bool:
        """Saglayici engellendi mi?"""
        return provider.lower().strip() in BLOCKED_PROVIDERS

    @staticmethod
    def safe_provider(provider: str) -> bool:
        """Saglayici guvenli mi?"""
        return provider.lower().strip() in SAFE_PROVIDERS


# -------------------------------------------------------
# 4. TESTLER
# -------------------------------------------------------

if __name__ == "__main__":
    ce = CloudEngine()

    print("= CloudEngineV2 Gercel Testleri =")
    print(f"Sira: {ce.provider_order}")
    print(f"Engellenenler: {ce.blocked}")
    print(f"Ollama var: {_ollama_var()} (model: {OLLAMA_MODEL})")
    print()

    # Test 1: OFFLINE mod - gercek yerel Ollama
    print("--- Test 1: OFFLINE mod (yerel Ollama, qwen3:4b) ---")
    r = ce.infer("Merhaba JARVIS, nasilsin? Kisa cevap ver.", mode="offline")
    print(f"  provider={r['provider']}, success={r['success']}")
    if r["success"]:
        print(f"  Yanit: {r['response'][:120]}")
        print(f"  Sure: {r.get('total_response_ms', 0)} ms")
    else:
        print(f"  Hata: {r['error']}")

    # Test 2: AUTO mod - bulut yoksa yerel Ollama'ya gecis
    print("\n--- Test 2: AUTO mod ---")
    r = ce.infer("Bana kisa bir selam ver.", mode="auto")
    print(f"  provider={r['provider']}, success={r['success']}, attempted={r['attempted']}")
    if r["success"]:
        print(f"  Yanit: {r['response'][:120]}")

    # Test 3: Engellenen provider kontrolu
    print("\n--- Test 3: Engelli/guvenli provider ---")
    print(f"  OpenAI engellendi: {ce.is_blocked('openai')}")
    print(f"  Gemini guvenli: {ce.safe_provider('gemini')}")
