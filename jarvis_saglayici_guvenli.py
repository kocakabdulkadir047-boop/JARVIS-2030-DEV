#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JARVIS - Guvenli API anahtari saklama (Windows DPAPI).

GOREV 2.8 / Bolum 3:
  * API anahtarlari Windows DPAPI (CryptProtectData) ile SIFRELENIR.
  * Sifreli veri TEK bir dosyada tutulur; dosyanin TAMAMI sifreli blob'dir
    (icinde JSON: {saglayici_adi: anahtar}).
  * Anahtar HICBIR zaman duz metin olarak yazilmaz, loglanmaz, exception
    mesajina girmez, GUI'de sadece parola alani olarak gosterilir.
  * DPAPI anahtari kullanici/oturum kapsamlidir: baska kullanici acamaz.
  * Geri yuklenemezse (kullanici degisti, profil silindi) anahtarlar kaybolur;
    bu durumda kullaniciya "anahtar girin" mesaji gosterilir.
  * Duz metin YEDEK OLUSTURULMAZ.

Dosya konumu: <proje>/config/.jarvis_guvenli_anahtarlar (gizli, sifreli)
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import sys
import tempfile
from ctypes import wintypes
from typing import Dict, List, Optional

__all__ = [
    'kaydet', 'oku', 'sil', 'var_mi', 'tum_anahtarlar', 'saglayici_listesi',
    'temizle', 'depolama_yolu', 'guvenli_hata_mesaji',
]

# ---------------------------------------------------------------------------
# Platform kontrolu
# ---------------------------------------------------------------------------
_IS_WINDOWS = os.name == 'nt'

if _IS_WINDOWS:
    try:
        _CRYPT32 = ctypes.windll.crypt32
        _KERNEL32 = ctypes.windll.kernel32
        _CRYPTPROTECTUI = getattr(ctypes.windll, 'crypt32ui', None)
    except Exception:  # pragma: no cover
        _CRYPT32 = None
        _KERNEL32 = None
        _CRYPTPROTECTUI = None
else:  # pragma: no cover
    _CRYPT32 = _KERNEL32 = _CRYPTPROTECTUI = None


class _BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD),
                ('pbData', ctypes.POINTER(ctypes.c_char))]


class GuvenliDepolamaHatasi(Exception):
    """Guvenli depolama islemi basarisiz."""


# ---------------------------------------------------------------------------
# Dosya yolu
# ---------------------------------------------------------------------------
def _proje_koku() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def depolama_yolu() -> str:
    """Sifreli anahtar deposunun tam yolu."""
    return os.path.join(_proje_koku(), 'config', '.jarvis_guvenli_anahtarlar')


# ---------------------------------------------------------------------------
# DPAPI sarmalayicilari
# ---------------------------------------------------------------------------
def _sifrele(veri: bytes, açiklama: str = 'JARVIS') -> bytes:
    if not _IS_WINDOWS or _CRYPT32 is None:
        raise GuvenliDepolamaHatasi(
            'Windows DPAPI bu sistemde kullanilamiyor.')
    giris = _BLOB()
    giris.cbData = len(veri)
    giris.pbData = ctypes.cast(ctypes.create_string_buffer(veri),
                               ctypes.POINTER(ctypes.c_char))
    cikis = _BLOB()
    # NOT: ctypes, DLL disa aktarilan parametre ADLARINI bilmez; bu yuzden
    # konumel (positional) cagrim KULLANILIR.
    #   CryptProtectData(pDataIn, szDataDescr, pOptionalEntropy, pvReserved,
    #                    pPromptStruct, dwFlags, pbData)
    basarili = _CRYPT32.CryptProtectData(
        ctypes.byref(giris), açiklama, None, None, None, 0x01,
        ctypes.byref(cikis))
    if not basarili:
        raise GuvenliDepolamaHatasi('Anahtar sifrelenemedi (DPAPI hatasi).')
    try:
        return ctypes.string_at(cikis.pbData, cikis.cbData)
    finally:
        _KERNEL32.LocalFree(cikis.pbData)


def _coz(veri: bytes, açiklama: str = 'JARVIS') -> bytes:
    if not _IS_WINDOWS or _CRYPT32 is None:
        raise GuvenliDepolamaHatasi(
            'Windows DPAPI bu sistemde kullanilamiyor.')
    giris = _BLOB()
    giris.cbData = len(veri)
    giris.pbData = ctypes.cast(ctypes.create_string_buffer(veri),
                               ctypes.POINTER(ctypes.c_char))
    cikis = _BLOB()
    # CryptUnprotectData(pDataIn, ppszDataDescr, pOptionalEntropy,
    #                    pvReserved, pPromptStruct, dwFlags, pbData)
    basarili = _CRYPT32.CryptUnprotectData(
        ctypes.byref(giris), None, None, None, None, 0x01, ctypes.byref(cikis))
    if not basarili:
        raise GuvenliDepolamaHatasi(
            'Anahtar cozulemedi (kullanici degismis veya dosya bozulmus).')
    try:
        return ctypes.string_at(cikis.pbData, cikis.cbData)
    finally:
        _KERNEL32.LocalFree(cikis.pbData)


# ---------------------------------------------------------------------------
# Duz metin JSON -> sifreli blob dosyasi
# ---------------------------------------------------------------------------
def _oku_ham() -> Dict[str, str]:
    yol = depolama_yolu()
    if not os.path.isfile(yol):
        return {}
    try:
        with open(yol, 'rb') as f:
            blob = f.read()
        if not blob:
            return {}
        duz = _coz(blob).decode('utf-8')
        veri = json.loads(duz)
        return {str(k): str(v) for k, v in veri.items() if v}
    except GuvenliDepolamaHatasi:
        raise
    except Exception:
        return {}


def _yaz_ham(sozluk: Dict[str, str]) -> None:
    yol = depolama_yolu()
    klasor = os.path.dirname(yol)
    if klasor and not os.path.isdir(klasor):
        os.makedirs(klasor, exist_ok=True)
    if not sozluk:
        if os.path.isfile(yol):
            try:
                os.remove(yol)
            except OSError:
                pass
        return
    duz = json.dumps(sozluk, ensure_ascii=False).encode('utf-8')
    blob = _sifrele(duz)
    # Atomik yazim
    fd, gecici = tempfile.mkstemp(dir=klasor or '.', prefix='.jarvis_sec_')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(blob)
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


# ---------------------------------------------------------------------------
# Genel API
# ---------------------------------------------------------------------------
def kaydet(saglayici_adi: str, anahtar: str) -> bool:
    """Saglayici API anahtarini guvenli sekilde saklar.

    Donus: True (basarili) / False (hata - anahtar DEGISTIRILMEZ).
    """
    ad = str(saglayici_adi or '').strip().lower()
    if not ad:
        return False
    try:
        veri = _oku_ham()
    except GuvenliDepolamaHatasi:
        # Bozuk/erisilemez depo: uzerine yazma, kullaniciya bildir.
        return False
    if anahtar is None:
        veri.pop(ad, None)
    else:
        metin = str(anahtar).strip()
        if not metin:
            veri.pop(ad, None)
        else:
            veri[ad] = metin
    try:
        _yaz_ham(veri)
        return True
    except Exception:
        return False


def oku(saglayici_adi: str) -> Optional[str]:
    """Saglayici API anahtarini cozup dondurur (yoksa None)."""
    ad = str(saglayici_adi or '').strip().lower()
    if not ad:
        return None
    try:
        return _oku_ham().get(ad)
    except GuvenliDepolamaHatasi:
        return None


def var_mi(saglayici_adi: str) -> bool:
    """Saglayici icin kayitli anahtar var mi (acmadan)."""
    ad = str(saglayici_adi or '').strip().lower()
    if not ad:
        return False
    try:
        return bool(_oku_ham().get(ad))
    except GuvenliDepolamaHatasi:
        return False


def sil(saglayici_adi: str) -> bool:
    """Saglayici anahtarini siler."""
    ad = str(saglayici_adi or '').strip().lower()
    if not ad:
        return False
    try:
        veri = _oku_ham()
    except GuvenliDepolamaHatasi:
        return False
    if ad not in veri:
        return False
    veri.pop(ad, None)
    try:
        _yaz_ham(veri)
        return True
    except Exception:
        return False


def tum_anahtarlar() -> Dict[str, str]:
    """TUM anahtarlari cozup dondurur. YALNIZCA dahili is mantigi kullanir.

    UYARI: Donen degerler duz metindir; loglanmamalidir.
    """
    try:
        return _oku_ham()
    except GuvenliDepolamaHatasi:
        return {}


def saglayici_listesi() -> List[str]:
    """Anahtari kayitli saglayici adlari (degerler acilmaz)."""
    try:
        return sorted(_oku_ham().keys())
    except GuvenliDepolamaHatasi:
        return []


def temizle() -> bool:
    """Tum anahtarlari siler (tum depoyu)."""
    try:
        _yaz_ham({})
        return True
    except Exception:
        return False


def guvenli_hata_mesaji(saglayici_adi: str) -> str:
    """Kullaniciya gosterilecek, ANAHTAR ICERMEYEN hata mesaji."""
    return ("%s icin kayitli anahtar cozulemedi. "
            "Lutfen Ayarlar > Yapay Zeka Beyinleri bolumunden anahtari "
            "yeniden girin." % str(saglayici_adi or 'Saglayici'))
