# -*- coding: utf-8 -*-
"""JARVIS SONSUZ v3 — ADAPTER (z42).

JarvisLive / arayuz katmaninin SONSUZ v2 motoruna baglanma gunlugu.
Her metod try/except'ten gecer; BASBOS donmez. 'ikisi' (komut+sohbet
ayrimi) zaten jarvis_sonsuz2.calistir icinde cozulur; bu dosya sadece
komut cevabinın UI'a (ve tekrardan log'a) sozlesmelı aktarilmasindan
sorumludur.
"""

from typing import Optional

MODULE_TAG = 'sonsuz_v3_adapter'

# Modullerin keşfedilip saklanacağı kayıt defteri.
_MODULE_REGISTRY = [
    "jarvis_usta", "jarvis_ajan", "jarvis_hakem", "jarvis_sonsuz2",
    "jarvis_hafiza", "jarvis_yetenek", "jarvis_speech_manager",
    "jarvis_canli_tts", "jarvis_telefon", "jarvis_ozellik_merkezi",
    "jarvis_bilgisayar", "jarvis_platform", "jarvis_kod_ajan",
    "jarvis_unity_uretici", "jarvis_rolo_x_arayuz", "jarvis_lua",
]


class _Adapter:
    """JARVIS modül kayıt defteri. inspect() ile modülleri içe aktarır,
    modules sözlüğü ve get_function() ile erişim sağlar."""

    def __init__(self):
        self.modules = {}
        self._inspected = False

    def inspect(self, force=False):
        """Bilinen JARVIS modüllerini içe aktarır ve modules'e kaydeder."""
        if self._inspected and not force:
            return self.modules
        for mod_name in _MODULE_REGISTRY:
            if mod_name in self.modules and not force:
                continue
            try:
                mod = __import__(mod_name)
                self.modules[mod_name] = mod
            except Exception:
                # Modül yok veya içe aktarılamaz — atla, sistemi bozma.
                pass
        self._inspected = True
        return self.modules

    def get_function(self, module_name, func_name):
        """Belirli modüldeki bir fonksiyonu döndürür."""
        mod = self.modules.get(module_name)
        if mod is None:
            # Hemen dene: modülü içe aktarmayı çalıştır.
            try:
                mod = __import__(module_name)
                self.modules[module_name] = mod
            except Exception:
                return None
        try:
            return getattr(mod, func_name, None)
        except Exception:
            return None


# Tekil adapter örneği — jarvis_v3_ai_baglanti vb. bu adıyla içe aktarır.
adapter = _Adapter()


class S2Adapter:
    """Hazır arayuz uzerinden calisabilen minimum adaptor."""

    def __init__(self, log=None, ses=None):
        self.log = log
        self.ses = ses
        self.baslatildi = False
        self._yukle()

    def _yukle(self):
        try:
            import jarvis_sonsuz2 as _s2  # noqa: F401
            self.baslatildi = True
        except Exception as _e:
            self.log("[" + MODULE_TAG + "] sonsuz2 yuklenemedi: " +
                     repr(_e)[:160])
            self.baslatildi = False

    def baslat(self):
        """Arka plan servislerini baslat (hatirlatici, fiyat, AFK ...)."""
        try:
            import jarvis_sonsuz_v3_motor as _m3
            ok = _m3.v3_baslat(log=self.log, ses=self.ses)
            self.baslatildi = bool(ok)
            if self.log:
                self.log("[S2Adapter] baslat ok=" + str(self.baslatildi))
            return self.baslatildi
        except Exception as _e:
            if self.log:
                self.log("[S2Adapter] baslat hata: " + repr(_e)[:160])
            return False

    def talep_et(self, talep: str) -> dict:
        """Tek komut/sohbet/ikisi islenmesi; arayuz icin gunvenli dondurur."""
        try:
            import jarvis_sonsuz_v3_motor as _m3
            sonuc = _m3.v3_talep(talep, log=self.log, ses=self.ses,
                                 ekran_al=True)
            if not isinstance(sonuc, dict):
                sonuc = {'durum': 'BILINMEYEN', 'cevap': str(sonuc)}
            return sonuc
        except Exception as _e:
            if self.log:
                self.log("[S2Adapter] talep_et hata: " + repr(_e)[:200])
            return {'durum': 'ADAPTER_HATA', 'hata': repr(_e)[:200]}

    def komut_uygula(self, komut: str) -> Optional[str]:
        """Komut icin sadece metin cevap (GUI-muhtelif isletim)."""
        sonuc = self.talep_et(komut)
        return sonuc.get('cevap') or sonuc.get('metin') or ''
