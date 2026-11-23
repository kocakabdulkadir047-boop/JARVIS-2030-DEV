#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JARVIS - Yapay Zeka Beyinleri kayit defteri.

GOREV 2.8 / Bolum 1 ve 4:
  * Kullanicinin ekledigi beyinlerin SIRALI listesi.
  * Persist: config/jarvis_beyinler.json
  * BU DOSYADA API ANAHTARI BULUNMAZ. Anahtarlar yalnizca
    jarvis_saglayici_guvenli.py (DPAPI) tarafinda tutulur.
  * Durum etiketleri:
      BAGLI | KULLANILABILIR | HATA | KOTA SINIRI | DEVRE DISI | TEST EDILMEDI
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

import jarvis_saglayici_kanon as kanon

__all__ = [
    'yukle', 'kaydet', 'beyinler', 'ekle', 'sil', 'guncelle', 'sira_degistir',
    'yukari_tas', 'asagi_tas', 'aktif_beyin', 'aktif_et', 'kurulum_gerekiyor_mi',
    'kurulum_tamamlandi', 'saglayici_sirasi', 'durum_guncelle',
    'son_basarili_guncelle', 'beyin_bul', 'kayit_yolu', 'temizle',
]

DURUM_BAGLI = 'BAGLI'
DURUM_KULLANILABILIR = 'KULLANILABILIR'
DURUM_HATA = 'HATA'
DURUM_KOTA = 'KOTA SINIRI'
DURUM_DEVRE_DISI = 'DEVRE DISI'
DURUM_TEST_EDILMEDI = 'TEST EDILMEDI'

DURUMLAR = (DURUM_BAGLI, DURUM_KULLANILABILIR, DURUM_HATA,
             DURUM_KOTA, DURUM_DEVRE_DISI, DURUM_TEST_EDILMEDI)

SURUM = 1


# ---------------------------------------------------------------------------
# Konum
# ---------------------------------------------------------------------------
def _proje_koku() -> str:
    if getattr(__import__('sys'), 'frozen', False):
        return os.path.dirname(os.path.abspath(__import__('sys').executable))
    return os.path.dirname(os.path.abspath(__file__))


def kayit_yolu() -> str:
    return os.path.join(_proje_koku(), 'config', 'jarvis_beyinler.json')


# ---------------------------------------------------------------------------
# Yukleme / kaydetme
# ---------------------------------------------------------------------------
def _bos_kayit() -> Dict[str, Any]:
    return {'surum': SURUM, 'kurulum_tamamlandi': False, 'beyinler': []}


def yukle() -> Dict[str, Any]:
    """Beyin kayit defterini okur (yoksa bos kayit dondurur)."""
    yol = kayit_yolu()
    try:
        if os.path.isfile(yol):
            with open(yol, 'r', encoding='utf-8') as f:
                veri = json.load(f)
            if isinstance(veri, dict):
                veri.setdefault('surum', SURUM)
                veri.setdefault('kurulum_tamamlandi', False)
                b = veri.get('beyinler')
                veri['beyinler'] = b if isinstance(b, list) else []
                return veri
    except Exception:
        pass
    return _bos_kayit()


def kaydet(veri: Dict[str, Any]) -> bool:
    """Beyin kayit defterini yazar (atomik). API anahtari YAZILMAZ."""
    try:
        yol = kayit_yolu()
        klasor = os.path.dirname(yol)
        if klasor and not os.path.isdir(klasor):
            os.makedirs(klasor, exist_ok=True)
        fd, gecici = tempfile.mkstemp(dir=klasor or '.', prefix='.beyin_')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(veri, f, ensure_ascii=False, indent=2)
            try:
                os.replace(gecici, yol)
            except OSError:
                shutil.copy2(gecici, yol)
                os.remove(gecici)
        finally:
            if os.path.exists(gecici):
                try:
                    os.remove(gecici)
                except OSError:
                    pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Sorgular
# ---------------------------------------------------------------------------
def beyinler() -> List[Dict[str, Any]]:
    """Oncelik sirasiyla beyin listesi."""
    return list(yukle().get('beyinler') or [])


def beyin_bul(beyin_id: str) -> Optional[Dict[str, Any]]:
    for b in beyinler():
        if b.get('id') == beyin_id:
            return b
    return None


def kurulum_tamamlandi() -> bool:
    return bool(yukle().get('kurulum_tamamlandi'))


def kurulum_gerekiyor_mi() -> bool:
    """Ilk acilista kurulum sihirbazi gosterilmeli mi?

    Kurulum daha once tamamlanmadiysa VE kayitli beyin yoksa evet.
    """
    veri = yukle()
    if veri.get('kurulum_tamamlandi') and (veri.get('beyinler') or []):
        return False
    return not (veri.get('beyinler') or [])


def aktif_beyin() -> Optional[Dict[str, Any]]:
    """Aktif (birincil) beyin."""
    veri = yukle()
    aktif_id = veri.get('aktif_beyin_id')
    for b in (veri.get('beyinler') or []):
        if b.get('id') == aktif_id:
            return b
    bl = veri.get('beyinler') or []
    return bl[0] if bl else None


def saglayici_sirasi() -> List[str]:
    """Router'in denemesi gereken saglayici sirasi (beyinlerden).

    Kurulum yapilmadiysa kanon varsayilan sirasi doner.
    """
    veri = yukle()
    bl = veri.get('beyinler') or []
    if not bl:
        return ['gemini', 'groq', 'openrouter']
    sira = []
    for b in bl:
        if not b.get('etkin', True):
            continue
        ad = str(b.get('saglayici') or '').strip().lower()
        if not ad or ad in sira:
            continue
        sira.append(ad)
    return sira


# ---------------------------------------------------------------------------
# Degisiklikler
# ---------------------------------------------------------------------------
def ekle(saglayici: str, model: str = '', etiket: str = '',
         ucret: str = '', kullanici_onayi: bool = False,
         etkin: bool = True) -> Optional[Dict[str, Any]]:
    """Yeni beyin ekler. Anahtar BURAYA girilmez (ayri kanal: guvenli depo)."""
    ad = str(saglayici or '').strip().lower()
    if not kanon.saglayici_var(ad):
        return None
    m = model or kanon.varsayilan_model(ad)
    u = ucret or kanon.ucret_durumu(ad, m)
    veri = yukle()
    bl = veri.get('beyinler') or []
    # Ayni saglayici+model cifti iki kez eklenmesin
    for b in bl:
        if (b.get('saglayici') == ad and b.get('model') == m):
            return b
    beyin = {
        'id': 'b%02d%s' % (len(bl) + 1, uuid.uuid4().hex[:6]),
        'saglayici': ad,
        'model': m,
        'etiket': etiket or (kanon.etiket(ad) + ' ' + str(m)),
        'ucret': u,
        'oncelik': len(bl) + 1,
        'etkin': bool(etkin) and ad not in kanon.POLITIKA_ENGELLI,
        'kullanici_onayi': bool(kullanici_onayi),
        'durum': DURUM_TEST_EDILMEDI,
        'son_basarili': None,
        'son_deneme': None,
        'eklendi': int(time.time()),
    }
    bl.append(beyin)
    veri['beyinler'] = bl
    if not veri.get('aktif_beyin_id'):
        veri['aktif_beyin_id'] = beyin['id']
    kaydet(veri)
    return beyin


def sil(beyin_id: str) -> bool:
    """Beyni siler (kayitli API anahtari SILINMEZ - ayri islem)."""
    veri = yukle()
    bl = veri.get('beyinler') or []
    yeni = [b for b in bl if b.get('id') != beyin_id]
    if len(yeni) == len(bl):
        return False
    veri['beyinler'] = yeni
    if veri.get('aktif_beyin_id') == beyin_id:
        veri['aktif_beyin_id'] = yeni[0]['id'] if yeni else None
    kaydet(veri)
    return True


def guncelle(beyin_id: str, **alanlar) -> Optional[Dict[str, Any]]:
    """Beyin alanlarini gunceller (anahtar alani burada guncellenmez)."""
    veri = yukle()
    bl = veri.get('beyinler') or []
    for b in bl:
        if b.get('id') == beyin_id:
            for k, v in alanlar.items():
                if k in ('id',):
                    continue
                b[k] = v
            kaydet(veri)
            return b
    return None


def sira_degistir(beyin_id: str, yeni_sira: int) -> bool:
    """Beyni listede yeni siraya tasir."""
    veri = yukle()
    bl = veri.get('beyinler') or []
    idx = None
    for i, b in enumerate(bl):
        if b.get('id') == beyin_id:
            idx = i
            break
    if idx is None:
        return False
    beyin = bl.pop(idx)
    yeni_sira = max(0, min(int(yeni_sira), len(bl)))
    bl.insert(yeni_sira, beyin)
    veri['beyinler'] = bl
    if veri.get('aktif_beyin_id') == beyin_id:
        veri['aktif_beyin_id'] = bl[0]['id'] if bl else None
    kaydet(veri)
    return True


def yukari_tas(beyin_id: str) -> bool:
    bl = beyinler()
    for i, b in enumerate(bl):
        if b.get('id') == beyin_id:
            return sira_degistir(beyin_id, max(0, i - 1))
    return False


def asagi_tas(beyin_id: str) -> bool:
    bl = beyinler()
    for i, b in enumerate(bl):
        if b.get('id') == beyin_id:
            return sira_degistir(beyin_id, min(len(bl) - 1, i + 1))
    return False


def aktif_et(beyin_id: str) -> bool:
    veri = yukle()
    bl = veri.get('beyinler') or []
    if not any(b.get('id') == beyin_id for b in bl):
        return False
    veri['aktif_beyin_id'] = beyin_id
    kaydet(veri)
    return True


def durum_guncelle(beyin_id: str, durum: str) -> bool:
    if durum not in DURUMLAR:
        return False
    return bool(guncelle(beyin_id, durum=durum))


def son_basarili_guncelle(beyin_id: str) -> bool:
    return bool(guncelle(beyin_id, son_basarili=int(time.time()),
                         durum=DURUM_KULLANILABILIR))


def kurulum_bitir() -> bool:
    veri = yukle()
    veri['kurulum_tamamlandi'] = True
    return kaydet(veri)


def temizle() -> bool:
    return kaydet(_bos_kayit())
