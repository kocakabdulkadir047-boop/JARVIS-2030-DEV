#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""JARVIS ucretsiz coklu model yoneticisi (FAZ 2).

Oncelik:
  1) OpenRouter (dinamik ucretsiz katalog)
  2) Gemini
  3) Z.AI GLM-4-Flash
  4) Groq

Kurallar:
  * Yalnizca ucretsiz oldugu dogrulanmis modeller plana girer.
  * Ucretli modele otomatik gecis YOKTUR.
  * 429/kota durumunda yalnizca siradaki ucretsiz saglayici denenir.
  * Ayni mesaj icin eszamanli yinelenen istek tekillestirilir.
  * Kullanilan saglayici/model ve gercek hata kodu kayda gecer.
  * API anahtari degeri okunmaz/yazilmaz; yalnizca var/yok bilgisi.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

SAGLAYICI_SIRASI = ('openrouter', 'gemini', 'zai_glm', 'groq')

SAGLAYICI_ETIKET = {
    'openrouter': 'OpenRouter',
    'gemini': 'Gemini',
    'zai_glm': 'Z.AI GLM',
    'groq': 'Groq',
}

MODELLER = {
    'gemini': ('gemini-3.8-flash', 'gemini-3.6-flash',
               'gemini-3.5-flash-lite'),
    'zai_glm': ('glm-4-flash', 'glm-4-air'),
    'groq': ('llama-3.3-70b-versatile', 'llama-3.1-8b-instant'),
}

#: Genel sohbet disi (gomme/siralama/guvenlik/ses) model kimligi isaretleri.
SOHBET_DISI_ISARET = ('embed', 'rerank', 'moderation', 'guard', 'safety',
                      'tts', 'whisper', 'transcribe', 'ocr')

#: Hesap kotasi 429'unda sifirlama zamani okunamazsa uygulanacak bekleme.
KOTA_BILINMEYEN_BEKLEME_SN = 3600.0

HATA_METIN = {
    'NO_KEY': 'API anahtari yok veya cozulemedi.',
    'AUTH': 'Yetki reddedildi (401/403).',
    'RATE_LIMIT': 'Kota/hiz siniri (429).',
    'MODEL_NOT_FOUND': 'Model bulunamadi (404).',
    'TIMEOUT': 'Istek zaman asimina ugradi.',
    'NETWORK': 'Ag/DNS baglantisi kurulamadi.',
    'TLS': 'TLS/sertifika dogrulama hatasi.',
    'HTTP_5XX': 'Saglayici sunucu hatasi (5xx).',
    'NO_PROVIDER': 'Saglayici yanit vermedi.',
    'EMPTY_RESPONSE': 'Saglayici bos yanit dondurdu.',
    'PROVIDER_ERROR': 'Saglayici hatasi; yanit alinamadi.',
    'NO_FREE_PROVIDER': 'Dogrulanmis ucretsiz saglayici kalmadi.',
    'FREE_CATALOG_UNAVAILABLE': 'OpenRouter ucretsiz katalogu dogrulanamadi.',
    'FREE_MODEL_UNVERIFIED': 'Ucretsiz oldugu dogrulanmamis model reddedildi.',
    'MODEL_CAPABILITY': 'Model genel sohbet icin uygun degil.',
    'PAID_MODEL_REJECTED': 'Ucretli model reddedildi.',
    'CANCELLED': 'Istek iptal edildi.',
    'EMPTY_MESSAGE': 'Soru metni bos.',
}

_KILIT = threading.Lock()
_YONETICI: Optional['ModelYonetici'] = None


def _kok() -> str:
    import sys
    try:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(os.path.abspath(sys.executable))
    except Exception:
        pass
    return os.path.dirname(os.path.abspath(__file__))


def _pytest_altinda() -> bool:
    import sys
    return 'pytest' in sys.modules


def _gecmis_destekli(fn) -> bool:
    """Router `sorgula` cagrisi gecmis parametresini kabul ediyor mu?"""
    try:
        parametreler = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    if 'gecmis' in parametreler:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD
               for p in parametreler.values())


def _kod(tur: str) -> str:
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


def _bulut_modu() -> str:
    """Gercek baglanti modu; okunamazsa FAIL-CLOSED: offline."""
    try:
        import jarvis_ai_router as _R
        return str(_R.mod_oku() or '').strip().lower() or 'offline'
    except Exception:
        return 'offline'


def _bulut_acik_mi() -> bool:
    """cloud_enabled ayari; okunamazsa FAIL-CLOSED: False."""
    try:
        import jarvis_ai_router as _R
        return bool(_R.ayarlar().get('cloud_enabled', True))
    except Exception:
        return False


def _merkezi_yetki(bilet, mesaj: str, mod: str, kaynak,
                   tuket: bool) -> bool:
    """Merkezi HMAC biletini dogrula (broker disi cagri FAIL-CLOSED)."""
    try:
        import jarvis_chat_v2_entegrasyon as _E
        return bool(_E.yetki_dogrula(
            bilet, mesaj=mesaj, mod=mod, kaynak=kaynak, tuket=tuket))
    except Exception:
        return False


class ModelYonetici:
    """Ucretsiz saglayici/model planlayici ve deneme yoneticisi."""

    def __init__(self, *, router=None, katalog=None,
                 usage_path: Optional[str] = None,
                 kota_path: Optional[str] = None,
                 max_openrouter: int = 5):
        self._router_override = router
        self._katalog_override = katalog
        self._router_mod = None
        self._katalog_mod = None
        self.usage_path = usage_path or os.path.join(
            _kok(), 'jarvis_ai_faiz1', 'model_kullanim.jsonl')
        acik_kota_yolu = kota_path is not None
        if kota_path is None:
            kota_path = os.path.join(
                os.path.dirname(self.usage_path) or _kok(),
                'kota_durumu.json')
        self.kota_path = kota_path
        #: Test kosulari uretim kota dosyasini okumaz/yazmaz; acikca
        #: verilen kota_path her zaman kalicidir.
        self._kota_kalici = bool(acik_kota_yolu) or not _pytest_altinda()
        self.max_openrouter = max(1, int(max_openrouter or 5))
        self._kota: Dict[str, float] = {}
        #: (saglayici, model) -> kota bitis zaman damgasi
        self._model_kota: Dict[str, float] = {}
        #: Hesap/free-tier gunluk kotasi nedeniyle kapatilan saglayicilar
        self._hesap_kota: set = set()
        self._or_imlec = 0
        self._son_or_kota: Dict[str, Any] = {}
        self._son_kod: Dict[str, str] = {}
        self._son_http: Dict[str, Optional[int]] = {}
        self._son_deneme: Dict[str, int] = {}
        self._son_saglayici: Optional[str] = None
        self._son_model: Optional[str] = None
        self._son_basarili: float = 0.0
        self._son_hata: Optional[str] = None
        self._ucus: Dict[str, Dict[str, Any]] = {}
        self._kota_yukle()

    # --- Bagimliliklar -------------------------------------------------
    def _router(self):
        if self._router_mod is None:
            self._router_mod = self._router_override
            if self._router_mod is None:
                import jarvis_ai_router as _R
                self._router_mod = _R
        return self._router_mod

    def _katalog(self):
        if self._katalog_mod is None:
            self._katalog_mod = self._katalog_override
            if self._katalog_mod is None:
                import jarvis_ucretsiz_katalog as _K
                self._katalog_mod = _K
        return self._katalog_mod

    def _tanimlar(self) -> Dict[str, Dict[str, Any]]:
        try:
            return {str(t.get('name') or '').strip().lower(): dict(t)
                    for t in self._router().saglayici_tanimlari()}
        except Exception:
            return {}

    def _anahtar_var(self, saglayici: str, tanimlar=None) -> bool:
        t = (tanimlar or {}).get(saglayici)
        if not t:
            return False
        try:
            return bool(self._router().anahtar_bul(t))
        except Exception:
            return False

    def _model_ucretsiz(self, saglayici: str, model: str) -> bool:
        try:
            return bool(self._router().model_izinli_mi(saglayici, model))
        except Exception:
            return False

    def _kota_uygun(self, saglayici: str) -> bool:
        bitis = float(self._kota.get(saglayici) or 0.0)
        return time.time() >= bitis

    @staticmethod
    def _model_anahtari(saglayici: str, model: str) -> str:
        return '%s|%s' % (str(saglayici or '').strip().lower(),
                          str(model or '').strip())

    def _model_kota_uygun(self, saglayici: str, model: str) -> bool:
        bitis = float(self._model_kota.get(
            self._model_anahtari(saglayici, model)) or 0.0)
        return time.time() >= bitis

    def _kota_yukle(self) -> None:
        """Yalnizca zaman damgalari/sayaclardan olusan kota durumunu oku."""
        if not self._kota_kalici:
            return
        try:
            with open(self.kota_path, 'r', encoding='utf-8') as f:
                veri = json.load(f)
        except Exception:
            return
        if not isinstance(veri, dict):
            return
        simdi = time.time()
        for ad, bitis in (veri.get('kota') or {}).items():
            try:
                b = float(bitis)
            except (TypeError, ValueError):
                continue
            if simdi < b <= simdi + 7.0 * 86400.0:
                self._kota[str(ad)] = b
        for anahtar, bitis in (veri.get('model_kota') or {}).items():
            try:
                b = float(bitis)
            except (TypeError, ValueError):
                continue
            if simdi < b <= simdi + 7.0 * 86400.0:
                self._model_kota[str(anahtar)] = b
        for ad in (veri.get('hesap_kota') or []):
            ad = str(ad or '').strip().lower()
            if ad and float(self._kota.get(ad) or 0.0) > simdi:
                self._hesap_kota.add(ad)
        try:
            self._or_imlec = int(veri.get('or_imlec') or 0)
        except (TypeError, ValueError):
            self._or_imlec = 0

    def _kota_kaydet(self) -> None:
        """Kota durumunu atomik yaz; gizli veri/sohbet icerigi YOK."""
        if not self._kota_kalici:
            return
        simdi = time.time()
        veri = {
            'surum': 1,
            'guncelleme': int(simdi),
            'kota': {k: float(v) for k, v in self._kota.items()
                     if float(v) > simdi},
            'model_kota': {k: float(v) for k, v in self._model_kota.items()
                           if float(v) > simdi},
            'hesap_kota': sorted(
                ad for ad in self._hesap_kota
                if float(self._kota.get(ad) or 0.0) > simdi),
            'or_imlec': int(self._or_imlec),
        }
        gecici = self.kota_path + '.tmp'
        try:
            klasor = os.path.dirname(self.kota_path)
            if klasor and not os.path.isdir(klasor):
                os.makedirs(klasor, exist_ok=True)
            with open(gecici, 'w', encoding='utf-8') as f:
                json.dump(veri, f, ensure_ascii=False, sort_keys=True)
            os.replace(gecici, self.kota_path)
        except Exception:
            try:
                if os.path.exists(gecici):
                    os.remove(gecici)
            except Exception:
                pass

    def _kota_isle(self, saglayici: str, retry_after=None) -> None:
        try:
            bekleme = float(retry_after or 20.0)
        except Exception:
            bekleme = 20.0
        self._kota[saglayici] = time.time() + max(5.0, min(bekleme, 120.0))
        self._hesap_kota.discard(saglayici)
        self._kota_kaydet()

    def _kota_hesap_isle(self, saglayici: str, hata) -> None:
        """Hesap/free-tier 429: saglayiciyi sifirlanma zamanina kadar kapat."""
        simdi = time.time()
        bitis = getattr(hata, 'kota_sifirlama_ts', None)
        try:
            bitis = float(bitis)
        except (TypeError, ValueError):
            bitis = 0.0
        if not (simdi + 5.0 <= bitis <= simdi + 7.0 * 86400.0):
            bitis = simdi + KOTA_BILINMEYEN_BEKLEME_SN
        self._kota[saglayici] = bitis
        self._hesap_kota.add(saglayici)
        self._son_or_kota = {
            'kota_hesap': True,
            'kota_bitis': bitis,
            'kota_kalan': getattr(hata, 'kota_kalan', None),
            'kota_sinir': getattr(hata, 'kota_sinir', None),
            'kota_kaynak': str(getattr(hata, 'kota_kaynak', '') or ''),
        }
        self._kota_kaydet()

    def _model_kota_isle(self, saglayici: str, model: str, hata) -> None:
        """Model bazli 429: yalnizca o modeli kisa sure kapat."""
        simdi = time.time()
        bekleme = getattr(hata, 'retry_after', None) or 30.0
        try:
            bekleme = float(bekleme)
        except (TypeError, ValueError):
            bekleme = 30.0
        bekleme = max(5.0, min(bekleme, 600.0))
        self._model_kota[self._model_anahtari(saglayici, model)] = \
            simdi + bekleme
        self._kota_kaydet()

    def _kota_temizle(self, saglayici: str, model: str) -> None:
        degisti = self._kota.pop(saglayici, None) is not None
        if saglayici in self._hesap_kota:
            self._hesap_kota.discard(saglayici)
            degisti = True
        if self._model_kota.pop(
                self._model_anahtari(saglayici, model), None) is not None:
            degisti = True
        if degisti:
            self._kota_kaydet()

    @staticmethod
    def _saat_metni(ts) -> str:
        try:
            t = float(ts)
            if t <= 0:
                return ''
            if time.strftime('%Y-%m-%d', time.localtime(t)) == \
                    time.strftime('%Y-%m-%d', time.localtime()):
                return time.strftime('%H:%M', time.localtime(t))
            return time.strftime('%d.%m %H:%M', time.localtime(t))
        except Exception:
            return ''

    # --- Plan ----------------------------------------------------------
    def plan(self, *, allow_network: bool = True
             ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """(adaylar, rapor) dondur. Yalnizca ucretsiz dogrulanmis modeller."""
        tanimlar = self._tanimlar()
        adaylar: List[Dict[str, Any]] = []
        rapor: List[Dict[str, Any]] = []
        R = self._router()

        for ad in SAGLAYICI_SIRASI:
            t = tanimlar.get(ad)
            if not t or not t.get('enabled'):
                rapor.append({'saglayici': ad, 'model': None,
                              'kod': 'PROVIDER_DISABLED', 'http': None,
                              'denendi': False})
                continue
            try:
                if not R.izinli_mi(ad):
                    rapor.append({'saglayici': ad, 'model': None,
                                  'kod': 'PROVIDER_DISABLED', 'http': None,
                                  'denendi': False})
                    continue
            except Exception:
                continue
            if not self._kota_uygun(ad):
                rapor.append({'saglayici': ad, 'model': None,
                              'kod': 'RATE_LIMIT', 'http': 429,
                              'denendi': False})
                continue
            if not self._anahtar_var(ad, tanimlar):
                rapor.append({'saglayici': ad, 'model': None,
                              'kod': 'NO_KEY', 'http': None,
                              'denendi': False})
                continue

            if ad == 'openrouter':
                kd = self._openrouter_katalog_tam(
                    allow_network=allow_network)
                if not kd.get('ok'):
                    rapor.append({'saglayici': ad, 'model': None,
                                  'kod': ('FREE_CATALOG_UNAVAILABLE'
                                          if kd.get('hata') else 'NO_FREE_MODEL'),
                                  'http': None, 'denendi': False})
                    continue
                modeller = [m for m in (kd.get('modeller') or [])
                            if isinstance(m, dict)]
                tercih = self._openrouter_tercihi(t)
                son = (str(self._son_model or '').strip()
                       if str(self._son_saglayici or '') == ad else '')
                uygun: List[Dict[str, Any]] = []
                soguk = 0
                yeteneksiz = 0
                for m in modeller:
                    kimlik = str(m.get('id') or '').strip()
                    if not kimlik or not self._model_ucretsiz(ad, kimlik):
                        continue
                    if not self._model_sohbet_uygun(kimlik, m):
                        yeteneksiz += 1
                        rapor.append({'saglayici': ad, 'model': kimlik,
                                      'kod': 'MODEL_CAPABILITY',
                                      'http': None, 'denendi': False})
                        continue
                    if not self._model_kota_uygun(ad, kimlik):
                        soguk += 1
                        continue
                    uygun.append(m)
                uygun.sort(key=lambda m: (
                    0 if tercih and str(m.get('id') or '').strip().lower()
                    == tercih.lower() else 1,
                    0 if son and str(m.get('id') or '').strip() == son else 1,
                    -int(m.get('created') or 0),
                    str(m.get('id') or '')))
                if uygun and not tercih and not son:
                    i = self._or_imlec % len(uygun)
                    uygun = uygun[i:] + uygun[:i]
                uygun = uygun[:self.max_openrouter]
                for m in uygun:
                    adaylar.append({'saglayici': ad,
                                    'model': str(m.get('id') or '').strip(),
                                    'ucretsiz': True,
                                    'kaynak': 'openrouter-katalog'})
                if not uygun:
                    rapor.append({'saglayici': ad, 'model': None,
                                  'kod': ('RATE_LIMIT' if soguk
                                          else 'NO_FREE_MODEL'),
                                  'http': 429 if soguk else None,
                                  'denendi': False})
                continue

            modeller = list(MODELLER.get(ad) or ())
            tercih = str(t.get('model') or '').strip()
            if tercih and tercih not in modeller:
                modeller.insert(0, tercih)
            bulundu = False
            for m in modeller:
                if not self._model_ucretsiz(ad, m):
                    rapor.append({'saglayici': ad, 'model': m,
                                  'kod': 'FREE_MODEL_UNVERIFIED',
                                  'http': None, 'denendi': False})
                    continue
                adaylar.append({'saglayici': ad, 'model': m,
                                'ucretsiz': True, 'kaynak': 'saglayici-politikasi'})
                bulundu = True
            if not bulundu:
                rapor.append({'saglayici': ad, 'model': None,
                              'kod': 'NO_FREE_MODEL', 'http': None,
                              'denendi': False})
        return (adaylar, rapor)

    def _openrouter_katalog(self, *, allow_network: bool) -> Dict[str, Any]:
        K = self._katalog()
        try:
            if allow_network:
                return K.katalog_getir()
            d = K.katalog_durumu()
            modeller = list(d.get('modeller') or [])
            ok = bool(d.get('dogrulanmis')) and not d.get('hata')
            return {'ok': ok, 'modeller': modeller,
                    'hata': d.get('hata'), 'bayat': True}
        except Exception as e:
            return {'ok': False, 'modeller': [], 'hata': type(e).__name__}

    def _openrouter_katalog_tam(self, *, allow_network: bool
                                ) -> Dict[str, Any]:
        """Katalogu tam listeyle dondur (UI dilimi degil, tum dogrulanmis)."""
        kd = self._openrouter_katalog(allow_network=allow_network)
        if not kd.get('ok'):
            return kd
        try:
            d = self._katalog().katalog_durumu() or {}
            tam = [m for m in (d.get('modeller') or [])
                   if isinstance(m, dict)]
            if tam and not d.get('hata'):
                kd = dict(kd)
                kd['modeller'] = tam
        except Exception:
            pass
        return kd

    @staticmethod
    def _model_sohbet_uygun(kimlik: str, kayit: Dict[str, Any]) -> bool:
        """Genel metin sohbeti icin yetenek dogrulamasi.

        Gomme/siralama/guvenlik/ses gibi ozel amacli modeller ve metin
        girdisi/ciktisi olmayan modeller genel sohbet listesine alinmaz.
        Yetenek bilgisi yoksa mevcut katı fiyat/isim dogrulamasi yeterlidir.
        """
        kid = str(kimlik or '').lower()
        if any(x in kid for x in SOHBET_DISI_ISARET):
            return False
        girdi = kayit.get('girdi_modaliteleri')
        cikti = kayit.get('cikti_modaliteleri')
        if not isinstance(girdi, list) or not isinstance(cikti, list):
            mimari = kayit.get('architecture')
            if isinstance(mimari, dict):
                g = mimari.get('input_modalities') or \
                    mimari.get('input_modality')
                c = mimari.get('output_modalities') or \
                    mimari.get('output_modality')
                girdi = [g] if isinstance(g, str) else g
                cikti = [c] if isinstance(c, str) else c
        def _liste(x):
            if isinstance(x, str):
                x = [x]
            if not isinstance(x, list):
                return []
            return [str(v).strip().lower() for v in x if str(v).strip()]
        g = _liste(girdi)
        c = _liste(cikti)
        if c and 'text' not in c:
            return False
        if g and 'text' not in g:
            return False
        return True

    def _openrouter_tercihi(self, tanim: Dict[str, Any]) -> str:
        """Kullanici model tercihi (ai_routing.json / ai_model_openrouter).

        Yalnizca ':free' sonekli tercih one alinir; katalog dogrulamasi ve
        `_model_ucretsiz` filtresi aynen uygulanir. Gecersiz tercih plani
        degistirmez (fail-safe).
        """
        try:
            R = self._router()
            mt = R.model_tercihi_kontrol(tanim, R.ayarlar())
            t = str(mt.get('kullanilan') or '').strip()
        except Exception:
            t = str(tanim.get('model') or '').strip()
        return t if t.lower().endswith(':free') else ''

    def onay_bilgisi(self) -> Tuple[str, str]:
        """Onay penceresi icin gercek ana rota + ucretsiz yedekler."""
        ad = 'OpenRouter (ana)'
        model = 'ucretsiz model - katalog dogrulanacak'
        yedek = 'dogrulanmis ucretsiz katalog'
        try:
            d = self._katalog().katalog_durumu()
            modeller = []
            for m in (d.get('modeller') or []):
                if not isinstance(m, dict):
                    continue
                kimlik = str(m.get('id') or '').strip()
                if not kimlik or not self._model_ucretsiz('openrouter', kimlik):
                    continue
                if not self._model_sohbet_uygun(kimlik, m):
                    continue
                modeller.append(kimlik)
            if modeller:
                model = modeller[0]
                if len(modeller) > 1:
                    yedek = ', '.join(modeller[1:4])
        except Exception:
            pass
        return (ad, '%s | yedek: %s' % (model, yedek))

    # --- Calistirma ----------------------------------------------------
    def calistir(self, message: str, *, sistem=None, zaman=60,
                 max_tokens=1200, sicaklik=0.6,
                 mode: str = 'online', yetki=None,
                 kaynak=None, gecmis=None) -> Dict[str, Any]:
        metin = str(message or '').strip()
        if not metin:
            return self._hata('EMPTY_MESSAGE', mode=mode)
        mod = str(mode or '').strip().lower()
        if mod not in ('online', 'auto'):
            return self._hata('MODE_INVALID', mode=mode)
        # FAZ 2.2B: bulut yolu yalnizca gercek mod musait + gecerli
        # tek kullanimlik bilet varken calisir. Bilet burada TUKETILMEZ;
        # ag cagrisindan hemen once `_dene` icinde tuketilir.
        if _bulut_modu() == 'offline':
            return self._hata('MODE_OFFLINE', mode=mode)
        if not _bulut_acik_mi():
            return self._hata('PROVIDER_DISABLED', mode=mode)
        if not _merkezi_yetki(yetki, metin, mod, kaynak, tuket=False):
            return self._hata('NOT_APPROVED', mode=mode)
        # Ucus anahtari gecmis imzasini da icerir: ayni metin farkli
        # oturum baglaminda birbirinin yanitini kapmaz.
        imza = repr(gecmis) if gecmis else ''
        anahtar = hashlib.sha256(
            ('%s|%s|%s' % (mode, metin, imza)).encode(
                'utf-8', 'replace')).hexdigest()
        rec, sahip = self._ucus_al(anahtar)
        if not sahip:
            try:
                if rec['olay'].wait(120.0) and rec.get('sonuc') is not None:
                    return dict(rec['sonuc'])
            except Exception:
                pass
            rec, sahip = self._ucus_al(anahtar + '#yeni')
        try:
            sonuc = self._dene(metin, sistem=sistem, zaman=zaman,
                               max_tokens=max_tokens, sicaklik=sicaklik,
                               mode=mode, yetki=yetki, kaynak=kaynak,
                               gecmis=gecmis)
            rec['sonuc'] = sonuc
            return sonuc
        except Exception as e:
            sonuc = self._hata('PROVIDER_ERROR', mode=mode,
                               errors=[{'saglayici': None, 'model': None,
                                        'kod': 'PROVIDER_ERROR',
                                        'http': None, 'denendi': False}])
            sonuc['error'] = '%s (%s)' % (
                HATA_METIN['PROVIDER_ERROR'], type(e).__name__)
            rec['hata'] = type(e).__name__
            return sonuc
        finally:
            try:
                rec['olay'].set()
            except Exception:
                pass
            self._ucus_temizle()

    def _dene(self, metin: str, *, sistem=None, zaman=60,
              max_tokens=1200, sicaklik=0.6,
              mode: str = 'online', yetki=None,
              kaynak=None, gecmis=None) -> Dict[str, Any]:
        R = self._router()
        plan, rapor = self.plan(allow_network=True)
        # FAZ 2.2B: ilk gercek saglayici isteginden hemen once bilet
        # tuketilir. Gecersiz/tekrar kullanilmis bilet -> ag YOK.
        if not _merkezi_yetki(yetki, metin, str(mode).strip().lower(),
                              kaynak, tuket=True):
            return self._hata('NOT_APPROVED', mode=mode)
        attempted: List[str] = []
        errors: List[Dict[str, Any]] = list(rapor)
        atlanan: set = set()
        t0 = time.time()

        for aday in plan:
            ad = str(aday.get('saglayici') or '').strip().lower()
            model = str(aday.get('model') or '').strip()
            if not ad or not model or ad in atlanan:
                continue
            attempted.append(ad)
            self._son_deneme[ad] = int(time.time())
            try:
                cagri = dict(sistem=sistem, zaman=zaman,
                             max_tokens=max_tokens, sicaklik=sicaklik,
                             saglayici=ad, model=model,
                             sadece_saglayici=True)
                if gecmis and _gecmis_destekli(R.sorgula):
                    cagri['gecmis'] = gecmis
                sonuc = R.sorgula(metin, **cagri)
            except R.RouterHatasi as e:
                kod = _kod(getattr(e, 'tur', ''))
                http = getattr(e, 'http_kod', None)
                satir = {'saglayici': ad, 'model': model, 'kod': kod,
                         'http': http, 'denendi': True}
                kes = False
                if kod == 'RATE_LIMIT':
                    model_bazli = bool(getattr(e, 'model_bazli', False))
                    # Hesap kotasi YALNIZCA kanitla (kota_hesap/limit/kalan/
                    # sifirlanma/kaynak) kapatilir; kanitsiz sahte/opak 429
                    # eski davranista kalir (saglayiciyi atla, sirada devam).
                    kanit = bool(
                        getattr(e, 'kota_hesap', False)
                        or str(getattr(e, 'kota_kaynak', '') or '')
                        or getattr(e, 'kota_sinir', None) is not None
                        or getattr(e, 'kota_kalan', None) is not None
                        or getattr(e, 'kota_sifirlama_ts', None))
                    hesap_kota = bool(getattr(e, 'kota_hesap', False)) or (
                        ad == 'openrouter' and not model_bazli and kanit)
                    satir['kota_kalan'] = getattr(e, 'kota_kalan', None)
                    satir['kota_sinir'] = getattr(e, 'kota_sinir', None)
                    satir['kota_kaynak'] = str(
                        getattr(e, 'kota_kaynak', '') or '')
                    satir['kota_hesap'] = hesap_kota
                    sifirlanma = getattr(e, 'kota_sifirlama_ts', None)
                    if sifirlanma:
                        satir['sifirlanma'] = sifirlanma
                    if hesap_kota:
                        # Hesap/free-tier gunluk 429: OpenRouter istekleri
                        # DERHAL durur, sifirlanma zamanina kadar kapali.
                        self._kota_hesap_isle(ad, e)
                        atlanan.add(ad)
                        kes = True
                    elif ad == 'openrouter' and model_bazli:
                        # Model bazli 429: yalnizca o model sogur; ayni
                        # model tekrar denenmez, siradaki :free model gelir.
                        self._model_kota_isle(ad, model, e)
                    else:
                        self._kota_isle(
                            ad, getattr(e, 'retry_after', None))
                        atlanan.add(ad)
                errors.append(satir)
                self._son_kod[ad] = kod
                self._son_http[ad] = http
                self._son_hata = '%s/%s: %s' % (ad, model,
                                                 HATA_METIN.get(kod, kod))
                self._kayit(ad, model, False, kod, http, t0, mode)
                if kod == 'CANCELLED':
                    return self._hata('CANCELLED', provider=ad, model=model,
                                      attempted=attempted, errors=errors,
                                      mode=mode)
                if kes:
                    break
                continue
            except Exception as e:
                errors.append({'saglayici': ad, 'model': model,
                               'kod': 'PROVIDER_ERROR', 'http': None,
                               'denendi': True})
                self._son_kod[ad] = 'PROVIDER_ERROR'
                self._son_hata = '%s/%s: %s' % (ad, model, type(e).__name__)
                self._kayit(ad, model, False, 'PROVIDER_ERROR', None, t0, mode)
                continue

            cevap = str((sonuc or {}).get('cevap') or '').strip()
            if not cevap:
                errors.append({'saglayici': ad, 'model': model,
                               'kod': 'EMPTY_RESPONSE', 'http': None,
                               'denendi': True})
                self._son_kod[ad] = 'EMPTY_RESPONSE'
                self._son_hata = '%s/%s: bos yanit' % (ad, model)
                self._kayit(ad, model, False, 'EMPTY_RESPONSE', None, t0, mode)
                continue

            self._son_saglayici = str((sonuc or {}).get('saglayici') or ad)
            self._son_model = str((sonuc or {}).get('model') or model)
            self._son_basarili = time.time()
            self._son_hata = None
            self._son_kod[ad] = ''
            self._son_http[ad] = None
            self._kota_temizle(ad, self._son_model)
            if ad == 'openrouter':
                # Basarili model bir sonraki mesajda onde baslar; boylece
                # ayni modele kilitlenme olmaz, rotasyon surer.
                self._or_imlec = (self._or_imlec + 1) % 1000000
                self._son_or_kota = {}
                self._kota_kaydet()
            self._kayit(ad, model, True, None, None, t0, mode)
            return {
                'provider': self._son_saglayici,
                'model': self._son_model,
                'success': True,
                'result_type': 'answer',
                'response': cevap,
                'error': None,
                'error_code': None,
                'attempted': attempted,
                'errors': errors,
                'mode': mode,
                'free_verified': True,
                'request_id': (sonuc or {}).get('gorev_id'),
                'total_response_ms': int((time.time() - t0) * 1000),
            }

        kod = self._sonuc_kodu(plan, errors)
        kota = None
        if kod == 'RATE_LIMIT':
            for satir in reversed(errors):
                if satir.get('kod') == 'RATE_LIMIT':
                    kota = {
                        'kota_saglayici': satir.get('saglayici'),
                        'kota_hesap': bool(satir.get('kota_hesap')),
                        'kota_kalan': satir.get('kota_kalan'),
                        'kota_sinir': satir.get('kota_sinir'),
                        'sifirlanma': satir.get('sifirlanma'),
                        'kota_kaynak': satir.get('kota_kaynak', ''),
                    }
                    break
        return self._hata(kod, attempted=attempted, errors=errors,
                          mode=mode, kota=kota)

    def _sonuc_kodu(self, plan: List[Dict[str, Any]],
                    errors: List[Dict[str, Any]]) -> str:
        denendi = [e for e in errors if e.get('denendi')]
        kodlar = [str(e.get('kod') or '') for e in denendi]
        if kodlar:
            if 'RATE_LIMIT' in kodlar:
                return 'RATE_LIMIT'
            son = kodlar[-1]
            if son:
                return son
        if plan:
            return 'NO_PROVIDER'
        if errors and all(e.get('kod') == 'NO_KEY' for e in errors):
            return 'NO_KEY'
        if any(e.get('kod') == 'FREE_CATALOG_UNAVAILABLE' for e in errors):
            return 'FREE_CATALOG_UNAVAILABLE'
        return 'NO_FREE_PROVIDER'

    def _hata(self, kod: str, *, provider=None, model=None,
              attempted=None, errors=None,
              mode: str = 'online', kota=None) -> Dict[str, Any]:
        sonuc = {
            'provider': provider,
            'model': model,
            'success': False,
            'result_type': 'provider_status' if kod in
                           ('NO_KEY', 'NO_FREE_PROVIDER',
                            'FREE_CATALOG_UNAVAILABLE',
                            'MODE_OFFLINE', 'EMPTY_MESSAGE')
                           else 'connection_error',
            'response': None,
            'error': HATA_METIN.get(kod, 'Saglayici hatasi.'),
            'error_code': kod,
            'attempted': list(attempted or []),
            'errors': list(errors or []),
            'mode': mode,
            'free_verified': False,
            'request_id': None,
            'total_response_ms': 0,
        }
        if kota:
            sonuc.update(kota)
        return sonuc

    # --- Tekilleştirme / kayit ----------------------------------------
    def _ucus_al(self, anahtar: str):
        with _KILIT:
            simdi = time.time()
            for k, rec in list(self._ucus.items()):
                if rec['olay'].is_set() or (simdi - rec['baslangic']) > 180.0:
                    self._ucus.pop(k, None)
            rec = self._ucus.get(anahtar)
            if rec is not None and not rec['olay'].is_set():
                return rec, False
            rec = {'olay': threading.Event(), 'sonuc': None,
                   'hata': None, 'baslangic': simdi}
            self._ucus[anahtar] = rec
            return rec, True

    def _ucus_temizle(self) -> None:
        simdi = time.time()
        with _KILIT:
            for k, rec in list(self._ucus.items()):
                if (rec['olay'].is_set()
                        and (simdi - rec['baslangic']) > 120.0) or \
                        (simdi - rec['baslangic']) > 300.0:
                    self._ucus.pop(k, None)

    def _kayit(self, saglayici: str, model: str, basarili: bool,
               kod: Optional[str], http: Optional[int], t0: float,
               mode: str) -> None:
        satir = {
            'ts': int(time.time()),
            'saglayici': saglayici,
            'model': model,
            'basarili': bool(basarili),
            'kod': kod,
            'http': http,
            'sure_ms': int((time.time() - t0) * 1000),
            'mod': mode,
        }
        try:
            klasor = os.path.dirname(self.usage_path)
            if klasor and not os.path.isdir(klasor):
                os.makedirs(klasor, exist_ok=True)
            with _KILIT:
                with open(self.usage_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(satir, ensure_ascii=False) + '\n')
        except Exception:
            pass

    # --- Durum ---------------------------------------------------------
    def durum(self) -> Dict[str, Any]:
        tanimlar = self._tanimlar()
        saglayicilar = {}
        for ad in SAGLAYICI_SIRASI:
            saglayicilar[ad] = {
                'anahtar_var': self._anahtar_var(ad, tanimlar),
                'kota_bitis': float(self._kota.get(ad) or 0.0),
                'son_kod': self._son_kod.get(ad),
                'son_http': self._son_http.get(ad),
                'son_deneme': self._son_deneme.get(ad),
            }
        try:
            katalog = self._katalog().katalog_durumu()
        except Exception:
            katalog = {'hata': 'KATALOG_YOK', 'modeller': []}
        return {
            'saglayici_sirasi': list(SAGLAYICI_SIRASI),
            'katalog': katalog,
            'saglayicilar': saglayicilar,
            'son_saglayici': self._son_saglayici,
            'son_model': self._son_model,
            'son_basarili': self._son_basarili,
            'son_hata': self._son_hata,
            'son_or_kota': dict(self._son_or_kota)
                            if self._son_or_kota else None,
            'model_kota': {k: float(v)
                           for k, v in self._model_kota.items()},
            'ucus': len([r for r in self._ucus.values()
                         if not r['olay'].is_set()]),
        }

    def aktif_bilgi(self) -> Optional[Dict[str, Any]]:
        # 1. Önce beyin config'inden durum bilgisini al (API call'i GEREKMİYOR)
        config_etkin = False
        saglayici_config = 'bilinmiyor'
        model_config = 'bilinmiyor'
        
        try:
            import jarvis_beyin_kayit as _b
            aktif = _b.aktif_beyin()
            if aktif:
                config_etkin = aktif.get('etkin', False)
                saglayici_config = aktif.get('saglayici', 'bilinmiyor')
                model_config = aktif.get('model', 'bilinmiyor')
        except Exception:
            pass
        
        # 2. API call'i durumu: _son_saglayici varsa online, yoksa config_only
        has_online_connection = self._son_saglayici is not None
        
        if has_online_connection:
            # API call'i yapılmış, mevcut bilgileri kullan
            return {
                'saglayici': self._son_saglayici,
                'model': self._son_model,
                'kaynak': '%s %s' % (SAGLAYICI_ETIKET.get(
                    self._son_saglayici, self._son_saglayici),
                    self._son_model or ''),
                'mod': 'online',
                'bulut_acik': True,  ← Sadece API call'i yapıldığında True
                'ayar_bilgisi': False,  ← API call'i yapıldı
                'kota_bitis': float(self._kota.get(self._son_saglayici) or 0.0),
                'kota_hesap': self._son_saglayici in self._hesap_kota,
            }
        else:
            # API call'i yapılmadıysa config bilgisiyle göster
            return {
                'saglayici': saglayici_config,
                'model': model_config,
                'kaynak': '%s %s' % (SAGLAYICI_ETIKET.get(
                    saglayici_config, saglayici_config),
                    model_config or ''),
                'mod': 'config_only' if config_etkin else 'beklemede',
                'bulut_acik': config_etkin,  ← Sadece config'de etkin, kanıtlanmamış online DEĞİL
                'ayar_bilgisi': True,  ← Config'den bilgi alındı
                'kota_bitis': 0.0,
                'kota_hesap': False,
            }


def get_active_bbein() -> Optional[Dict[str, Any]]:
    """Aktif beyin bilgisini döndür."""
    from jarvis_model_yonetici import get_yonetici
    yonetici = get_yonetici()
    return yonetici.aktif_bilgi()


def get_yonetici() -> ModelYonetici:
    global _YONETICI
    with _KILIT:
        if _YONETICI is None:
            _YONETICI = ModelYonetici()
        return _YONETICI


def durum() -> Dict[str, Any]:
    return get_yonetici().durum()
