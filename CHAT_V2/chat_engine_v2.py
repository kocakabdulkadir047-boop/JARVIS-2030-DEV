#!/usr/bin/env python
"""ChatEngineV2 - JARVIS CHAT V2 orchestration module.

Bu mod, ModeManager, MessageRouterV2, CloudEngineV2 ve ResponseManagerV2
bileşenlerini bir araya getiren merkezilestirme (orchestration) modülüdür.

KULLANIM:
    from chat_engine_v2 import ChatEngineV2
    engine = ChatEngineV2()
    result = engine.process_message("Merhaba JARVIS")
"""

from __future__ import annotations
import time

from typing import Optional, Dict, Any, Literal

from .mode_manager import ModeManager, get_mode_manager, set_mode, get_mode, MOD_ONLINE, MOD_OFFLINE, MOD_AUTO
from .message_router_v2 import classify_intent, is_device_command, is_development_task, is_normal_chat
from .cloud_engine_v2 import (
    CloudEngine, GEMINI, GROQ, OPENROUTER, gecmis_destekli)
from .response_manager_v2 import ResponseManager, new_request_id, ResponseInfo


def _gecmisle_cagir(fn, message, *, gecmis, **kw):
    """`fn` gecmis kabul ediyorsa ilet; eski imzali katmanlari bozmadan cagir."""
    if gecmis and gecmis_destekli(fn):
        kw['gecmis'] = gecmis
    return fn(message, **kw)


def _bulut_yetki_on_kontrol(message: str, mode: str, yetki,
                            kaynak: Optional[str]) -> bool:
    """FAZ 2.2A motor kapisi: bilet GECERLI mi? (tuketmeden).

    Gercek ag isteginden hemen once CloudEngine ayni bileti tuketerek
    yeniden dogrular. Burada yalnizca erken fail-closed saglanir.
    """
    if not isinstance(yetki, dict) or not kaynak:
        return False
    try:
        from jarvis_chat_v2_entegrasyon import yetki_dogrula
        return bool(yetki_dogrula(
            yetki, mesaj=message, mod=mode, kaynak=kaynak, tuket=False))
    except Exception:
        return False


class ChatEngineV2:
    """JARVIS CHAT V2 merkezi motoru.

    ModeManager, MessageRouterV2, CloudEngineV2 ve ResponseManagerV2
    bileşenlerini bir araya getirir.
    """

    def __init__(self):
        self.mode_manager = get_mode_manager()
        self.message_router = None  # classify_intent kullanılacak
        self.cloud_engine = CloudEngine()
        self.response_manager = ResponseManager()
        self._request_id: Optional[str] = None

    # --- Mod Yönetimi ---

    def get_mode(self) -> str:
        """Mevcut aktif modu döndür."""
        return self.mode_manager.get_mod()

    def get_mode_label(self) -> str:
        """Kullanıcıya gösterilebilir mod etiketini döndür."""
        return self.mode_manager.get_label()

    def set_mode(self, mod: str, *, save: bool = True) -> None:
        """Modu değiştir."""
        self.mode_manager.set_mod(mod, save=save)

    def resolve_mode(self, *, force: Optional[str] = None) -> str:
        """Mod belirle (force verildiyse onu, aksi halde mevcut mod)."""
        return self.mode_manager.resolve_mode(force=force)

    # --- Mesaj Sınıflandırması ---

    def classify_intent(self, message: str) -> Dict[str, Any]:
        """Mesajı sınıflandır ve niyet türünü döndür."""
        if not message:
            return {"type": "normal_chat", "confidence": 1.0}
        return classify_intent(message)

    def is_normal_chat(self, message: str) -> bool:
        """Hızlı kontrol: Normal sohbet mi?"""
        return is_normal_chat(message)

    def is_device_command(self, message: str) -> bool:
        """Hızlı kontrol: Cihaz komutu mu?"""
        return is_device_command(message)

    def is_development_task(self, message: str) -> bool:
        """Hızlı kontrol: Geliştirme görevi mi?"""
        return is_development_task(message)

    # --- Cloud Engine İsteği ---

    def process_message(
        self,
        message: str,
        *,
        force_mode: Optional[str] = None,
        yetki: Optional[Dict[str, Any]] = None,
        kaynak: Optional[str] = None,
        gecmis: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Tek mesaj işleme.

        Args:
            message: Kullanıcı mesajı
            force_mode: Modu zorlayıp geçmek için (None = mevcut mod)
            yetki: FAZ 2.2A tek kullanımlık bulut izin bileti
            kaynak:İstek kaynağı (canli/sesli/adapter_*)
            gecmis: Oturumun onceki turlari (role/content sozlukleri)

        Dönen dict:
            {
                "request_id": str,
                "mode": str,
                "message_type": str,      # normal_chat, device_command, development_task
                "ai_provider": Optional[str],
                "success": bool,
                "response": Optional[str],
                "error": Optional[str],
                "attempted_providers": list,
                "first_token_ms": int,
                "total_response_ms": int,
                "cloud_failed": bool,
                "local_llm_called": bool,
            }
        """
        # 1. Mod belirle
        # NOT: set_mod() None dondurdugu icin resolve_mode(force=...) None
        # donebilir; bu durumda mevcut mod dogrudan okunur.
        mode = self.resolve_mode(force=force_mode)
        if mode not in (MOD_ONLINE, MOD_OFFLINE, MOD_AUTO):
            mode = self.get_mode()
        # Router modu TEK yetkili kaynaktir. ModeManager'in kendi config
        # dosyasi eski kalabiliyor; force_mode verilmediginde router ne
        # diyorsa o uygulanir (yukari veya asagi yon). Zorlanmis offline
        # ise bu blok atlanir; boylece `zorla_offline` semantigi korunur.
        if force_mode is None:
            try:
                import jarvis_ai_router as _R
                _rm = str(_R.mod_oku() or '').strip().lower()
                if _rm in (MOD_ONLINE, MOD_OFFLINE, MOD_AUTO):
                    mode = _rm
                else:
                    mode = MOD_OFFLINE
            except Exception:
                mode = MOD_OFFLINE
        mode_label = self._mod_etiket(mode)

        # 2. Mesajı sınıflandır
        intent_result = self.classify_intent(message)
        msg_type = intent_result.get("type", "normal_chat")

        result: Dict[str, Any] = {
            "request_id": None,
            "mode": mode,
            "mode_label": mode_label,
            "message_type": msg_type,
            "ai_provider": None,
            "model": None,
            "success": False,
            "result_type": None,
            "response": None,
            "error": None,
            "error_code": None,
            "errors": [],
            "attempted_providers": [],
            "free_verified": False,
            "provider_request_id": None,
            "first_token_ms": 0,
            "total_response_ms": 0,
            "cloud_failed": False,
            "local_llm_called": False,
        }

        # === MOD SORGULAMA HANDLING (GOREV 2.5) ===
        # Mod/sistem sorgulamasi tespit edildi:
        #   * LLM / bulut / yerel model CAGRISI YAPILMAZ
        #   * Gercek durum okunur (jarvis_ai_router.aktif_model_bilgisi
        #     + Ollama varlik kontrolu)
        #   * Kullaniciya Turkce, UYDURMA bilgi olmayan yanit dondurulur
        if msg_type == "mod_sorgulama":
            self._request_id = self.response_manager.start_request(msg_type)
            gercek = self._gercek_mod_bilgisi()
            result["request_id"] = self._request_id
            result["mode"] = gercek["mod"]
            result["mode_label"] = self._mod_etiket(gercek["mod"])
            result["message_type"] = "mod_sorgulama"
            result["success"] = True
            result["result_type"] = "status"
            result["response"] = self._mod_sorgulama_yaniti(gercek)
            result["ai_provider"] = None
            result["model"] = None
            result["error"] = None
            result["error_code"] = None
            result["errors"] = []
            result["attempted_providers"] = []
            result["first_token_ms"] = 0
            result["total_response_ms"] = 0
            result["cloud_failed"] = False
            result["local_llm_called"] = False
            return result

        # 3. Request ID başlat (ResponseManager'da da kayıt olur)
        self._request_id = self.response_manager.start_request(msg_type)
        # request_id sonuc ciktisina da yazilir (GUI callback + izleme)
        result["request_id"] = self._request_id

        # FAZ 2.2A: ONLINE/AUTO icin motor seviyesinde erken kapı.
        # Bilet yok/gecersizse ag katmanina HIC inilmez.
        if mode in (MOD_ONLINE, MOD_AUTO) and not _bulut_yetki_on_kontrol(
                message, mode, yetki, kaynak):
            result["result_type"] = "connection_error"
            result["error_code"] = "NOT_APPROVED"
            result["error"] = (
                "Bulut izni yok; istek ağ katmanına gönderilmedi.")
            result["mode"] = mode
            result["mode_label"] = mode_label
            result["local_llm_called"] = False
            result["cloud_failed"] = False
            return result

        # 4. Mesaj türüne göre işlem

        # 5. OFFLINE modunda: dogrudan yerel Qwen3.5-4B
        if mode == MOD_OFFLINE:
            result["local_llm_called"] = True
            yerel_result = _gecmisle_cagir(
                self.cloud_engine.infer_local, message, gecmis=gecmis)
            result["attempted_providers"] = yerel_result.get("attempted", [])
            result["errors"] = yerel_result.get("errors", [])
            if yerel_result["success"]:
                result["ai_provider"] = yerel_result.get("provider", "llama-cpp-local")
                result["model"] = yerel_result.get("model")
                result["success"] = True
                result["result_type"] = "answer"
                result["response"] = yerel_result.get("response")
                result["total_response_ms"] = yerel_result.get("total_response_ms", 0)
                return result
            result["result_type"] = "connection_error"
            result["error_code"] = yerel_result.get("error_code") or "OLLAMA_DOWN"
            result["error"] = (
                "OFFLINE: Yerel Qwen basarisiz - "
                + str(yerel_result.get("error") or "")
            )
            result["total_response_ms"] = int((time.time() * 1000) - self.response_manager._recent_requests[self._request_id]["start_time"])
            return result

        # 6. AUTO modunda: bulut deneyin, başarısızsa yerel Ollama (qwen3:4b)
        if mode == MOD_AUTO:
            # Bulut denemesi
            cloud_result = _gecmisle_cagir(
                self.cloud_engine.infer, message, gecmis=gecmis,
                mode="auto", yetki=yetki, kaynak=kaynak)
            result["attempted_providers"] = cloud_result.get("attempted", [])
            result["errors"] = cloud_result.get("errors", [])
            if cloud_result["success"]:
                result["ai_provider"] = cloud_result["provider"]
                result["model"] = cloud_result.get("model")
                result["success"] = True
                result["result_type"] = "answer"
                result["response"] = cloud_result["response"]
                result["free_verified"] = bool(
                    cloud_result.get("free_verified"))
                result["provider_request_id"] = cloud_result.get("request_id")
                result["total_response_ms"] = cloud_result.get("total_response_ms", 0)
                return result
            if str(cloud_result.get("error_code") or '') == 'NOT_APPROVED':
                result["result_type"] = "connection_error"
                result["error_code"] = "NOT_APPROVED"
                result["error"] = (
                    "Bulut izni geçersiz; istek ağ katmanına gönderilmedi.")
                result["model"] = cloud_result.get("model")
                result["local_llm_called"] = False
                result["cloud_failed"] = False
                return result
            # Tüm bulut başarısızsa gerçek yerel Ollama
            result["local_llm_called"] = True
            yerel_result = _gecmisle_cagir(
                self.cloud_engine.infer_local, message, gecmis=gecmis)
            result["attempted_providers"] = result["attempted_providers"] + yerel_result.get("attempted", [])
            result["errors"] = result["errors"] + yerel_result.get("errors", [])
            if yerel_result["success"]:
                result["ai_provider"] = yerel_result.get("provider", "llama-cpp-local")
                result["model"] = yerel_result.get("model")
                result["success"] = True
                result["result_type"] = "answer"
                result["response"] = yerel_result.get("response")
                result["total_response_ms"] = yerel_result.get("total_response_ms", 0)
                return result
            result["result_type"] = "connection_error"
            result["error_code"] = yerel_result.get("error_code") or "OLLAMA_DOWN"
            result["model"] = yerel_result.get("model")
            result["error"] = (
                "AUTO: Secili bulut saglayicisi ve yerel Qwen basarisiz - "
                + str(yerel_result.get("error") or "")
            )
            result["total_response_ms"] = int((time.time() * 1000) - self.response_manager._recent_requests[self._request_id]["start_time"])
            return result

        # 7. ONLINE modunda: yalnızca seçili sağlayıcıyı dene
        online_result = _gecmisle_cagir(
            self.cloud_engine.infer, message, gecmis=gecmis,
            mode="online", yetki=yetki, kaynak=kaynak)
        result["attempted_providers"] = online_result.get("attempted", [])
        result["errors"] = online_result.get("errors", [])

        if online_result["success"]:
            result["ai_provider"] = online_result["provider"]
            result["model"] = online_result.get("model")
            result["success"] = True
            result["result_type"] = "answer"
            result["response"] = online_result["response"]
            result["free_verified"] = bool(
                online_result.get("free_verified"))
            result["provider_request_id"] = online_result.get("request_id")
            result["first_token_ms"] = online_result.get("first_token_ms", 0)
            result["total_response_ms"] = online_result.get("total_response_ms", 0)
            return result

        # Seçili sağlayıcı başarısızsa başka bulut sağlayıcısına geçilmez.
        result["cloud_failed"] = True
        result["result_type"] = online_result.get("result_type") or "connection_error"
        result["error_code"] = online_result.get("error_code") or "PROVIDER_ERROR"
        result["model"] = online_result.get("model")
        result["free_verified"] = bool(
            online_result.get("free_verified"))
        result["provider_request_id"] = online_result.get("request_id")
        result["error"] = (online_result.get("error")
                           or "ONLINE: Ücretsiz sağlayıcılar yanıt vermedi")
        result["local_llm_called"] = False
        result["total_response_ms"] = int((time.time() * 1000) - self.response_manager._recent_requests[self._request_id]["start_time"])
        return result

    # --- Bilgi ---

    # --- GOREV 2.5: Gercek Mod / Saglayici Bilgisi ---

    def _mod_etiket(self, mod: str) -> str:
        """Mod icin Turkce etiket (uydurma yok, sadece mod adindan)."""
        return {
            MOD_ONLINE: "ONLINE (bulut AI)",
            MOD_OFFLINE: "OFFLINE (yerel model)",
            MOD_AUTO: "AUTO (internet varsa bulut, yoksa yerel model)",
        }.get(mod, mod)

    def _gercek_mod_bilgisi(self) -> Dict[str, Any]:
        """Gercek mod + son kullanilan saglayici/model bilgisini topla.

        UYDURMA YAPILMAZ: baglanti varmis gibi davranilmaz. Son basarili
        istek yoksa saglayici/model alani bos kalir; politika ayri gosterilir.
        """
        # Mod TEK kaynaktan raporlanir: router (config/jarvis_bag_mod.json).
        # ModeManager'in kendi dosyasi eski kalirsa UI ile motor celisirdi.
        _mod = self.mode_manager.get_mod()
        _kaynak_dosya = "CHAT_V2.mode_manager"
        try:
            import jarvis_ai_router as _R2
            _rm = str(_R2.mod_oku() or '').strip().lower()
            if _rm in (MOD_ONLINE, MOD_OFFLINE, MOD_AUTO):
                _mod = _rm
                _kaynak_dosya = "jarvis_ai_router.mod_oku"
        except Exception:
            pass
        bilgi: Dict[str, Any] = {
            "mod": _mod,
            "saglayici": None,
            "model": None,
            "kaynak": None,
            "bulut_acik": False,
            "yerel_var": False,
            "yerel_bilindi": False,
            "politika": [],
            "son_saglayici": None,
            "son_model": None,
            "kaynak_dosya": _kaynak_dosya,
        }
        # 1) FAZ 2 model yoneticisi: politika + son gercek basarili istek
        try:
            import jarvis_model_yonetici as _my
            d = _my.durum()
            bilgi["politika"] = list(d.get("saglayici_sirasi") or [])
            bilgi["son_saglayici"] = d.get("son_saglayici")
            bilgi["son_model"] = d.get("son_model")
            bilgi["bulut_acik"] = any(
                bool((v or {}).get("anahtar_var"))
                for v in (d.get("saglayicilar") or {}).values())
            bilgi["kaynak_dosya"] = "jarvis_model_yonetici"
            if d.get("son_saglayici"):
                bilgi["saglayici"] = d.get("son_saglayici")
                bilgi["model"] = d.get("son_model")
                bilgi["kaynak"] = "%s %s" % (
                    d.get("son_saglayici"), d.get("son_model") or "")
        except Exception:
            # 2) Eski router bilgisi (yalnizca yonetici yoksa)
            try:
                import jarvis_ai_router as _R
                b = _R.aktif_model_bilgisi()
                if b:
                    bilgi["mod"] = b.get("mod") or bilgi["mod"]
                    bilgi["saglayici"] = b.get("saglayici")
                    bilgi["model"] = b.get("model")
                    bilgi["kaynak"] = b.get("kaynak")
                    bilgi["bulut_acik"] = bool(b.get("bulut_acik"))
                    bilgi["politika"] = list(b.get("politika") or [])
                    bilgi["kaynak_dosya"] = "jarvis_ai_router.aktif_model_bilgisi"
            except Exception:
                pass
        # 2) Yerel model gercekten var mi? (llama.cpp + Qwen3.5-4B)
        # GOREV 2.7 / AŞAMA 5: SOFT kontrol - ag cagrisi YAPILMAZ, onbellekteki
        # son bilgi kullanilir. Boylece mod sorgusu ANINDA yanit verir.
        try:
            from .cloud_engine_v2 import _ollama_var_soft, _OLLAMA_CACHE
            _soft = bool(_ollama_var_soft())
            bilgi["yerel_var"] = _soft
            # Onbellek bos ise durum BILINMIYOR (ag cagrisi yapilmaz).
            bilgi["yerel_bilindi"] = bool(_OLLAMA_CACHE.get('t'))
        except Exception:
            bilgi["yerel_var"] = False
            bilgi["yerel_bilindi"] = False
        return bilgi

    def _mod_sorgulama_yaniti(self, g: Dict[str, Any]) -> str:
        """Mod/sistem sorgusuna Turkce, gercek durumu anlatan yanit."""
        mod = g.get("mod") or "online"
        kaynak = g.get("kaynak")
        politika = list(g.get("politika") or [])
        bulut_acik = bool(g.get("bulut_acik"))
        yerel_var = bool(g.get("yerel_var"))
        yerel_bilindi = bool(g.get("yerel_bilindi"))
        parcalar = []
        politika_metni = "OpenRouter -> Gemini -> GLM-4-Flash -> Groq"
        if politika:
            adlar = {"openrouter": "OpenRouter", "gemini": "Gemini",
                     "zai_glm": "GLM-4-Flash", "groq": "Groq"}
            politika_metni = " -> ".join(
                adlar.get(str(x), str(x)) for x in politika)

        if mod == MOD_OFFLINE:
            parcalar.append("Su anda OFFLINE modundayim.")
            if yerel_var:
                parcalar.append("Yerel model kullaniliyor: %s." % (kaynak or "Qwen3.5-4B (llama.cpp)"))
                parcalar.append("Bulut saglayici kullanilmaz.")
            elif yerel_bilindi:
                parcalar.append(
                    "Ancak yerel model su anda kullanilamiyor "
                    "(Qwen sunucusu calismiyor veya model yuklu degil), "
                    "bu yuzden yanit uretemiyorum."
                )
            else:
                parcalar.append(
                    "Yerel modelin durumu su anda bilinmiyor "
                    "(Yerel Qwen kontrolu yapilmadi)."
                )
        elif mod == MOD_AUTO:
            parcalar.append("Su anda AUTO modundayim.")
            parcalar.append("Ucretsiz bulut onceligi: %s." % politika_metni)
            if kaynak:
                parcalar.append("Son basarili yanit: %s." % kaynak)
            else:
                parcalar.append(
                    "Bu oturumda henuz basarili bir bulut istegi kaydi yok.")
            if bulut_acik:
                parcalar.append("En az bir saglayici icin anahtar tanimli.")
            else:
                parcalar.append("Saglayici anahtari tanimli degil.")
            if yerel_var:
                parcalar.append("Bulut basarisiz olursa yerel modele gecilir (Qwen3.5-4B / llama.cpp).")
            elif yerel_bilindi:
                parcalar.append("Yerel model su anda kullanilamiyor.")
            else:
                parcalar.append("Yerel modelin durumu su anda bilinmiyor.")
        else:  # ONLINE
            parcalar.append("Su anda ONLINE modundayim.")
            parcalar.append("Ucretsiz sohbet onceligi: %s." % politika_metni)
            if kaynak:
                parcalar.append("Son basarili yanit: %s." % kaynak)
            else:
                parcalar.append(
                    "Bu oturumda henuz basarili bir bulut istegi kaydi yok.")
            if bulut_acik:
                parcalar.append("Saglayici anahtarlari tanimli; baglanti "
                                "yalnizca gercek istek sonucuyla dogrulanir.")
            else:
                parcalar.append(
                    "Ancak saglayici anahtari tanimli degil; istek gonderilemez.")
            if yerel_bilindi and not yerel_var:
                parcalar.append("OFFLINE moduna gecildiginde yerel model de kullanilamaz.")

        return " ".join(parcalar)

    def get_stats(self) -> Dict[str, Any]:
        """İstatistikleri döndür."""
        return {
            "mode": self.get_mode(),
            "mode_label": self.get_mode_label(),
            "mode_manager_stats": self.mode_manager.get_stats(),
            "response_manager_stats": self.response_manager.get_stats(),
        }


# === Tek örnek (singleton) yardımcı fonksiyon ===

_global_engine: Optional[ChatEngineV2] = None


def get_chat_engine() -> ChatEngineV2:
    """Global ChatEngineV2 örneğini döndür."""
    global _global_engine
    if _global_engine is None:
        _global_engine = ChatEngineV2()
    return _global_engine


def process_message(
    message: str,
    *,
    force_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Kısayol: Tek mesaj işleme."""
    return get_chat_engine().process_message(message, force_mode=force_mode)


# === Örnek kullanım ===

if __name__ == "__main__":
    engine = ChatEngineV2()
    print("ChatEngineV2 başlatıldı")
    print(f"Başlangıç mod: {engine.get_mode()} ({engine.get_mode_label()})")

    # Test: Normal sohbet
    result = engine.process_message("Merhaba JARVIS, nasılsın?")
    print(f"İstek ID: {result['request_id']}")
    print(f"Mod: {result['mode']} ({result['message_type']})")
    print(f"Sağlayıcı: {result['ai_provider']}")
    print(f"Başarılı: {result['success']}")
    print(f"Yanıt: {result['response'][:60] if result['response'] else 'Yok'}...")
    print(f"Süre: {result['total_response_ms']} ms")