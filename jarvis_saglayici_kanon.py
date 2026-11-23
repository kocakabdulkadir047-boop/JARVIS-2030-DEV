#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JARVIS - Saglayici katalogu (TEK YAPILANDIRMA KAYNAGI).

GOREV 2.8 / Bolum 2:
  * Model adlari, API adresleri ve fiyat politikasi burada tek yerde durur.
  * Yeni saglayici eklemek icin bu listeye bir kayit eklemek yeterlidir.
  * Her kayit GERCEK bir entegrasyonu tanimlar:
      api_tipi  -> 'gemini'  : Google generateContent govdesi
                -> 'openai'  : OpenAI-uyumlu /chat/completions
                -> 'ollama'  : yerel /v1/chat/completions
      url       -> gercek endpoint (zaten %s yer tutucularini icerir)
      modeller  -> gercek model kimlikleri
      anahtar_adi -> anahtarin config/api_keys.json icindeki alan adi
      ucret     -> 'ucretsiz' | 'ucretli' | 'bilinmiyor'

  Ucret politikasi (Bolum 6):
    * 'ucretsiz'      : saglayici katmani bilinir; model izni icin ayrica
                        model bazli prompt/completion = 0 kaniti gerekir
    * 'ucretli'       : ucretli -> varsayilan KAPALI, acik kullanici onayi gerekir
    * 'bilinmiyor'    : dogrulanmamis -> varsayilan KAPALI, acik onay gerekir
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Fiyat / izin sabitleri
# ---------------------------------------------------------------------------
UCRETSIZ = 'ucretsiz'
UCRETLI = 'ucretli'
BILINMIYOR = 'bilinmiyor'

#: Ucretsiz katmani bilinen saglayicilar; model izni icin ayrica
#: model bazli fiyat kaniti (prompt/completion = 0) gerekir.
UCRETSIZ_OLANLAR = ('gemini', 'groq', 'openrouter', 'ollama', 'zai_glm')

#: Acik kullanici onayi olmadan HICBIR kosulda cagrilmayacak saglayicilar
ONAY_GEREKENLER = ('deepseek', 'anthropic', 'openai', 'minimax')

API_TIPI_GEMINI = 'gemini'
API_TIPI_OPENAI = 'openai'
API_TIPI_OLLAMA = 'ollama'

#: Mevcut mimaride tamamen engelli saglayicilar (politika)
POLITIKA_ENGELLI = ('openai', 'gpt', 'anthropic', 'claude')


# ---------------------------------------------------------------------------
# Katalog
# ---------------------------------------------------------------------------
KATALOG: Dict[str, Dict[str, Any]] = {
    'gemini': {
        'ad': 'gemini',
        'etiket': 'Google Gemini',
        'aciklama': 'Google AI Studio uzerinden erisim. Ucretsiz katman mevcut.',
        'api_tipi': API_TIPI_GEMINI,
        'url': ('https://generativelanguage.googleapis.com/v1beta/'
                'models/%s:generateContent?key=%s'),
        'modeller': ['gemini-3.8-flash', 'gemini-2.5-flash', 'gemini-2.0-flash'],
        'varsayilan_model': 'gemini-3.8-flash',
        'anahtar_adi': 'gemini_api_key',
        'ucret': UCRETSIZ,
        'kategori': 'bulut',
        'anahtar_gerekli': True,
    },
    'groq': {
        'ad': 'groq',
        'etiket': 'Groq',
        'aciklama': 'Hizli OpenAI-uyumlu API. Ucretsiz katman mevcut.',
        'api_tipi': API_TIPI_OPENAI,
        'url': 'https://api.groq.com/openai/v1/chat/completions',
        'modeller': ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant'],
        'varsayilan_model': 'llama-3.3-70b-versatile',
        'anahtar_adi': 'groq_api_key',
        'ucret': UCRETSIZ,
        'kategori': 'bulut',
        'anahtar_gerekli': True,
    },
    'openrouter': {
        'ad': 'openrouter',
        'etiket': 'OpenRouter',
        'aciklama': 'Coklu model agi. Yalnizca ":free" modeli ucretsizdir.',
        'api_tipi': API_TIPI_OPENAI,
        'url': 'https://openrouter.ai/api/v1/chat/completions',
        'modeller': ['meta-llama/llama-3.3-70b-instruct:free',
                     'google/gemini-2.0-flash-exp:free'],
        'varsayilan_model': 'meta-llama/llama-3.3-70b-instruct:free',
        'anahtar_adi': 'openrouter_api_key',
        'ucret': UCRETSIZ,
        'kategori': 'bulut',
        'anahtar_gerekli': True,
    },
    'zai_glm': {
        'ad': 'zai_glm',
        'etiket': 'Z.AI (GLM)',
        'aciklama': 'Z.AI / Zhipu AI GLM modelleri. OpenAI-uyumlu API.',
        'api_tipi': API_TIPI_OPENAI,
        'url': 'https://api.z.ai/api/paas/v4/chat/completions',
        'modeller': ['glm-4.7-flash', 'glm-4-flash', 'glm-4-air', 'glm-4-plus'],
        'varsayilan_model': 'glm-4-flash',
        'ucretsiz_modeller': ['glm-4-flash', 'glm-4-air'],
        'anahtar_adi': 'z_ai_api_key',
        'ucret': UCRETSIZ,
        'kategori': 'bulut',
        'anahtar_gerekli': True,
    },
    'minimax': {
        'ad': 'minimax',
        'etiket': 'MiniMax',
        'aciklama': 'MiniMax modelleri. OpenAI-uyumlu API.',
        'api_tipi': API_TIPI_OPENAI,
        'url': 'https://api.minimax.io/v1/chat/completions',
        'modeller': ['MiniMax-M2', 'MiniMax-M1', 'MiniMax-Text-01'],
        'varsayilan_model': 'MiniMax-M2',
        'anahtar_adi': 'minimax_api_key',
        'ucret': BILINMIYOR,
        'kategori': 'bulut',
        'anahtar_gerekli': True,
    },
    'ollama': {
        'ad': 'ollama',
        'etiket': 'Ollama (yerel)',
        'aciklama': 'Yerel model. Internet gerektirmez, tamamen ucretsiz.',
        'api_tipi': API_TIPI_OLLAMA,
        'url': 'http://localhost:11434/v1/chat/completions',
        'modeller': ['qwen3:4b', 'qwen3-vl:2b'],
        'varsayilan_model': 'qwen3:4b',
        'anahtar_adi': None,
        'ucret': UCRETSIZ,
        'kategori': 'yerel',
        'anahtar_gerekli': False,
    },
    'deepseek': {
        'ad': 'deepseek',
        'etiket': 'DeepSeek',
        'aciklama': 'Ucretli API. Acik kullanici onayi olmadan kullanilmaz.',
        'api_tipi': API_TIPI_OPENAI,
        'url': 'https://api.deepseek.com/chat/completions',
        'modeller': ['deepseek-chat', 'deepseek-reasoner'],
        'varsayilan_model': 'deepseek-chat',
        'anahtar_adi': 'deepseek_api_key',
        'ucret': UCRETLI,
        'kategori': 'bulut',
        'anahtar_gerekli': True,
    },
    'anthropic': {
        'ad': 'anthropic',
        'etiket': 'Anthropic Claude',
        'aciklama': 'Ucretli API. Politika gereği engelli.',
        'api_tipi': API_TIPI_OPENAI,
        'url': 'https://api.anthropic.com/v1/messages',
        'modeller': ['claude-3-5-sonnet-latest'],
        'varsayilan_model': 'claude-3-5-sonnet-latest',
        'anahtar_adi': 'anthropic_api_key',
        'ucret': UCRETLI,
        'kategori': 'bulut',
        'anahtar_gerekli': True,
        'politika_engelli': True,
    },
    'openai': {
        'ad': 'openai',
        'etiket': 'OpenAI (GPT)',
        'aciklama': 'Politika gereği tamamen engelli (GPT/OpenAI).',
        'api_tipi': API_TIPI_OPENAI,
        'url': 'https://api.openai.com/v1/chat/completions',
        'modeller': ['gpt-4o-mini'],
        'varsayilan_model': 'gpt-4o-mini',
        'anahtar_adi': 'openai_api_key',
        'ucret': UCRETLI,
        'kategori': 'bulut',
        'anahtar_gerekli': True,
        'politika_engelli': True,
    },
}

#: Kurulum sihirbazinda gosterilecek saglayici sirasi
KURULUM_SIRASI = ('zai_glm', 'gemini', 'minimax', 'groq', 'openrouter', 'ollama')


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------
def saglayici_var(ad: str) -> bool:
    return str(ad or '').strip().lower() in KATALOG


def bilgi(ad: str) -> Dict[str, Any]:
    """Saglayici tanimini dondur (yoksa bos sozluk)."""
    return dict(KATALOG.get(str(ad or '').strip().lower(), {}))


def etiket(ad: str) -> str:
    b = bilgi(ad)
    return b.get('etiket') or str(ad or '')


def modeller(ad: str) -> List[str]:
    b = bilgi(ad)
    return list(b.get('modeller') or [])


def varsayilan_model(ad: str) -> str:
    b = bilgi(ad)
    m = b.get('varsayilan_model')
    if m:
        return m
    ms = b.get('modeller') or []
    return ms[0] if ms else ''


def _sifir_fiyat(deger: Any) -> bool:
    if deger is None or isinstance(deger, bool):
        return False
    try:
        return Decimal(str(deger).strip()) == 0
    except (InvalidOperation, ValueError, TypeError):
        return False


def _fiyat_uygun(pricing: Any) -> bool:
    if not isinstance(pricing, dict):
        return False
    if 'prompt' not in pricing or 'completion' not in pricing:
        return False
    if not (_sifir_fiyat(pricing.get('prompt'))
            and _sifir_fiyat(pricing.get('completion'))):
        return False
    for alan, deger in pricing.items():
        if alan in ('prompt', 'completion'):
            continue
        if deger is None or (isinstance(deger, str) and not deger.strip()):
            continue
        if not _sifir_fiyat(deger):
            return False
    return True


def _model_fiyat_kaniti(b: Dict[str, Any], model: str) -> Any:
    for alan in ('model_fiyatlari', 'model_pricing', 'prices'):
        fiyatlar = b.get(alan)
        if isinstance(fiyatlar, dict) and model in fiyatlar:
            return fiyatlar.get(model)
    return None


def ucret_durumu(ad: str, model: Optional[str] = None) -> str:
    """Saglayici/model ucret durumu: 'ucretsiz' | 'ucretli' | 'bilinmiyor'."""
    b = bilgi(ad)
    if not b:
        return BILINMIYOR
    a = str(ad or '').strip().lower()
    if not model:
        # Model bazli fiyat kaniti olmadan saglayici seviyesindeki
        # 'ucretsiz' bilgisi tek basina yetmez.
        if a in ('gemini', 'zai_glm', 'groq'):
            return BILINMIYOR
        return b.get('ucret', BILINMIYOR)
    if a == 'ollama':
        return b.get('ucret', BILINMIYOR)
    if a == 'openrouter':
        return UCRETSIZ if str(model).endswith(':free') else UCRETLI
    fiyat = _model_fiyat_kaniti(b, model)
    if fiyat is None:
        return BILINMIYOR
    if not isinstance(fiyat, dict):
        return BILINMIYOR
    if not ('prompt' in fiyat and 'completion' in fiyat):
        return BILINMIYOR
    if not (_sifir_fiyat(fiyat.get('prompt'))
            and _sifir_fiyat(fiyat.get('completion'))):
        return UCRETLI
    return UCRETSIZ if _fiyat_uygun(fiyat) else UCRETLI


def ucretsiz_mi(ad: str, model: Optional[str] = None) -> bool:
    return ucret_durumu(ad, model) == UCRETSIZ


def varsayilan_izinli(ad: str, model: Optional[str] = None) -> bool:
    """Saglayici varsayilan olarak kullanilabilir mi?

    Yalnizca ucretsiz oldugu DOGRULANMIS saglayicilar varsayilan ETKIN olur.
    Politika gereği engelli saglayicilar hicbir zaman izinli degildir.
    """
    a = str(ad or '').strip().lower()
    if a in POLITIKA_ENGELLI:
        return False
    if not saglayici_var(a):
        return False
    return ucretsiz_mi(a, model)


def aciklama(ad: str) -> str:
    b = bilgi(ad)
    return b.get('aciklama', '')


def ucret_etiketi(ad: str, model: Optional[str] = None) -> str:
    d = ucret_durumu(ad, model)
    return {'ucretsiz': 'Ucretsiz',
            'ucretli': 'Ucretli',
            'bilinmiyor': 'Fiyati bilinmiyor'}.get(d, 'Fiyati bilinmiyor')


def sirali_liste() -> List[Dict[str, Any]]:
    """Kurulum sihirbazinda gosterilecek saglayici tanimlari."""
    out = []
    for ad in KURULUM_SIRASI:
        if ad in KATALOG:
            out.append(dict(KATALOG[ad]))
    return out
