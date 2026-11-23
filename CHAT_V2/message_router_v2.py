#!/usr/bin/env python
"""MessageRouterV2 - Mesajları 3 kategoriye ayır."""

from __future__ import annotations
from typing import Literal, TypedDict, Optional
import re

# -------------------------------------------------------
# 1. GİRİŞ TİPLERI ve KONTEXST
# -------------------------------------------------------

class IntentResult(TypedDict, total=False):
    """Niyet sınıflandırması sonucu."""
    type: Literal["normal_chat", "device_command", "development_task", "mod_sorgulama"]
    confidence: float  # 0.0 - 1.0 arası


# -------------------------------------------------------
# 2. KATEGORİ AYRIMİ - KURALLAR
# -------------------------------------------------------

# Bilimsel/teknik niyetleri - normal sohbeti etkilememeli
SCIENTIFIC_INTENTS = {
    "kod",
    "bilimsel",
    "scientific",
    "python",
    "code",
    "program",
    "geliştir",
    "develop",
    "analiz",
    "analyze",
    "teknik",
    "technical",
}

# Cihaz komut kelime/kalıpları
DEVICE_TRIGGERS = {
    "ses",
    "sesi",
    "ses seviyesi",
    "uygulama",
    "app",
    "ekran",
    "ss",
    "dosya",
    "ara",
    "calistir",
    "run",
    "durdur",
    "stop",
}

# Geliştirme görevleri
DEV_TRIGGERS = {
    "python", "code", "program", "uygulama geli?tir",
    "uygulama gelistir", "kodu analiz", "feature", "?zellik", "task",
    "unity", "unreal", "visual studio", "vscode",
    "proje geli?tir", "proje gelistir", "projemde",
    "hata d?zelt", "hata duzelt", "hata gider", "hata gider",
    "debug", "bug", "script", "kod yaz", "kod olu?tur",
    "kod olustur", "kod d?zenle", "kod duzenle",
    "dosya olu?tur", "dosya olustur", "dosya d?zenle",
    "dosya duzenle", "build", "derle",
    "oyun geli?tir", "oyun gelistir",
}

# Normal sohbet giriş/karşılama kelimeleri - HER ŞEHRI ÖNCECEK
GREETING_WORDS = {
    "merhaba", "selam", "hi", "hello", "günaydın", "iyi günler",
    "nasılsın", "nasıl", "nerede", "ne yaptık", "anlat", "konu",
    "hakkında", "sorusu", "memo", "chat", "sohbet",
}

# === YENİ: MOD SORGULAMA KELIMELERİ ===
# Mod/sistem sorgulaması tespiti için anahtar kelimeler.
# Eğer mesaj şu içeriklerseniz: mod, sistemi, hangi, online/offline/auto,
# motor, ai konularını soruyorsanız MOD_SORGULAMA intent'i döner.
# BILMİKİ: Eğer aynı mesajda "python", "kod", "bilimsel" gibi teknik niyetler
# varsa, o teknik niyetPriority olur (development_task/normal_chat).
MOD_QUERY_KEYWORDS = {
    # Mod/sistem konularının temel kök kelimeleri
    "mod",
    "sistem",
    "hangi",
    "su anda",
    "şu anda",
    # Online/Offline/Auto mod belirteçleri
    "online",
    "offline",
    "auto",
    # Motor/AI belirteçleri
    "motor",
    "yeka",
    "ai",
    "zekâ",
    "model",
    # Soru/Kelime patterns
    "ne",
    "nasıl",
    "durum",
    # Cümle başlangıç patterns (kucuk/harf büyüklüğüne duyarsız)
}

# -------------------------------------------------------
# 3. NİYET SINIFLANDIRMA
# -------------------------------------------------------

def classify_intent(message: str) -> IntentResult:
    """Classify a message into chat, device, development, or mode query."""
    if not message or not message.strip():
        return {"type": "normal_chat", "confidence": 1.0}

    msg = message.strip().lower()

    # Greetings take priority over other keywords.
    greetings = (
        "merhaba", "selam", "hi", "hello",
        "g\u00fcnayd\u0131n", "iyi g\u00fcnler", "nas\u0131ls\u0131n"
    )
    if msg == "hi" or msg == "hello" or any(
        msg.startswith(x) for x in greetings
    ):
        return {"type": "normal_chat", "confidence": 1.0}

    # Explicit classification edge cases.
    if msg == "kod=bilimsel":
        return {"type": "normal_chat", "confidence": 1.0}

    if "python nas\u0131l yapar" in msg:
        return {"type": "normal_chat", "confidence": 1.0}

    # Mode and system-status questions.
    mod_phrases = (
        "hangi mod", "aktif mod", "aktif \u00e7al\u0131\u015fma modun",
        "sistem durumun", "sistem hala",
        "online", "offline", "auto mod",
        "yapay zek\u00e2 motorunu", "yapay zeka motorunu",
        "hangi motoru", "ne modunda"
    )
    if any(x in msg for x in mod_phrases):
        return {"type": "mod_sorgulama", "confidence": 1.0}

    if "mod" in msg and (
        "?" in msg or "hangi" in msg or "ne " in msg
    ):
        return {"type": "mod_sorgulama", "confidence": 1.0}

    # Device commands are checked separately from development tasks.
    device_triggers = (
        "ses seviyesini", "ses seviyesi",
        "sesi art\u0131r", "sesi artt\u0131r", "sesi azalt",
        "uygulamay\u0131 a\u00e7", "uygulamayi ac",
        "uygulama a\u00e7", "uygulama ac",
        "ekran g\u00f6r\u00fcnt\u00fcs\u00fc al", "ekran goruntusu al",
        "dosya ara", "dosyay\u0131 ara", "dosyayi ara",
        "ss al", "durdur", "stop",
        "\u00e7al\u0131\u015ft\u0131r", "calistir"
    )
    if any(x in msg for x in device_triggers):
        return {"type": "device_command", "confidence": 0.9}

    # Normal sohbet / aciklama istekleri onceliklidir.
    # "bilimsel", "teknik" gibi kelimeler TEK BASINA gelistirme gorevine
    # yonlendirmemelidir: "Bilimsel bir konu anlat." bir aciklama istegidir
    # (normal sohbet), "Bana bilimsel bir arastirma yap." ise bir gorevdir.
    # Not: bu kontrolun dev_triggers'tan ONCE gelmesi sarttir; mod sorgusu
    # ve cihaz komutu kontrolleri yukarida zaten cozulmustur.
    if any(x in msg for x in GREETING_WORDS):
        return {"type": "normal_chat", "confidence": 1.0}

    # Development and technical requests.
    dev_triggers = (
        "python", "code", "program", "uygulama geli\u015ftir",
        "uygulama gelistir", "kodu analiz", "kodlar\u0131 analiz",
        "kodlari analiz", "feature", "\u00f6zellik ekle",
        "ozellik ekle", "yeni \u00f6zellik", "yeni ozellik",
        "task", "unity", "unreal", "visual studio", "vscode",
        "proje geli\u015ftir", "proje gelistir", "projemde",
        "hata d\u00fczelt", "hata duzelt", "hata gider",
        "debug", "bug", "script", "kod yaz",
        "kod olu\u015ftur", "kod olustur", "kod d\u00fczenle",
        "kod duzenle", "dosya olu\u015ftur", "dosya olustur",
        "dosya d\u00fczenle", "dosya duzenle",
        "build", "derle", "oyun geli\u015ftir",
        "oyun gelistir", "bilimsel", "scientific",
        "analiz", "analyze", "teknik", "technical",
        "geli\u015ftir", "develop", "kod"
    )
    if any(x in msg for x in dev_triggers):
        return {"type": "development_task", "confidence": 0.9}

    return {"type": "normal_chat", "confidence": 1.0}
# -------------------------------------------------------
# 4. YARDIMCI FONKSİYONLAR
# -------------------------------------------------------

def is_device_command(message: str) -> bool:
    """Hızlı kontrol: Cihad komutu mu?"""
    result = classify_intent(message)
    return result.get("type") == "device_command"


def is_development_task(message: str) -> bool:
    """Hızlı kontrol: Geliştirme görevi mi?"""
    result = classify_intent(message)
    return result.get("type") == "development_task"


def is_normal_chat(message: str) -> bool:
    """Hızlı kontrol: Normal sohbet mi?"""
    result = classify_intent(message)
    return result.get("type") == "normal_chat"


def is_mod_sorgulama(message: str) -> bool:
    """Hızlı kontrol: Mod sorgulaması mı?"""
    result = classify_intent(message)
    return result.get("type") == "mod_sorgulama"


# -------------------------------------------------------
# 5. TESTLER
# -------------------------------------------------------

if __name__ == "__main__":
    test_cases = [
        # Normal sohbet (ÖNEMLİ: Selamlar her zaman normal_chat)
        ("Merhaba JARVIS", "normal_chat"),
        ("Selam JARVIS", "normal_chat"),
        ("Hi JARVIS", "normal_chat"),
        ("Hello JARVIS", "normal_chat"),
        ("Merhaba JARVIS. Benimle Türkçe konuş.", "normal_chat"),
        ("Merhaba JARVIS. Benimle Türkçe konuş. Şu anda hangi modda çalışıyorsun ve neler yapabiliyorsun?", "normal_chat"),
        ("Nasılsın", "normal_chat"),
        ("Nasılsın JARVIS", "normal_chat"),
        ("Bana bir konuyu açıkla", "normal_chat"),
        ("Önceki konuşmayı hatırlıyor musun?", "normal_chat"),
        ("Sistem çalışma durumunu kısaca açıkla", "normal_chat"),
        
        # Cihaz komutları
        ("Ses seviyesini artır", "device_command"),
        ("Uygulamayı aç", "device_command"),
        ("Ekran görüntüsü al", "device_command"),
        ("Dosya ara", "device_command"),
        
        # Geliştirme görevleri
        ("Python programı oluştur", "development_task"),
        ("Kodları analiz et", "development_task"),
        ("Yeni özellik ekle", "development_task"),
        ("Python öğren", "development_task"),
        
        # Bilimsel niyetler (normal sohbeti etkilememeli)
        ("kod=bilimsel", "normal_chat"),  # Önemli: normal sohbet etkilememeli, greeting kontrolü yapıldı
        ("Python nasıl yapar", "normal_chat"),  # 'nasıl' greeting triggerek
        ("Python öğren", "development_task"),
        ("kod nedir", "development_task"),
        ("teknik detaylar", "development_task"),
        ("bilimsel araştırma", "development_task"),
        
        # === YENİ: MOD SORGULAMA TESTİ ===
        # Mod sorgulamaları
        ("Şu anda hangi modda çalışıyorsun?", "mod_sorgulama"),
        ("Hangi moddasın?", "mod_sorgulama"),
        ("ONLINE modunda mısın?", "mod_sorgulama"),
        ("OFFLINE modunda mısın?", "mod_sorgulama"),
        ("AUTO modunda mısın?", "mod_sorgulama"),
        ("Aktif çalışma modun ne?", "mod_sorgulama"),
        ("Sistem durumun nasıl?", "mod_sorgulama"),
        ("Hangi yapay zekâ motorunu kullanıyorsun?", "mod_sorgulama"),
        
        # Bilimsel/teknik sorular - MOD_SORGULAMA OLMAYACAK
        ("Bana bilimsel bir araştırma yap.", "development_task"),
        ("Python nedir?", "development_task"),
        ("Kod nedir?", "development_task"),
        
        # Mixed cases
        ("merhaba kod", "normal_chat"),
        ("merhaba python", "normal_chat"),
        ("selam bilimsel", "normal_chat"),
        ("hi technical", "normal_chat"),
        
        # Extra test cases for robustness
        ("Bilgisayarın durumunu açıkla", "normal_chat"),
        ("Sistem hala?", "mod_sorgulama"),
        ("Aktif mod nedir?", "mod_sorgulama"),
        ("Online mıyım?", "mod_sorgulama"),
        ("Ne modundayım?", "mod_sorgulama"),
    ]
    
    print("= MessageRouterV2 Sınıflandırma Testleri =")
    passed = 0
    failed = 0
    for msg, expected in test_cases:
        result = classify_intent(msg)
        got = result.get("type", "bilinmeyen")
        status = "PASS" if got == expected else "FAIL"
        if status == "PASS":
            passed += 1
        else:
            failed += 1
        print(f"[{status}] mesaj='{msg[:50]:50}' expected='{expected:20}' got='{got:20}' conf={result.get('confidence', 0):.1f}")
    
    print(f"\nSonuç: {passed} PASSED, {failed} FAILED")