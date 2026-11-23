#!/usr/bin/env python
from __future__ import annotations

from typing import TypedDict, Optional, Dict, Any
import time
import uuid


# -------------------------------------------------------
# 1. REQUEST ID ve LOG TEMELİ
# -------------------------------------------------------

def new_request_id() -> str:
    """Benzersiz request_id üret."""
    return str(uuid.uuid4())


# -------------------------------------------------------
# 2. Yanıt Bilgisi
# -------------------------------------------------------

class ResponseInfo(TypedDict, total=False):
    """Yanıt bilgileri."""
    request_id: str
    message_type: str
    ai_provider: str
    first_token_ms: int
    total_response_ms: int
    tts_started: bool
    cloud_failed: bool
    local_llm_called: bool


# -------------------------------------------------------
# 3. Yanıt Yöneticisi
# -------------------------------------------------------

class ResponseManager:
    """Yanıt yöneticisi - TTS ve izleme."""

    def __init__(self):
        # Önceki mesaj tracker'ları (basit: son N mesajı hafızala)
        self._recent_requests: Dict[str, Dict[str, Any]] = {}
        self._max_recent: int = 10  # Kaç istek hafızada tutulacak

    def start_request(self, message_type: str = "normal_chat") -> str:
        """Yeni bir istek başlat ve request_id döndür."""
        req_id = new_request_id()
        self._recent_requests[req_id] = {
            "start_time": time.time() * 1000,  # ms
            "message_type": message_type,
            "tts_in_progress": False,
            "cancelled": False,
        }
        # Eski'ları temizle
        if len(self._recent_requests) > self._max_recent * 2:
            # En eski yarısıyu sil
            keys = list(self._recent_requests.keys())
            for k in keys[: len(keys) // 2]:
                del self._recent_requests[k]
        return req_id

    def finish_request(
        self,
        req_id: str,
        *,
        ai_provider: Optional[str] = None,
        first_token_ms: Optional[int] = None,
        total_response_ms: Optional[int] = None,
        cloud_failed: bool = False,
        local_llm_called: bool = False,
    ) -> ResponseInfo:
        """İsteği tamamla ve ResponseInfo döndür."""
        if req_id not in self._recent_requests:
            # Yanlış request_id - yeni bir tane oluştur
            req_id = new_request_id()

        info: ResponseInfo = {
            "request_id": req_id,
            "message_type": self._recent_requests[req_id].get("message_type", "normal_chat"),
            "ai_provider": ai_provider or "bilinmiyor",
            "first_token_ms": first_token_ms or 0,
            "total_response_ms": total_response_ms or 0,
            "tts_started": False,
            "cloud_failed": cloud_failed,
            "local_llm_called": local_llm_called,
        }

        # Hafızadan çıkar (veya tut)
        # self._recent_requests.pop(req_id, None)

        return info

    def mark_tts_started(self, req_id: str) -> None:
        """TTS başlatıldı işaretle."""
        if req_id in self._recent_requests:
            self._recent_requests[req_id]["tts_in_progress"] = True
            self._recent_requests[req_id]["tts_started"] = True

    def is_cancelled(self, req_id: str) -> bool:
        """İsteğin iptal edilip edilmediği."""
        return self._recent_requests.get(req_id, {}).get("cancelled", False)

    def cancel_request(self, req_id: str) -> None:
        """İsteği iptal et."""
        if req_id in self._recent_requests:
            self._recent_requests[req_id]["cancelled"] = True

    # --- İstatistikler ---

    def get_stats(self) -> Dict[str, Any]:
        """İstatistikleri döndür."""
        total = len(self._recent_requests)
        ttss = sum(1 for v in self._recent_requests.values() if v.get("tts_in_progress", False))
        cancelled = sum(1 for v in self._recent_requests.values() if v.get("cancelled", False))
        return {
            "active_requests": total,
            "tts_in_progress": ttss,
            "cancelled_requests": cancelled,
        }


# -------------------------------------------------------
# 5. TEST KISMI (test_chat_v2.py içinde test edilecek)
# -------------------------------------------------------

if __name__ == "__main__":
    rm = ResponseManager()

    print("= ResponseManagerV2 Testleri =")

    # Test 1: Request başlat ve bitir
    print("\n--- Test 1: Request başlat/bitir ---")
    req_id = rm.start_request("normal_chat")
    print(f"Request ID: {req_id}")
    info = rm.finish_request(
        req_id,
        ai_provider="gemini",
        first_token_ms=150,
        total_response_ms=800,
    )
    print(f"ResponseInfo: request_id={info['request_id']}, provider={info['ai_provider']}, "
          f"first_token_ms={info['first_token_ms']}, total_response_ms={info['total_response_ms']}")

    # Test 2: TTS işaretleme
    print("\n--- Test 2: TTS başlatıldı işaretleme ---")
    rm.mark_tts_started(req_id)
    print(f"TTS started: should be tracked")

    # Test 3: Farklı request_id
    print("\n--- Test 3: Farklı request_id ---")
    req_id2 = rm.start_request("device_command")
    info2 = rm.finish_request(req_id2, ai_provider="groq", total_response_ms=300)
    print(f"İkinci request: {info2['request_id']}, provider={info2['ai_provider']}")

    # Test 3: Stats
    print("\n--- Test 3: İstatistikler ---")
    print(f"Stats: {rm.get_stats()}")

    # Test 4: Benzersiz ID kontrolü
    print("\n--- Test 4: Unique request_id ---")
    ids = set()
    for _ in range(20):
        rid = new_request_id()
        ids.add(rid)
    print(f"20 farklı ID: {len(ids) == 20} (tümün farklı mı?: {len(ids) == 20})")

    print("\nSonuç: Tüm testler tamamlandı.")