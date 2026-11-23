# -*- coding: utf-8 -*-
"""J.A.R.V.I.S - SONSUZ MOD v2 (sifirdan, tek modul).

Tek giris noktasi: calistir(talep, log=None, ses=None, ekran_al=True)

Bu modul eski dagilmis SONSUZ yamalarinin yerine gecer. Ozellikler:

* %100 sohbet: her mesaja mutlaka yazili + sesli cevap verir.
* Tum oyunlari oynama: pencere + ekran goruntusu + gorsel AI hamlesi.
  Insan benzeri hiz, tekrar yok, molalar -> ban riski azaltilir.
* AFK: her saniye oyun penceresi kontrolu; hareketsizlikte otomatik
  hareket; tek oturumda en fazla 15 dakika.
* Hatirlatici: saniye/dakika/saat ve saat:dd; kalici (config).
* Oyun istegi: arastirir, platform secer (OpenCode/Claude/Freebuff),
  uygulamayi acar, arka planda dahi hedef ekrani yakalar, sohbeti acar,
  "merhaba"yi 0.2 saniyede harf harf yazar, detayli brief'i gonderir.
  Ayrica oyunu yerelde uretir ve EXE olarak derler.
* Google Maps / HTML harita / konum acma.
* Her saniye ekran kontrolu; tek dosyaya yazar (disk sisirmez).
* Arka plan penceresi ekran goruntusu: PrintWindow(PW_RENDERFULLCONTENT).
* PowerShell ozgurlugu: araclar basarisiz olursa komutu kendisi calistirir.
* 3D: sketchfab.com + 3dmodels.org/tr arar, ucretsizleri analiz eder,
  indirir ve hedef projeye aktarir.
* Gorsel/video uretimi + uzerinde KOPYALA dugmesi olan goruntuleyici.
* Fiyat takibi: Trendyol, Amazon, Vatan, Idefix, N11. Ucuzlarsa
  "ucuza girdi! (fiyat)" + URL; pahalilasirsa "çok pahalılaştı!!" + URL.
  JARVIS kapaliyken kacirilan degisim acilista bildirilir.
* Kendini gelistirme: olay/hata kaydi, oneri uretimi; yapay sinir yok.
"""

import base64
import ctypes
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

WIN = os.name == 'nt'

try:
    import jarvis_usta as _ju
except Exception:  # pragma: no cover
    _ju = None

try:
    if _ju is not None:
        _KOK = getattr(_ju, '_KOK', '') or ''
    else:
        _KOK = ''
except Exception:
    _KOK = ''
if not _KOK:
    if getattr(sys, 'frozen', False):
        _KOK = os.path.dirname(os.path.abspath(sys.executable))
    else:
        _KOK = os.path.dirname(os.path.abspath(__file__))

_CFG = os.path.join(_KOK, 'config', 'sonsuz2')
_URETIM = os.path.join(_KOK, 'uretim')
_VARLIK = os.path.join(_KOK, 'varliklar', '3d')
for _p in (_CFG, _URETIM, _VARLIK):
    try:
        os.makedirs(_p, exist_ok=True)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Durum
# ---------------------------------------------------------------------------
_KILIT = threading.Lock()
_HATIRLATILAR = []
_HATIRLAT_KILIT = threading.Lock()
_HATIRLAT_THREAD = None
_EKRAN_IZLE = False
_EKRAN_THREAD = None
_EKRAN_LOG = None
_AFK = {'aktif': False, 'log': None, 'ses': None, 'basladi': 0.0,
        'thread': None, 'son_hareket': 0.0}
_AFK_SURE = 15 * 60.0
_AFK_ESIK = 5.0
_FIYAT_THREAD = None
_FIYAT_LOG = None
_FIYAT_SON = 0.0
_FIYAT_ARALIK = 15 * 60.0
_SOHBET_SAY = 0
_SON_HATA = ''

_OYUN_DISLA = (
    'jarvis', 'program manager', 'explorer', 'google chrome', 'chrome',
    'microsoft edge', 'edge', 'firefox', 'opera', 'brave', 'yandex',
    'visual studio', 'vs code', 'notepad', 'not defteri', 'word', 'excel',
    'powerpoint', 'outlook', 'discord', 'spotify', 'whatsapp', 'telegram',
    'settings', 'ayarlar', 'denetim masasi', 'control panel', 'task manager',
    'gorev yoneticisi', 'cmd.exe', 'powershell', 'windows terminal',
    'file explorer', 'dosya gezgini', 'steam', 'steam library',
    'opencode', 'claude', 'freebuff', 'ea app', 'ubisoft connect',
    'battle.net', 'epic games launcher', 'rockstar games launcher',
    'gog galaxy', 'itch.io', 'xbox', 'microsoft store', 'twitch',
)


# ---------------------------------------------------------------------------
# Temel yardimcilar
# ---------------------------------------------------------------------------
def _yaz(log, metin):
    try:
        if _ju is not None:
            _ju._yaz(log, metin)
            return
    except Exception:
        pass
    try:
        print('[SONSUZ2] ' + str(metin))
    except Exception:
        pass


def _hata(log, metin):
    global _SON_HATA
    _SON_HATA = str(metin)[:400]
    try:
        if _ju is not None:
            _ju._hata(log, metin)
            return
    except Exception:
        pass
    _yaz(log, 'ERR: ' + str(metin))


def _sesle(ses, metin):
    metin = str(metin or '').strip()
    if not metin:
        return
    # TEK SES YOLU: merkezi canli ses yoneticisi (Gemini TTS).
    # SAPI / pyttsx3 / PowerShell System.Speech ASLA.
    try:
        import jarvis_speech_manager as _sm
        if _sm.konus(metin, kaynak='sonsuz'):
            return
    except Exception:
        pass
    # Geriye uyumluluk: UI/canli callback.
    try:
        if callable(ses):
            ses(metin)
            return
    except Exception:
        pass
    try:
        if _ju is not None and hasattr(_ju, '_sesle'):
            _ju._sesle(None, metin)
            return
    except Exception:
        pass
    for mod, fn in (('jarvis_canli_ses', 'konus'),
                    ('jarvis_live_ses', 'konus'),
                    ('jarvis_ses_canli', 'soyle')):
        try:
            m = __import__(mod)
            f = getattr(m, fn, None)
            if callable(f):
                f(metin)
                return
        except Exception:
            pass
    try:
        print('[SES:CANLI_BEKLIYOR] ' + metin[:200])
    except Exception:
        pass


def _json_oku(yol, varsayilan):
    try:
        with open(yol, 'r', encoding='utf-8', errors='ignore') as f:
            return json.load(f)
    except Exception:
        return varsayilan


def _json_yaz(yol, veri):
    try:
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        gecici = yol + '.tmp'
        with open(gecici, 'w', encoding='utf-8') as f:
            json.dump(veri, f, ensure_ascii=False, indent=1)
        os.replace(gecici, yol)
        return True
    except Exception:
        return False


def _slug(metin, uzun=40):
    s = str(metin or '').strip().lower()
    for a, b in (('ç', 'c'), ('ğ', 'g'), ('ı', 'i'), ('ö', 'o'),
                 ('ş', 's'), ('ü', 'u'), ('â', 'a'), ('î', 'i')):
        s = s.replace(a, b)
    s = re.sub(r'[^a-z0-9]+', '_', s).strip('_')
    return (s or 'jarvis')[:uzun]


def _ai(soru, sistem=None, zaman=45, max_tokens=900, sicaklik=0.4):
    """AI zinciri; bos cevap gelirse ikinci kez dener."""
    for _ in range(2):
        try:
            import jarvis_yetenek as yt
            cevap, _sag = yt.ai_sor_ex(
                soru, sistem=sistem, zaman=zaman, max_tokens=max_tokens,
                sicaklik=sicaklik)
            cevap = str(cevap or '').strip()
            if cevap:
                return cevap
        except Exception:
            pass
        try:
            import jarvis_yetenek as yt
            cevap = str(yt.ai_sor(soru, sistem=sistem, zaman=zaman) or '').strip()
            if cevap:
                return cevap
        except Exception:
            pass
        time.sleep(1.0)
    return ''


def _vizyon(yol, istem, zaman=60):
    try:
        import jarvis_ergonomi as je
        return str(je.gemini_vizyon(yol, istem, zaman=zaman) or '').strip()
    except Exception:
        return ''


def _insansi_bekleme(taban, alt=0.7, ust=1.4):
    try:
        return max(0.03, float(taban) * random.uniform(alt, ust))
    except Exception:
        return max(0.03, float(taban))


def _ps_calistir(komut, log=None, timeout=240, cwd=None):
    """PowerShell ozgurlugu; tehlikeli komutlar kirmizi RED olarak doner."""
    if _ju is None:
        return {'ok': False, 'kod': -1, 'cikti': 'jarvis_usta yok', 'red': False}
    _yaz(log, 'SYS: PS> ' + str(komut)[:500])
    try:
        r = _ju._ps(komut, cwd=cwd, timeout=timeout)
    except Exception as e:
        _hata(log, 'PowerShell hatasi: ' + repr(e)[:200])
        return {'ok': False, 'kod': -1, 'cikti': repr(e), 'red': False}
    if r.get('red'):
        _hata(log, 'PowerShell IPTAL - REDDEDILDI (komut, guvenlik): '
              + str(komut)[:300])
        return r
    if r.get('ok'):
        cikti = str(r.get('cikti') or '')
        _yaz(log, 'SYS: PS OK (kod 0)' + (': ' + cikti[:400] if cikti else ''))
    else:
        _hata(log, 'PowerShell IPTAL - basarisiz (komut, kod %s): %s | %s' % (
            r.get('kod'), str(komut)[:300], str(r.get('cikti') or '')[:400]))
    return r


# ---------------------------------------------------------------------------
# Win32: pencere, ekran goruntusu, girdi
# ---------------------------------------------------------------------------
if WIN:
    from ctypes import wintypes as _wt

    class _BMIH(ctypes.Structure):
        _fields_ = [
            ('biSize', _wt.DWORD), ('biWidth', _wt.LONG),
            ('biHeight', _wt.LONG), ('biPlanes', _wt.WORD),
            ('biBitCount', _wt.WORD), ('biCompression', _wt.DWORD),
            ('biSizeImage', _wt.DWORD), ('biXPelsPerMeter', _wt.LONG),
            ('biYPelsPerMeter', _wt.LONG), ('biClrUsed', _wt.DWORD),
            ('biClrImportant', _wt.DWORD),
        ]

    class _LII(ctypes.Structure):
        _fields_ = [('cbSize', _wt.UINT), ('dwTime', _wt.DWORD)]


def _pencere_listesi():
    if not WIN:
        return []
    out = []
    try:
        u = ctypes.windll.user32

        @ctypes.WINFUNCTYPE(_wt.BOOL, _wt.HWND, _wt.LPARAM)
        def _cb(hwnd, _lp):
            try:
                if not u.IsWindowVisible(hwnd):
                    return True
                n = u.GetWindowTextLengthW(hwnd)
                if n <= 0:
                    return True
                b = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, b, n + 1)
                if b.value.strip():
                    out.append((int(hwnd), b.value.strip()))
            except Exception:
                pass
            return True

        u.EnumWindows(_cb, 0)
    except Exception:
        pass
    return out


def _pencere_bul(parcalar):
    if isinstance(parcalar, str):
        parcalar = (parcalar,)
    parcalar = tuple(str(p).lower() for p in (parcalar or ()) if str(p).strip())
    if not parcalar:
        return 0
    for hwnd, ad in _pencere_listesi():
        if any(p in ad.lower() for p in parcalar):
            return hwnd
    return 0


def _pencere_on(hwnd):
    if not WIN or not hwnd:
        return False
    try:
        u = ctypes.windll.user32
        h = _wt.HWND(int(hwnd))
        if u.IsIconic(h):
            u.ShowWindow(h, 9)
        u.BringWindowToTop(h)
        u.SetForegroundWindow(h)
        try:
            u.SetFocus(h)
        except Exception:
            pass
        time.sleep(0.35)
        return True
    except Exception:
        return False


def _pencere_rect(hwnd):
    if not WIN or not hwnd:
        return None
    try:
        r = _wt.RECT()
        if not ctypes.windll.user32.GetWindowRect(_wt.HWND(int(hwnd)),
                                                  ctypes.byref(r)):
            return None
        return (int(r.left), int(r.top), int(r.right), int(r.bottom))
    except Exception:
        return None


def _pencere_sinifi(hwnd):
    if not WIN or not hwnd:
        return ''
    try:
        b = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(_wt.HWND(int(hwnd)), b, 256)
        return b.value
    except Exception:
        return ''


def _pencere_kapat(hwnd):
    try:
        if WIN and hwnd:
            ctypes.windll.user32.PostMessageW(_wt.HWND(int(hwnd)), 0x0010, 0, 0)
            return True
    except Exception:
        pass
    return False


def _bmp_yaz(yol, w, h, veri):
    satir = int(w) * 4
    boyut = satir * int(h)
    bas = 54
    try:
        with open(yol, 'wb') as f:
            f.write(b'BM')
            f.write((bas + boyut).to_bytes(4, 'little'))
            f.write((0).to_bytes(4, 'little'))
            f.write(bas.to_bytes(4, 'little'))
            f.write((40).to_bytes(4, 'little'))
            f.write(int(w).to_bytes(4, 'little', signed=True))
            f.write(int(h).to_bytes(4, 'little', signed=True))
            f.write((1).to_bytes(2, 'little'))
            f.write((32).to_bytes(2, 'little'))
            f.write((0).to_bytes(4, 'little'))
            f.write(boyut.to_bytes(4, 'little'))
            f.write((2835).to_bytes(4, 'little'))
            f.write((2835).to_bytes(4, 'little'))
            f.write((0).to_bytes(4, 'little'))
            f.write((0).to_bytes(4, 'little'))
            f.write(veri)
        return yol
    except Exception:
        return ''


def _dib_al(mdc, bmp, w, h, yol_bmp):
    try:
        g = ctypes.windll.gdi32
        bi = _BMIH()
        bi.biSize = ctypes.sizeof(_BMIH)
        bi.biWidth = int(w)
        bi.biHeight = int(h)
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0
        bi.biSizeImage = int(w) * int(h) * 4
        buf = ctypes.create_string_buffer(int(w) * int(h) * 4)
        g.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, _wt.UINT,
                                _wt.UINT, ctypes.c_void_p,
                                ctypes.POINTER(_BMIH), _wt.UINT]
        g.GetDIBits.restype = ctypes.c_int
        n = g.GetDIBits(ctypes.c_void_p(mdc), ctypes.c_void_p(bmp), 0,
                        int(h), ctypes.byref(buf), ctypes.byref(bi), 0)
        if not n:
            return ''
        return _bmp_yaz(yol_bmp, w, h, buf.raw)
    except Exception:
        return ''


def _png_yap(yol):
    try:
        if not yol or not os.path.isfile(yol):
            return yol
        if str(yol).lower().endswith('.png'):
            return yol
        hedef = os.path.splitext(str(yol))[0] + '.png'
        # Eski kareyi sil: aksi halde jarvis_gorsel var olan PNG'yi
        # yeniden cevirmeden dondurur ve goruntu donar.
        try:
            if os.path.isfile(hedef):
                os.remove(hedef)
        except Exception:
            pass
        import jarvis_gorsel as jg
        return jg.png_haline(yol) or yol
    except Exception:
        return yol


def _pencere_yakala(hwnd, yol_bmp):
    """Arka plandaki pencereyi bile PrintWindow ile yakalar."""
    if not WIN:
        return ''
    try:
        u = ctypes.windll.user32
        g = ctypes.windll.gdi32
        g.CreateCompatibleDC.restype = ctypes.c_void_p
        g.CreateCompatibleBitmap.restype = ctypes.c_void_p
        g.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        g.SelectObject.restype = ctypes.c_void_p
        u.GetWindowDC.restype = ctypes.c_void_p
        d = _pencere_rect(hwnd)
        if not d:
            return ''
        w = int(d[2] - d[0])
        h = int(d[3] - d[1])
        if w < 40 or h < 40:
            return ''
        hdc = u.GetWindowDC(_wt.HWND(int(hwnd)))
        if not hdc:
            return ''
        mdc = g.CreateCompatibleDC(ctypes.c_void_p(hdc))
        bmp = g.CreateCompatibleBitmap(ctypes.c_void_p(hdc), w, h)
        if not mdc or not bmp:
            return ''
        eski = g.SelectObject(ctypes.c_void_p(mdc), ctypes.c_void_p(bmp))
        ok = False
        for flag in (2, 1, 0):
            try:
                if u.PrintWindow(_wt.HWND(int(hwnd)),
                                 ctypes.c_void_p(mdc), flag):
                    ok = True
                    break
            except Exception:
                pass
        if not ok:
            try:
                g.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_void_p, ctypes.c_int,
                                     ctypes.c_int, _wt.DWORD]
                g.BitBlt(ctypes.c_void_p(mdc), 0, 0, w, h,
                         ctypes.c_void_p(hdc), 0, 0, 0x00CC0020)
            except Exception:
                pass
        yol = _dib_al(mdc, bmp, w, h, yol_bmp)
        try:
            g.SelectObject(ctypes.c_void_p(mdc), ctypes.c_void_p(eski))
            g.DeleteObject(ctypes.c_void_p(bmp))
            g.DeleteDC(ctypes.c_void_p(mdc))
            u.ReleaseDC(_wt.HWND(int(hwnd)), ctypes.c_void_p(hdc))
        except Exception:
            pass
        return yol
    except Exception:
        return ''


def _tam_ekran_yakala(yol_bmp):
    if not WIN:
        return ''
    try:
        u = ctypes.windll.user32
        g = ctypes.windll.gdi32
        g.CreateCompatibleDC.restype = ctypes.c_void_p
        g.CreateCompatibleBitmap.restype = ctypes.c_void_p
        g.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        g.SelectObject.restype = ctypes.c_void_p
        u.GetDC.restype = ctypes.c_void_p
        w = int(u.GetSystemMetrics(0))
        h = int(u.GetSystemMetrics(1))
        if w < 40 or h < 40:
            return ''
        hdc = u.GetDC(0)
        mdc = g.CreateCompatibleDC(ctypes.c_void_p(hdc))
        bmp = g.CreateCompatibleBitmap(ctypes.c_void_p(hdc), w, h)
        eski = g.SelectObject(ctypes.c_void_p(mdc), ctypes.c_void_p(bmp))
        g.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                             ctypes.c_int, ctypes.c_int, _wt.DWORD]
        g.BitBlt(ctypes.c_void_p(mdc), 0, 0, w, h, ctypes.c_void_p(hdc),
                 0, 0, 0x00CC0020)
        yol = _dib_al(mdc, bmp, w, h, yol_bmp)
        try:
            g.SelectObject(ctypes.c_void_p(mdc), ctypes.c_void_p(eski))
            g.DeleteObject(ctypes.c_void_p(bmp))
            g.DeleteDC(ctypes.c_void_p(mdc))
            u.ReleaseDC(0, ctypes.c_void_p(hdc))
        except Exception:
            pass
        return yol
    except Exception:
        return ''


def ekran_goruntusu(yol=None, hwnd=0):
    """Pencere (arka planda olsa bile) veya tam ekran goruntusu -> PNG yolu."""
    if not yol:
        yol = os.path.join(_CFG, 'ekran_%d.bmp' % int(time.time() * 1000))
    bmp = str(yol)
    if not bmp.lower().endswith('.bmp'):
        bmp = os.path.splitext(bmp)[0] + '.bmp'
    sonuc = ''
    if hwnd:
        sonuc = _pencere_yakala(hwnd, bmp)
    if not sonuc:
        sonuc = _tam_ekran_yakala(bmp)
    if not sonuc:
        return ''
    png = _png_yap(sonuc)
    # Disk sismesin: ara BMP'yi PNG'ye cevirdikten sonra sil.
    try:
        if png and png.lower().endswith('.png') and os.path.isfile(png) \
                and os.path.abspath(png) != os.path.abspath(sonuc):
            if os.path.getsize(png) > 0:
                os.remove(sonuc)
    except Exception:
        pass
    return png


def _son_girdi_sn():
    if not WIN:
        return 0.0
    try:
        lii = _LII()
        lii.cbSize = ctypes.sizeof(_LII)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0
        tick = ctypes.windll.kernel32.GetTickCount64()
        return max(0.0, (tick - int(lii.dwTime)) / 1000.0)
    except Exception:
        return 0.0


def _tus_bas(vk, hwnd=0, basili=0.15):
    """Foreground oyuna insan benzeri tus basimi."""
    if not WIN:
        return False
    try:
        u = ctypes.windll.user32
        if hwnd and int(u.GetForegroundWindow() or 0) != int(hwnd):
            try:
                u.PostMessageW(_wt.HWND(int(hwnd)), 0x0100, int(vk), 0)
                time.sleep(basili)
                u.PostMessageW(_wt.HWND(int(hwnd)), 0x0101, int(vk), 0)
                return True
            except Exception:
                pass
        u.keybd_event(int(vk), 0, 0, 0)
        time.sleep(_insansi_bekleme(basili, 0.8, 1.5))
        u.keybd_event(int(vk), 0, 2, 0)
        return True
    except Exception:
        return False


if WIN:
    class _MI(ctypes.Structure):
        _fields_ = [('dx', _wt.LONG), ('dy', _wt.LONG),
                    ('mouseData', _wt.DWORD), ('dwFlags', _wt.DWORD),
                    ('time', _wt.DWORD), ('dwExtraInfo', ctypes.c_size_t)]

    class _KI(ctypes.Structure):
        _fields_ = [('wVk', _wt.WORD), ('wScan', _wt.WORD),
                    ('dwFlags', _wt.DWORD), ('time', _wt.DWORD),
                    ('dwExtraInfo', ctypes.c_size_t)]

    class _IU(ctypes.Union):
        _fields_ = [('mi', _MI), ('ki', _KI)]

    class _INP(ctypes.Structure):
        _fields_ = [('type', _wt.DWORD), ('u', _IU)]


_VK = {
    'space': 0x20, 'shift': 0x10, 'ctrl': 0x11, 'alt': 0x12,
    'tab': 0x09, 'enter': 0x0D, 'esc': 0x1B, 'backspace': 0x08,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34, '5': 0x35,
    '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39, '0': 0x30,
}

try:  # pragma: no cover - yalnizca Windows
    if WIN:
        ctypes.windll.user32.SendInput.argtypes = [
            _wt.UINT, ctypes.POINTER(_INP), ctypes.c_int]
        ctypes.windll.user32.SendInput.restype = _wt.UINT
except Exception:
    pass


def _sendinput_key(tus, bas=True):
    """Normal Windows SendInput + scan code (hile/enjeksiyon yok)."""
    if not WIN:
        return False
    try:
        tus = str(tus).lower()
        vk = _VK.get(tus)
        if vk is None:
            if len(tus) == 1 and tus.isalnum():
                vk = ord(tus.upper())
            elif tus.startswith('f') and tus[1:].isdigit():
                vk = 0x6F + int(tus[1:])
            else:
                return False
        inp = _INP()
        inp.type = 1
        inp.u.ki.wVk = 0
        inp.u.ki.wScan = int(ctypes.windll.user32.MapVirtualKeyW(
            int(vk), 0) & 0xFFFF)
        inp.u.ki.dwFlags = 0x0008 | (0 if bas else 0x0002)
        inp.u.ki.time = 0
        inp.u.ki.dwExtraInfo = 0
        n = ctypes.windll.user32.SendInput(
            1, ctypes.byref(inp), ctypes.sizeof(_INP))
        if not n:
            # Bazi oyunlar SendInput'u yutabilir; normal keybd_event'e dus.
            if bas:
                ctypes.windll.user32.keybd_event(int(vk), 0, 0, 0)
            else:
                ctypes.windll.user32.keybd_event(int(vk), 0, 2, 0)
        return True
    except Exception:
        return False


def _klavye_vur(tuslar, ms=220):
    """Insan benzeri: rastgele sira, kisa basma, ara vererek birakma."""
    tuslar = [str(t).lower() for t in (tuslar or []) if str(t).strip()][:3]
    if not tuslar:
        return []
    if random.random() < 0.5:
        random.shuffle(tuslar)
    basilan = []
    for t in tuslar:
        if _sendinput_key(t, True):
            basilan.append(t)
            time.sleep(random.uniform(0.012, 0.045))
    try:
        sure = max(0.07, float(ms) / 1000.0)
    except Exception:
        sure = 0.22
    time.sleep(random.uniform(sure * 0.75, sure * 1.25))
    for t in reversed(basilan):
        _sendinput_key(t, False)
        time.sleep(random.uniform(0.012, 0.040))
    # Bazen kucuk bir ikinci dokunus (insan parmak titremesi)
    if basilan and random.random() < 0.12:
        time.sleep(random.uniform(0.05, 0.12))
        t = random.choice(basilan)
        _sendinput_key(t, True)
        time.sleep(random.uniform(0.03, 0.08))
        _sendinput_key(t, False)
    return basilan


def _fare_hareket(dx, dy):
    """Goreli fare hareketi; kucuk adimlara bolunur (kamera/aim)."""
    if not WIN:
        return False
    try:
        dx = max(-260, min(260, int(dx)))
        dy = max(-260, min(260, int(dy)))
        if dx == 0 and dy == 0:
            return False
        adim = random.randint(2, 4)
        kalan_x, kalan_y = dx, dy
        for i in range(adim):
            if i == adim - 1:
                ax, ay = kalan_x, kalan_y
            else:
                ax = int(kalan_x / (adim - i)) + random.randint(-3, 3)
                ay = int(kalan_y / (adim - i)) + random.randint(-2, 2)
                kalan_x -= ax
                kalan_y -= ay
            ctypes.windll.user32.mouse_event(0x0001, int(ax), int(ay), 0, 0)
            time.sleep(random.uniform(0.012, 0.035))
        return True
    except Exception:
        return False


def _fare_tikla_sessiz(sag=False):
    if not WIN:
        return False
    try:
        u = ctypes.windll.user32
        if sag:
            u.mouse_event(0x0008, 0, 0, 0, 0)
            time.sleep(random.uniform(0.05, 0.11))
            u.mouse_event(0x0010, 0, 0, 0, 0)
        else:
            u.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(random.uniform(0.05, 0.11))
            u.mouse_event(0x0004, 0, 0, 0, 0)
        return True
    except Exception:
        return False


def _tikla(x, y):
    try:
        import jarvis_ajan as ja
        return ja.tikla(int(x), int(y), 'sol')
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetCursorPos(int(x), int(y))
        time.sleep(0.12)
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.08)
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
        return True
    except Exception:
        return False


def _yaz_harf(metin, sure=0.2):
    try:
        import jarvis_komut_ilet as jk
        return jk.harf_harf_yaz(metin, sure)
    except Exception:
        try:
            for ch in str(metin):
                ctypes.windll.user32.VkKeyScanW(ord(ch))
                time.sleep(max(0.005, float(sure) / max(1, len(str(metin)))))
        except Exception:
            pass
        return False


def _enter():
    return _tus_bas(0x0D, basili=0.05)


# ---------------------------------------------------------------------------
# HATIRLATICI (kalici, saniye/dakika/saat + saat:dd)
# ---------------------------------------------------------------------------
def _hatirlat_yolu():
    return os.path.join(_CFG, 'hatirlaticilar.json')


def _hatirlat_yukle():
    global _HATIRLATILAR
    veri = _json_oku(_hatirlat_yolu(), [])
    if isinstance(veri, dict):
        veri = veri.get('liste') or []
    _HATIRLATILAR = [h for h in (veri or []) if isinstance(h, dict)]
    return _HATIRLATILAR


def _hatirlat_kaydet():
    with _HATIRLAT_KILIT:
        veri = [dict(h) for h in _HATIRLATILAR]
    _json_yaz(_hatirlat_yolu(), veri)


def _hatirlat_ekle(metin, saniye=60.0, log=None, ses=None):
    try:
        saniye = max(1.0, float(saniye))
    except Exception:
        saniye = 60.0
    hedef = time.time() + saniye
    with _HATIRLAT_KILIT:
        _HATIRLATILAR.append({'metin': str(metin)[:200], 'hedef': hedef,
                              'eklendi': time.time()})
    _hatirlat_kaydet()
    _yaz(log, 'SYS: HATIRAT KURULDU: ' + str(metin)[:160]
         + ' (%.0f sn sonra)' % saniye)
    _sesle(ses, 'Hatirlatma kuruldu: ' + str(metin)[:120])
    _hatirlat_baslat(log, ses)
    return hedef


def _hatirlat_ekle_saat(metin, saat_dk, log=None, ses=None):
    """'14:30' bicimini bugun/yarin ilk karsilasmaya cevirir."""
    try:
        m = re.match(r'^\s*(\d{1,2})\s*[:.]\s*(\d{2})\s*$', str(saat_dk))
        if not m:
            return 0.0
        saat = int(m.group(1))
        dakika = int(m.group(2))
        if not (0 <= saat <= 23 and 0 <= dakika <= 59):
            return 0.0
        simdi = time.localtime()
        hedef_t = time.mktime((simdi.tm_year, simdi.tm_mon, simdi.tm_mday,
                               saat, dakika, 0, 0, 0, -1))
        if hedef_t <= time.time() + 1:
            hedef_t += 24 * 3600
        saniye = max(1.0, hedef_t - time.time())
        return _hatirlat_ekle(metin, saniye, log, ses)
    except Exception:
        return 0.0


def _hatirlat_izle():
    global _HATIRLAT_THREAD
    try:
        while True:
            time.sleep(1.0)
            simdi = time.time()
            due = []
            with _HATIRLAT_KILIT:
                kalan = []
                for h in _HATIRLATILAR:
                    try:
                        if float(h.get('hedef') or 0) <= simdi:
                            due.append(h)
                        else:
                            kalan.append(h)
                    except Exception:
                        pass
                if due:
                    _HATIRLATILAR[:] = kalan
            if due:
                _hatirlat_kaydet()
                for h in due:
                    metin = str(h.get('metin') or 'Hatirlatma')[:200]
                    _yaz(_demir_log(), 'SYS: HATIRAT: ' + metin)
                    _sesle(_demir_ses(), metin[:160])
    finally:
        _HATIRLAT_THREAD = None


_DEMIR_LOG = None
_DEMIR_SES = None


def _demir_log():
    return _DEMIR_LOG


def _demir_ses():
    return _DEMIR_SES


def _hatirlat_baslat(log=None, ses=None):
    global _HATIRLAT_THREAD, _DEMIR_LOG, _DEMIR_SES
    if log is not None:
        _DEMIR_LOG = log
    if ses is not None:
        _DEMIR_SES = ses
    if _HATIRLAT_THREAD is not None:
        return True
    _HATIRLAT_THREAD = threading.Thread(target=_hatirlat_izle,
                                       name='sonsuz2-hatirlat', daemon=True)
    _HATIRLAT_THREAD.start()
    return True


def _hatirlat_kacirilanlar(log=None, ses=None):
    """JARVIS kapaliyken zamani gecen hatirlatmalari acilista bildirir."""
    simdi = time.time()
    kacirilan = []
    kalan = []
    with _HATIRLAT_KILIT:
        for h in list(_HATIRLATILAR):
            try:
                if float(h.get('hedef') or 0) <= simdi:
                    kacirilan.append(h)
                else:
                    kalan.append(h)
            except Exception:
                pass
        _HATIRLATILAR[:] = kalan
    if kacirilan:
        _hatirlat_kaydet()
        for h in kacirilan:
            metin = str(h.get('metin') or 'Hatirlatma')[:200]
            _yaz(log, 'SYS: HATIRAT (JARVIS kapaliyken kacirildi): ' + metin)
            _sesle(ses, 'Kacirilan hatirlatma: ' + metin[:140])
    return len(kacirilan)


# ---------------------------------------------------------------------------
# EKRAN IZLEME (her saniye, tek dosya - disk sisirmez)
# ---------------------------------------------------------------------------
def ekran_izle_baslat(log=None, ses=None):
    global _EKRAN_IZLE, _EKRAN_THREAD, _EKRAN_LOG
    _EKRAN_IZLE = True
    _EKRAN_LOG = log
    try:
        if _ju is not None:
            _ju._ekran_izle_durdur()
    except Exception:
        pass
    if _EKRAN_THREAD is None:
        _EKRAN_THREAD = threading.Thread(target=_ekran_izle_dongu,
                                         name='sonsuz2-ekran', daemon=True)
        _EKRAN_THREAD.start()
    _yaz(log, 'SYS: EKRAN IZLEME BASLATILDI (her saniye, tek dosya). '
              'Durdurmak icin: "ekran izlemeyi durdur"')
    _sesle(ses, 'Ekran izlemeye basladim; her saniye kontrol ediyorum.')
    return True


def ekran_izle_durdur(log=None):
    global _EKRAN_IZLE
    _EKRAN_IZLE = False
    _yaz(log, 'SYS: EKRAN IZLEME DURDURULDU.')
    return True


def _ekran_izle_dongu():
    global _EKRAN_THREAD
    hedef = os.path.join(_CFG, 'ekran_izle')
    n = 0
    son_log = 0.0
    son_imza = ''
    try:
        while _EKRAN_IZLE:
            t0 = time.time()
            try:
                # Ayni dosyanin uzerine yazilir: disk sabit kalir.
                yol = ekran_goruntusu(hedef + '.bmp')
                n += 1
                imza = ''
                if yol and os.path.isfile(yol):
                    try:
                        import hashlib
                        with open(yol, 'rb') as f:
                            imza = hashlib.md5(f.read()).hexdigest()[:12]
                    except Exception:
                        imza = ''
                    if imza != son_imza:
                        son_imza = imza
                simdi = time.time()
                if simdi - son_log >= 60.0:
                    boyut = 0
                    try:
                        boyut = os.path.getsize(yol) if yol else 0
                    except Exception:
                        pass
                    degisti = 'degisim VAR' if imza != '' else 'goruntu yok'
                    _yaz(_EKRAN_LOG, 'SYS: EKRAN IZLE #%d | 1 sn | %s | '
                                     '%.1f KB | tek dosya' %
                         (n, degisti, boyut / 1024.0))
                    son_log = simdi
            except Exception as e:
                _yaz(_EKRAN_LOG, 'ERR: ekran izleme: ' + repr(e)[:160])
            gecen = time.time() - t0
            time.sleep(max(0.05, 1.0 - gecen))
    finally:
        _EKRAN_THREAD = None
        _yaz(_EKRAN_LOG, 'SYS: EKRAN IZLEME DURDU (%d goruntu).' % n)


# ---------------------------------------------------------------------------
# AFK / BAN KORUMA (her saniye kontrol, en fazla 15 dakika)
# ---------------------------------------------------------------------------
_OYUN_ANAHTAR = (
    'roblox', 'minecraft', 'counter-strike', 'cs2', 'cs:go', 'valorant',
    'league of legends', 'gta', 'fivem', 'redm', 'pubg', 'fortnite',
    'among us', 'brawl', 'genshin', 'warzone', 'apex', 'rust', 'terraria',
    'stardew', 'beamng', 'euro truck', 'ets2', 'farm simulator',
    'simulator', 'rocket league', 'overwatch', 'rainbow six',
    'escape from tarkov', 'unturned', 'garry', 'gmod', 'team fortress',
    'left 4 dead', 'portal', 'witcher', 'cyberpunk', 'elden ring',
    'skyrim', 'fallout', 'hollow', 'geometry dash', 'osu', 'call of duty',
    'battlefield', 'destiny', 'halo', 'forza', 'assetto', 'nba', 'fifa',
    'ea sports', 'pes', 'efootball', 'total war', 'civilization',
    'cities skylines', 'palworld', 'valheim', 'phasmophobia',
    'lethal company', 'content warning', 'balatro', 'hades', 'dead cells',
    'risk of rain', 'slay the spire', 'deep rock', 'satisfactory',
    'anno', 'tropico', 'planet coaster', 'planet zoo', 'the sims',
    'football manager', 'jurassic world', 'subnautica', 'no man',
    'star citizen', 'elite dangerous', 'war thunder', 'world of tanks',
    'world of warships', 'crossout', 'path of exile', 'diablo',
    'lost ark', 'new world', 'black desert', 'final fantasy', 'monster hunter',
    'dark souls', 'sekiro', 'bloodborne', 'lies of p', 'armored core',
    'tekken', 'street fighter', 'mortal kombat', 'smash', 'brawlhalla',
    'fall guys', 'human fall flat', 'gang beasts', 'pummel party',
    'move or die', 'duck game', 'stick fight', 'castle crashers',
)

_OYUN_SINIF = (
    'unitywndclass', 'unrealwindow', 'riotwindowclass', 'sdl_app',
    'glfw30', 'glfw', 'lwjgl', 'sunawtframe', 'valve001', 'cryengine',
    'gamewindow', 'windowsgame',
)


def _oyun_penceresi():
    """Acik oyun penceresini puanlayarak bulur (baslik + sinif + tam ekran)."""
    if not WIN:
        return 0, ''
    try:
        u = ctypes.windll.user32
        ekran_w = int(u.GetSystemMetrics(0))
        ekran_h = int(u.GetSystemMetrics(1))
    except Exception:
        ekran_w = ekran_h = 0
    adaylar = []
    for hwnd, ad in _pencere_listesi():
        adk = ad.lower()
        if not adk or any(k in adk for k in _OYUN_DISLA):
            continue
        d = _pencere_rect(hwnd)
        if not d or (d[2] - d[0]) < 320 or (d[3] - d[1]) < 240:
            continue
        puan = 0
        if any(k in adk for k in _OYUN_ANAHTAR):
            puan += 4
        sinif = _pencere_sinifi(hwnd).lower()
        if any(k in sinif for k in _OYUN_SINIF):
            puan += 3
        if ekran_w and ekran_h:
            if (d[2] - d[0]) >= int(ekran_w * 0.82) and \
                    (d[3] - d[1]) >= int(ekran_h * 0.82):
                puan += 2
        if puan > 0:
            adaylar.append((puan, hwnd, ad))
    adaylar.sort(key=lambda x: -x[0])
    if adaylar:
        return adaylar[0][1], adaylar[0][2]
    return 0, ''


def _oyun_penceresi_uygun(hwnd):
    """Tek bir pencerenin oyun olma ihtimalini dogrular (tarayici vb. degil)."""
    if not WIN or not hwnd:
        return False
    try:
        ad = ''
        for h, a in _pencere_listesi():
            if int(h) == int(hwnd):
                ad = a
                break
        adk = ad.lower()
        if not adk or any(k in adk for k in _OYUN_DISLA):
            return False
        if any(k in adk for k in _OYUN_ANAHTAR):
            return True
        if any(k in _pencere_sinifi(hwnd).lower() for k in _OYUN_SINIF):
            return True
        d = _pencere_rect(hwnd)
        if d:
            w = int(ctypes.windll.user32.GetSystemMetrics(0))
            h = int(ctypes.windll.user32.GetSystemMetrics(1))
            if w and h and (d[2] - d[0]) >= int(w * 0.82) and \
                    (d[3] - d[1]) >= int(h * 0.82):
                return True
    except Exception:
        pass
    return False


def _afk_hareket(hwnd, baslik):
    """Kucuk, insan benzeri girdi. Ayni tus ust uste 3'ten fazla basilmaz."""
    if not WIN:
        return False
    try:
        u = ctypes.windll.user32
        one = int(u.GetForegroundWindow() or 0)
        if one != int(hwnd):
            if _son_girdi_sn() < 30.0:
                return False
            _pencere_on(hwnd)
            time.sleep(_insansi_bekleme(0.5))
        try:
            pt = _wt.POINT()
            u.GetCursorPos(ctypes.byref(pt))
            dx = random.choice((-4, -3, -2, 2, 3, 4))
            dy = random.choice((-3, -1, 1, 3))
            u.SetCursorPos(int(pt.x) + dx, int(pt.y) + dy)
            time.sleep(_insansi_bekleme(0.15))
            u.SetCursorPos(int(pt.x), int(pt.y))
        except Exception:
            pass
        tuslar = ['w', 'a', 's', 'd', 'space', 'shift', 'e']
        son = getattr(_afk_hareket, '_son', [])
        aday = [t for t in tuslar if son.count(t) < 2] or tuslar
        tus = random.choice(aday)
        son.append(tus)
        if len(son) > 8:
            del son[0:len(son) - 8]
        _afk_hareket._son = son
        _klavye_vur([tus], random.randint(120, 280))
        if random.random() < 0.35:
            _fare_hareket(random.randint(-60, 60), random.randint(-40, 40))
        return True
    except Exception:
        return False


def _afk_dongu():
    global _AFK
    oyun_vardi = False
    son_log = 0.0
    while True:
        with _KILIT:
            if not _AFK.get('aktif'):
                break
            basladi = float(_AFK.get('basladi') or 0.0)
        if time.time() - basladi > _AFK_SURE:
            _yaz(_AFK.get('log'), 'SYS: AFK KORUMA | 15 dakika doldu; '
                                   'koruma durduruldu.')
            with _KILIT:
                _AFK['aktif'] = False
            break
        hwnd, baslik = _oyun_penceresi()
        if not hwnd:
            if oyun_vardi:
                _yaz(_AFK.get('log'), 'SYS: AFK KORUMA | oyun kapandi; '
                                       'izleme devam ediyor.')
                oyun_vardi = False
            time.sleep(1.0)
            continue
        if not oyun_vardi:
            _yaz(_AFK.get('log'), 'SYS: AFK KORUMA | oyun acik: '
                 + str(baslik)[:120] + ' | her saniye kontrol.')
            oyun_vardi = True
        bos = _son_girdi_sn()
        if bos >= _AFK_ESIK:
            if _afk_hareket(hwnd, baslik):
                _AFK['son_hareket'] = time.time()
                if time.time() - son_log >= 10.0:
                    _yaz(_AFK.get('log'),
                         'SYS: AFK KORUMA | %.0f sn hareketsizlik -> otomatik '
                         'hareket (%s).' % (bos, str(baslik)[:80]))
                    son_log = time.time()
        time.sleep(1.0)


def afk_baslat(log=None, ses=None):
    global _AFK
    try:
        if _ju is not None:
            _ju._afk_durdur(log=None)
    except Exception:
        pass
    with _KILIT:
        _AFK['log'] = log
        _AFK['ses'] = ses
        _AFK['basladi'] = time.time()
        if _AFK.get('aktif') and _AFK.get('thread') is not None:
            _yaz(log, 'SYS: AFK KORUMA | zaten aktif.')
            return True
        _AFK['aktif'] = True
        t = threading.Thread(target=_afk_dongu, name='sonsuz2-afk', daemon=True)
        _AFK['thread'] = t
    t.start()
    _yaz(log, 'SYS: AFK KORUMA | acildi; oyun acikken hareketsizlikte '
              'otomatik hareket (en fazla 15 dakika).')
    _sesle(ses, 'AFK korumasi acildi.')
    return True


def afk_durdur(log=None):
    with _KILIT:
        _AFK['aktif'] = False
    _yaz(log, 'SYS: AFK KORUMA | durduruldu.')
    return True


# ---------------------------------------------------------------------------
# YASAM DONGUSU
# ---------------------------------------------------------------------------
def baslat(log=None, ses=None):
    """SONSUZ v2 servislerini baslatir (uygulama acilisinda cagrilir)."""
    global _DEMIR_LOG, _DEMIR_SES
    _DEMIR_LOG = log
    _DEMIR_SES = ses
    try:
        if _ju is not None:
            _ju._afk_durdur(log=None)
            _ju._ekran_izle_durdur()
    except Exception:
        pass
    _hatirlat_yukle()
    _hatirlat_baslat(log, ses)
    _hatirlat_kacirilanlar(log, ses)
    try:
        _fiyat_baslat(log, ses)
    except Exception:
        pass
    _yaz(log, 'SYS: SONSUZ v2 hazir | sohbet, hatirlatici, ekran, AFK, '
              'fiyat, oyun, 3D, medya.')
    return True


def durdur(log=None):
    global _EKRAN_IZLE
    _EKRAN_IZLE = False
    with _KILIT:
        _AFK['aktif'] = False
    _yaz(log, 'SYS: SONSUZ v2 servisleri durduruldu.')
    return True


# ---------------------------------------------------------------------------
# HARITA / KONUM
# ---------------------------------------------------------------------------
def _konum_temizle(talep):
    t = str(talep or '')
    t = re.sub(r'(?i)\b(google\s*)?(maps?|harita(si|yı|yi)?|konum|location|'
               r'gps|yol\s*tarifi|html|ac|aç|goster|göster|bul|git|ara|'
               r'search|için|icin)\b', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip(' .,-:;')
    return t[:160]


def harita_ac(talep, log=None, ses=None):
    yer = _konum_temizle(talep)
    if len(yer) < 2:
        yer = 'Türkiye'
    q = urllib.parse.quote(yer)
    google = 'https://www.google.com/maps/search/?api=1&query=' + q
    html_istendi = bool(re.search(r'(?i)\bhtml\b', str(talep or '')))
    try:
        webbrowser.open(google)
    except Exception as e:
        _hata(log, 'Google Maps acilamadi: ' + repr(e)[:160])
    if html_istendi or re.search(r'(?i)\bharita\s*(yap|olustur|oluştur)\b',
                                  str(talep or '')):
        try:
            dosya = os.path.join(_URETIM, 'harita_%s.html' % _slug(yer))
            icerik = """<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<title>J.A.R.V.I.S Harita - %s</title>
<style>
body{margin:0;background:#05070d;color:#cfefff;font-family:Segoe UI,Arial}
.bar{display:flex;gap:12px;align-items:center;padding:12px 16px;
background:#0b1522;border-bottom:1px solid #1e4058}
.bar h1{font-size:16px;margin:0;flex:1;letter-spacing:.5px}
button{background:#00b7ff;border:0;color:#001018;font-weight:700;
padding:10px 16px;border-radius:8px;cursor:pointer}
button:hover{background:#55d4ff}
iframe{width:100%%;height:calc(100vh - 62px);border:0}
.path{font-size:11px;color:#5f8aa5;padding:6px 16px;word-break:break-all}
</style></head><body>
<div class="bar"><h1>J.A.R.V.I.S &mdash; %s</h1>
<button onclick="kopyala()">KOPYALA</button>
<a href="%s" target="_blank" style="color:#7fe3ff">Google Maps</a></div>
<div class="path" id="yol">konum: %s</div>
<iframe src="https://maps.google.com/maps?q=%s&z=14&output=embed"
loading="eager" referrerpolicy="no-referrer-when-downgrade"></iframe>
<script>
function kopyala(){
  var m = "J.A.R.V.I.S konum: %s\\n%s";
  if(navigator.clipboard){navigator.clipboard.writeText(m).then(function(){
    document.querySelector('button').textContent='KOPYALANDI';
  });}else{window.prompt('Kopyala:',m);}
}
</script></body></html>""" % (yer, yer, google, yer, q, yer, google)
            with open(dosya, 'w', encoding='utf-8') as f:
                f.write(icerik)
            webbrowser.open('file:///' + dosya.replace('\\', '/'))
            _yaz(log, 'SYS: HTML harita acildi: ' + dosya)
        except Exception as e:
            _hata(log, 'HTML harita hatasi: ' + repr(e)[:160])
    _yaz(log, 'SYS: HARITA | %s | %s' % (yer, google))
    _sesle(ses, 'Haritada aciliyor: ' + yer[:100])
    return {'durum': 'HARITA', 'yer': yer, 'url': google}


# ---------------------------------------------------------------------------
# GORSEL / VIDEO URETIMI + KOPYALA DUGMESI
# ---------------------------------------------------------------------------
def _medya_prompt(talep):
    t = str(talep or '')
    p = re.sub(r'(?i)\b(görsel|gorsel|resim|foto|fotoğraf|fotograf|video|'
               r'film|animasyon|üret|uret|yap|oluştur|olustur|bana|bir|'
               r'oluşturur|göster|goster)\b', ' ', t)
    p = re.sub(r'\s+', ' ', p).strip(' .,-:;')
    return p[:400] or 'J.A.R.V.I.S icin fütüristik neon şehir'


def _pollinations(prompt, seed=0):
    try:
        import jarvis_gorsel as jg
        return jg.pollinations_cek(prompt, seed=seed, boyut=1024, deneme=2)
    except Exception:
        return None


def _medya_kaydet(ham, ad, uzanti):
    yol = os.path.join(_URETIM, '%s.%s' % (ad, uzanti))
    try:
        with open(yol, 'wb') as f:
            f.write(ham)
        return yol
    except Exception:
        return ''


def _medya_izleyici(yol, video=False):
    """Uzerinde KOPYALA dugmesi olan HTML goruntuleyici uretir ve acar."""
    try:
        ad = os.path.splitext(os.path.basename(yol))[0]
        html = os.path.join(_URETIM, 'izle_%s.html' % _slug(ad))
        dosya_url = 'file:///' + os.path.abspath(yol).replace('\\', '/')
        medya = ('<video src="%s" controls autoplay loop></video>' % dosya_url
                 if video else '<img src="%s" alt="JARVIS uretimi">' % dosya_url)
        icerik = """<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><title>J.A.R.V.I.S Uretim</title>
<style>
body{margin:0;background:radial-gradient(circle at 50%% 30%%,#0a2233,#03050a 70%%);
color:#d9f6ff;font-family:Segoe UI,Arial;min-height:100vh}
.bar{display:flex;gap:12px;align-items:center;padding:14px 18px;
background:#08131f;border-bottom:1px solid #16405a}
.bar h1{font-size:16px;margin:0;flex:1}
button{background:#00c8ff;border:0;color:#00121c;font-weight:800;
padding:11px 18px;border-radius:9px;cursor:pointer;font-size:14px}
button:hover{background:#67e0ff}
.sahne{display:flex;justify-content:center;align-items:center;padding:24px}
img,video{max-width:92vw;max-height:76vh;border-radius:14px;
box-shadow:0 0 60px #00a8ff44;background:#000}
.yol{padding:10px 20px;font-size:12px;color:#6fb7d8;word-break:break-all}
</style></head><body>
<div class="bar"><h1>J.A.R.V.I.S &mdash; %s</h1>
<button onclick="kopyala()">KOPYALA</button>
<a href="%s" download style="color:#8de8ff">INDIR</a></div>
<div class="sahne">%s</div>
<div class="yol" id="yol">%s</div>
<script>
function kopyala(){
  var m = "JARVIS uretim dosyasi: %s";
  if(navigator.clipboard){navigator.clipboard.writeText(m).then(function(){
    document.querySelector('button').textContent='KOPYALANDI';
  });}else{window.prompt('Kopyala:',m);}
}
</script></body></html>""" % (ad, dosya_url, medya,
                              os.path.abspath(yol).replace('\\', '/'),
                              os.path.abspath(yol).replace('\\', '/'))
        with open(html, 'w', encoding='utf-8') as f:
            f.write(icerik)
        webbrowser.open('file:///' + html.replace('\\', '/'))
        return html
    except Exception:
        return ''


def _xml_kacis(metin):
    return (str(metin or '').replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _yerel_svg(ad, prompt, video=False):
    """Internet/ffmpeg yoksa: animasyonlu, uzerinde KOPYALA olan yerel SVG."""
    try:
        import hashlib
        tohum = int(hashlib.md5(str(prompt).encode('utf-8', 'ignore'))
                    .hexdigest()[:8], 16)
        r = random.Random(tohum)
        c1 = '#%02x%02x%02x' % (r.randint(4, 40), r.randint(18, 90),
                                r.randint(40, 140))
        c2 = '#%02x%02x%02x' % (r.randint(20, 120), r.randint(60, 190),
                                r.randint(90, 240))
        c3 = '#%02x%02x%02x' % (r.randint(60, 200), r.randint(120, 230),
                                r.randint(150, 255))
        kelimeler = str(prompt or '').split()
        satirlar, satir = [], ''
        for k in kelimeler:
            if len(satir) + len(k) + 1 > 34:
                satirlar.append(satir)
                satir = k
            else:
                satir = (satir + ' ' + k).strip()
        if satir:
            satirlar.append(satir)
        satirlar = satirlar[:4] or ['JARVIS yerel uretim']
        metin = ''.join(
            '<text x="512" y="%d" text-anchor="middle" fill="#eafcff" '
            'font-family="Segoe UI,Arial" font-size="30">%s</text>'
            % (600 + i * 42, _xml_kacis(s)) for i, s in enumerate(satirlar))
        daireler = ''
        for i in range(9):
            cx, cy = r.randint(80, 944), r.randint(80, 500)
            rr = r.randint(30, 130)
            sure = r.uniform(3.0, 9.0)
            daireler += (
                '<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" '
                'stroke-width="2" opacity="0.55">'
                '<animate attributeName="r" values="%d;%d;%d" dur="%.1fs" '
                'repeatCount="indefinite"/>'
                '<animate attributeName="cy" values="%d;%d;%d" dur="%.1fs" '
                'repeatCount="indefinite"/></circle>'
                % (cx, cy, rr, c3 if i % 2 else c2, rr, rr + 18, rr,
                   sure, cy, cy - 20, cy, sure + 1.5))
        hareket = ''
        if video:
            hareket = (
                '<rect x="-300" y="0" width="300" height="1024" '
                'fill="url(#parlak)" opacity="0.18">'
                '<animate attributeName="x" values="-300;1024" dur="3.5s" '
                'repeatCount="indefinite"/></rect>')
        svg = os.path.join(_URETIM, ad + '.svg')
        with open(svg, 'w', encoding='utf-8') as f:
            f.write(
                '<svg xmlns="http://www.w3.org/2000/svg" width="1024" '
                'height="1024" viewBox="0 0 1024 1024">'
                '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
                '<stop offset="0" stop-color="%s"/><stop offset="0.55" '
                'stop-color="%s"/><stop offset="1" stop-color="%s"/>'
                '</linearGradient>'
                '<linearGradient id="parlak" x1="0" y1="0" x2="1" y2="0">'
                '<stop offset="0" stop-color="#ffffff" stop-opacity="0"/>'
                '<stop offset="0.5" stop-color="#ffffff" stop-opacity="1"/>'
                '<stop offset="1" stop-color="#ffffff" stop-opacity="0"/>'
                '</linearGradient></defs>'
                '<rect width="1024" height="1024" fill="url(#g)"/>'
                '<circle cx="512" cy="330" r="170" fill="none" '
                'stroke="%s" stroke-width="3" opacity="0.6">'
                '<animate attributeName="r" values="165;185;165" dur="4s" '
                'repeatCount="indefinite"/></circle>'
                '<circle cx="512" cy="330" r="120" fill="%s" opacity="0.18"/>'
                '%s%s'
                '<text x="512" y="352" text-anchor="middle" fill="#ffffff" '
                'font-family="Segoe UI,Arial" font-size="58" '
                'font-weight="800">J.A.R.V.I.S</text>'
                '<text x="512" y="404" text-anchor="middle" fill="#bff3ff" '
                'font-family="Segoe UI,Arial" font-size="20">%s URETIM</text>'
                '%s'
                '<text x="512" y="900" text-anchor="middle" fill="#9fdcf2" '
                'font-family="Segoe UI,Arial" font-size="18">Yerel motor '
                '(internet/ffmpeg yok)</text>'
                '</svg>' % (c1, c2, c3, c3, c3, daireler, hareket,
                            'VIDEO' if video else 'GORSEL', metin))
        return svg
    except Exception:
        return ''


def medya_uret(talep, log=None, ses=None):
    video = bool(re.search(r'(?i)\b(video|film|animasyon)\b', str(talep or '')))
    prompt = _medya_prompt(talep)
    ad = 'medya_%s_%s' % (_slug(prompt, 24), time.strftime('%H%M%S'))
    _yaz(log, 'SYS: MEDYA | uretiliyor (%s): %s'
         % ('video' if video else 'gorsel', prompt[:160]))
    if not video:
        ham = _pollinations(prompt, seed=random.randint(1, 999999))
        if not ham:
            _yaz(log, 'SYS: MEDYA | internet motoru yanit vermedi; yerel '
                      'SVG gorsel uretiyorum.')
            svg = _yerel_svg(ad, prompt, video=False)
            if svg:
                izle = _medya_izleyici(svg, video=False)
                _yaz(log, 'JARVIS: Gorsel (yerel SVG) hazir -> ' + svg)
                _yaz(log, 'SYS: KOPYALA dugmesi acik: ' + (izle or 'tarayici'))
                _sesle(ses, 'Gorsel hazir; ekranda kopyalama dugmesi var.')
                return {'durum': 'GORSEL_SVG', 'dosya': svg,
                        'izleyici': izle}
            _hata(log, 'Gorsel motoru ve yerel SVG yanit vermedi.')
            _sesle(ses, 'Gorsel uretemedim.')
            return {'durum': 'MEDYA_HATA'}
        yol = _medya_kaydet(ham, ad, 'jpg')
        if not yol:
            return {'durum': 'MEDYA_HATA'}
        yol = _png_yap(yol)
        izle = _medya_izleyici(yol, video=False)
        _yaz(log, 'JARVIS: Gorsel hazir -> ' + yol)
        _yaz(log, 'SYS: KOPYALA dugmesi acik: ' + (izle or 'tarayici'))
        _sesle(ses, 'Gorsel hazir; ekranda kopyalama dugmesi var.')
        return {'durum': 'GORSEL', 'dosya': yol, 'izleyici': izle}
    # Video: 4 kare uret + ffmpeg ile mp4 birlestir.
    kareler = []
    for i in range(4):
        ham = _pollinations(prompt + ', sahne %d' % (i + 1),
                            seed=random.randint(1, 999999))
        if not ham:
            continue
        k = _medya_kaydet(ham, '%s_k%d' % (ad, i + 1), 'jpg')
        if k:
            kareler.append(k)
    if not kareler:
        _yaz(log, 'SYS: MEDYA | video kareleri gelmedi; yerel animasyonlu '
                  'SVG video uretiyorum.')
        svg = _yerel_svg(ad, prompt, video=True)
        if svg:
            izle = _medya_izleyici(svg, video=True)
            _yaz(log, 'JARVIS: Animasyonlu video (yerel SVG) hazir -> ' + svg)
            _sesle(ses, 'Video hazir; tarayicida oynuyor.')
            return {'durum': 'VIDEO_SVG', 'dosya': svg, 'izleyici': izle}
        _hata(log, 'Video icin kare ve yerel SVG uretilemedi.')
        _sesle(ses, 'Video uretemedim.')
        return {'durum': 'MEDYA_HATA'}
    mp4 = ''
    try:
        import jarvis_film as jf
        ff = jf.ffmpeg_bul()
    except Exception:
        ff = shutil.which('ffmpeg')
    if ff:
        try:
            liste = os.path.join(_URETIM, ad + '_liste.txt')
            with open(liste, 'w', encoding='utf-8') as f:
                for k in kareler:
                    f.write("file '%s'\nduration 2\n" %
                            os.path.abspath(k).replace('\\', '/'))
                f.write("file '%s'\n" % os.path.abspath(kareler[-1])
                        .replace('\\', '/'))
            mp4 = os.path.join(_URETIM, ad + '.mp4')
            komut = [ff, '-y', '-f', 'concat', '-safe', '0', '-i', liste,
                     '-vf', 'scale=1024:1024:force_original_aspect_ratio=decrease,'
                            'pad=1024:1024:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
                     '-c:v', 'libx264', '-r', '25', '-shortest', mp4]
            r = subprocess.run(komut, capture_output=True, text=True,
                               timeout=300, encoding='utf-8', errors='replace',
                               creationflags=0x08000000 if WIN else 0)
            if r.returncode != 0 or not os.path.isfile(mp4):
                mp4 = ''
        except Exception as e:
            _yaz(log, 'SYS: ffmpeg video hatasi: ' + repr(e)[:160])
            mp4 = ''
    if not mp4:
        # ffmpeg yoksa: animasyonlu SVG "video" + kare galerisi
        try:
            svg = os.path.join(_URETIM, ad + '.svg')
            with open(svg, 'w', encoding='utf-8') as f:
                f.write('<svg xmlns="http://www.w3.org/2000/svg" '
                        'width="1024" height="1024">')
                for i, k in enumerate(kareler):
                    b64 = base64.b64encode(open(k, 'rb').read()).decode()
                    f.write('<image href="data:image/jpeg;base64,%s" '
                            'width="1024" height="1024" opacity="0">'
                            '<animate attributeName="opacity" values="0;1;0" '
                            'dur="%ds" begin="%ds" repeatCount="indefinite"/>'
                            '</image>' % (b64, len(kareler) * 2, i * 2))
                f.write('</svg>')
            izle = _medya_izleyici(svg, video=True)
            _yaz(log, 'JARVIS: Animasyonlu video (SVG) hazir -> ' + svg)
            _sesle(ses, 'Video hazir; tarayicida oynuyor.')
            return {'durum': 'VIDEO_SVG', 'dosya': svg, 'izleyici': izle}
        except Exception as e:
            _hata(log, 'SVG video hatasi: ' + repr(e)[:160])
            return {'durum': 'MEDYA_HATA'}
    izle = _medya_izleyici(mp4, video=True)
    _yaz(log, 'JARVIS: Video hazir -> ' + mp4)
    _yaz(log, 'SYS: KOPYALA dugmesi acik: ' + (izle or 'tarayici'))
    _sesle(ses, 'Video hazir; ekranda kopyalama dugmesi var.')
    return {'durum': 'VIDEO', 'dosya': mp4, 'izleyici': izle}


# ---------------------------------------------------------------------------
# 3D VARLIK: sketchfab + 3dmodels.org/tr
# ---------------------------------------------------------------------------
def _http_al(url, zaman=25, boyut=2500000):
    try:
        istek = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 Chrome/124 Safari/537.36',
            'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8'})
        with urllib.request.urlopen(istek, timeout=zaman) as r:
            return r.read(boyut)
    except Exception:
        return b''


def _3d_ad(talep):
    t = str(talep or '')
    t = re.sub(r'(?i)\b(3d|üç\s*boyut|uc\s*boyut|model|modeli|varlık|varlik|'
               r'asset|indir|download|ücretsiz|ucretsiz|free|bul|ara|'
               r'ekle|aktar|projeye|sketchfab|3dmodels|org|com|tr|lütfen|'
               r'lutfen|bana|bir)\b', ' ', t)
    t = re.sub(r'https?://\S+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip(' .,-:;/')
    return t[:120]


def _hedef_proje():
    try:
        kayit = _json_oku(os.path.join(_KOK, 'memory', 'son_oyun.json'), {})
        klasor = str(kayit.get('klasor') or '')
        if klasor and os.path.isdir(klasor):
            return klasor
    except Exception:
        pass
    return ''


def _indir_dosya(url, hedef):
    try:
        istek = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 Chrome/124 Safari/537.36'})
        with urllib.request.urlopen(istek, timeout=60) as r:
            os.makedirs(os.path.dirname(hedef), exist_ok=True)
            with open(hedef, 'wb') as f:
                toplam = 0
                while True:
                    parca = r.read(262144)
                    if not parca:
                        break
                    toplam += len(parca)
                    if toplam > 250 * 1024 * 1024:
                        return ''
                    f.write(parca)
        return hedef if os.path.isfile(hedef) and os.path.getsize(hedef) > 2000 else ''
    except Exception:
        return ''


def uc_boyut(talep, log=None, ses=None):
    ad = _3d_ad(talep)
    if len(ad) < 2:
        ad = 'obje'
    q = urllib.parse.quote(ad)
    s_url = ('https://sketchfab.com/search?q=%s&type=models&features='
             'downloadable&sort_by=-pertinence' % q)
    m_url = 'https://3dmodels.org/tr/?s=' + q
    m_free = 'https://3dmodels.org/tr/free-3d-models/'
    for u in (s_url, m_url):
        try:
            webbrowser.open(u)
        except Exception:
            pass
    _yaz(log, 'SYS: 3D ARAMA | "%s" | Sketchfab + 3dmodels.org/tr acildi.'
         % ad)
    adaylar = []
    # Sketchfab API: indirilebilir ucretsiz modeller
    try:
        ham = _http_al('https://api.sketchfab.com/v3/search?type=models&q=%s'
                       '&downloadable=true&count=12' % q)
        if ham:
            veri = json.loads(ham.decode('utf-8', 'ignore'))
            for m in (veri.get('results') or [])[:8]:
                adaylar.append({
                    'kaynak': 'Sketchfab', 'ad': m.get('name') or '',
                    'url': m.get('viewerUrl') or '',
                    'uid': m.get('uid') or '',
                    'ucretsiz': True})
    except Exception:
        pass
    # 3dmodels arama sayfasi: baglantilari topla
    try:
        ham = _http_al(m_url)
        if ham:
            html = ham.decode('utf-8', 'ignore')
            for m in re.finditer(r'href="(https?://3dmodels\.org/[^"]+)"', html):
                u = m.group(1)
                if any(x in u.lower() for x in ('/tr/', '/free', '/model')):
                    if u not in [a['url'] for a in adaylar]:
                        adaylar.append({'kaynak': '3dmodels', 'ad': u
                                        .rstrip('/').split('/')[-1],
                                        'url': u, 'uid': '', 'ucretsiz':
                                        'free' in u.lower()})
    except Exception:
        pass
    if adaylar:
        for a in adaylar[:5]:
            _yaz(log, 'SYS: 3D ADAY | %s | %s | %s'
                 % (a['kaynak'], a['ad'][:80], a['url']))
    else:
        _yaz(log, 'SYS: 3D ADAY | API listesi bos; tarayici sekmelerinden '
                  'ucretsizleri inceleyebilirsin.')
    # Dogrudan indirilebilir dosya baglantisi ara (3dmodels / acik sayfalar).
    indirilen = ''
    hedef_klasor = os.path.join(_VARLIK, _slug(ad))
    for a in adaylar[:6]:
        if a['kaynak'] != '3dmodels':
            continue
        try:
            ham = _http_al(a['url'], zaman=20)
            if not ham:
                continue
            html = ham.decode('utf-8', 'ignore')
            if 'download' not in html.lower():
                continue
            for m in re.finditer(
                    r'https?://[^\s"\'<>]+\.(?:zip|glb|gltf|fbx|obj|blend)',
                    html, re.I):
                u = m.group(0)
                hedef = os.path.join(hedef_klasor,
                                     os.path.basename(urllib.parse.urlparse(u)
                                                      .path) or 'model.glb')
                indirilen = _indir_dosya(u, hedef)
                if indirilen:
                    break
            if indirilen:
                break
        except Exception:
            continue
    if indirilen:
        proje = _hedef_proje()
        if proje:
            try:
                pd = os.path.join(proje, 'varliklar', '3d')
                os.makedirs(pd, exist_ok=True)
                shutil.copy2(indirilen, pd)
                _yaz(log, 'SYS: 3D AKTARILDI -> ' + pd)
            except Exception:
                pass
        _yaz(log, 'JARVIS: 3D varlik hazir -> ' + indirilen)
        _sesle(ses, '3D model indirildi ve projeye aktarildi.')
        return {'durum': '3D', 'dosya': indirilen, 'adaylar': adaylar}
    _yaz(log, 'SYS: 3D | otomatik indirme basarisiz; ucretsiz adaylar '
              'listelendi ve tarayicida acildi. Indirme icin en uygun: '
              + (adaylar[0]['url'] if adaylar else m_free))
    _sesle(ses, '3D modelleri arastirdim; ucretsiz adaylari actim.')
    return {'durum': '3D_LISTE', 'adaylar': adaylar, 'url': m_url}


# ---------------------------------------------------------------------------
# FIYAT TAKIBI (Trendyol, Amazon, Vatan, Idefix, N11)
# ---------------------------------------------------------------------------
_PLATFORMLAR = ('Trendyol', 'Amazon', 'Vatan', 'Idefix', 'N11')
_FIYAT_DOSYA = os.path.join(_CFG, 'fiyat_takip.json')


def _fiyat_veri():
    veri = _json_oku(_FIYAT_DOSYA, {})
    if not isinstance(veri, dict):
        veri = {}
    veri.setdefault('urunler', [])
    veri.setdefault('son_kontrol', 0)
    return veri


def _fiyat_kaydet(veri):
    return _json_yaz(_FIYAT_DOSYA, veri)


def _fiyat_url(platform, q):
    qq = urllib.parse.quote_plus(str(q))
    if platform == 'Trendyol':
        return 'https://www.trendyol.com/sr?q=' + qq
    if platform == 'Amazon':
        return 'https://www.amazon.com.tr/s?k=' + qq
    if platform == 'Vatan':
        return 'https://www.vatanbilgisayar.com/arama/' + qq + '/'
    if platform == 'Idefix':
        return 'https://www.idefix.com/arama?q=' + qq
    if platform == 'N11':
        return 'https://www.n11.com/arama?q=' + qq
    return ''


def _fiyat_sayi(metin):
    s = str(metin or '').strip().replace(' ', '').replace('\xa0', '')
    s = s.replace('₺', '').replace('TL', '').replace('tl', '')
    s = re.sub(r'[^0-9.,]', '', s)
    if not s:
        return 0.0
    try:
        if ',' in s and '.' in s:
            if s.rfind(',') < s.rfind('.'):
                s = s.replace(',', '')
            else:
                s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            parcalar = s.split(',')
            if len(parcalar[-1]) == 3 and len(parcalar[0]) <= 3:
                s = s.replace(',', '')
            else:
                s = s.replace(',', '.')
        elif s.count('.') > 1:
            s = s.replace('.', '')
        elif '.' in s:
            parcalar = s.split('.')
            if len(parcalar[-1]) == 3 and len(parcalar[0]) <= 3:
                s = s.replace('.', '')
        f = float(s)
        if 0.5 <= f <= 10000000.0:
            return f
    except Exception:
        pass
    return 0.0


def _fiyat_json_ld(html):
    """JSON-LD icinden ilk urunun (fiyat, url, ad) bilgisini cikarir."""
    for m in re.finditer(
            r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
            html or '', re.I | re.S):
        ham = (m.group(1) or '').strip()
        if not ham:
            continue
        try:
            veri = json.loads(ham)
        except Exception:
            continue
        kuyruk = [veri]
        while kuyruk:
            v = kuyruk.pop(0)
            if isinstance(v, list):
                kuyruk.extend(v)
                continue
            if not isinstance(v, dict):
                continue
            t = str(v.get('@type') or '').lower()
            if 'itemlist' in t:
                for it in (v.get('itemListElement') or []):
                    urun = it.get('item') if isinstance(it, dict) else None
                    if not isinstance(urun, dict):
                        continue
                    offers = urun.get('offers') or {}
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    f = _fiyat_sayi((offers or {}).get('price') or
                                    urun.get('price') or '')
                    if f:
                        return f, str(urun.get('url') or ''), str(
                            urun.get('name') or '')
            if 'product' in t:
                offers = v.get('offers') or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                f = _fiyat_sayi((offers or {}).get('price') or
                                v.get('price') or '')
                if f:
                    return f, str(v.get('url') or ''), str(v.get('name') or '')
            for k in ('@graph', 'mainEntity', 'itemListElement', 'item'):
                if k in v:
                    kuyruk.append(v[k])
    return 0.0, '', ''


def _fiyat_baslik_puan(baslik, urun):
    b = str(baslik or '').lower()
    puan = 0
    for k in re.findall(r'[a-z0-9ğüşıöç]{2,}', str(urun or '').lower()):
        if k in b:
            puan += 2 if len(k) >= 4 else 1
    return puan


def _fiyat_ayikla(html, platform, urun=''):
    """HTML'den ilk/uygun urunun fiyatini ve baglantisini cikarir."""
    if not html:
        return 0.0, ''
    # 1) JSON-LD (N11, Trendyol, Idefix, bazi Vatan sayfalari)
    f, u, ad = _fiyat_json_ld(html)
    if f:
        return f, u

    # 2) N11: JSON-LD yoksa gomulu urun kaydi
    if platform == 'N11':
        m = re.search(
            r'"url"\s*:\s*"(https://www\.n11\.com/urun/[^"]+)"[^{}]{0,800}?'
            r'"price"\s*:\s*"?([\d.,]+)"?', html, re.I | re.S)
        if m:
            return _fiyat_sayi(m.group(2)), m.group(1)

    # 3) Vatan: ilk urun karti
    if platform == 'Vatan':
        m = re.search(
            r'<a[^>]+class="product-list-link"[^>]+href="([^"]+)"',
            html, re.I)
        f = re.search(r'class="product-list__price"[^>]*>\s*([^<]+)',
                      html, re.I)
        if m and f:
            fiyat = _fiyat_sayi(f.group(1))
            if fiyat:
                return fiyat, urllib.parse.urljoin(
                    'https://www.vatanbilgisayar.com', m.group(1))

    # 4) Amazon: arama sonucu kartlarindan baslige en uygun olani
    if platform == 'Amazon':
        kartlar = []
        for m in re.finditer(r'data-component-type="s-search-result"',
                             html, re.I):
            blok = html[m.start():m.start() + 9000]
            asin = re.search(r'data-asin="([^"]+)"', blok)
            bas = re.search(r'<h2[^>]*>[\s\S]{0,400}?<span[^>]*>'
                            r'([^<]{5,240})</span>', blok)
            if not bas:
                bas = re.search(r'<img[^>]+alt="([^"]{5,240})"', blok)
            pf = re.search(r'<span class="a-offscreen">\s*([^<]{1,40})'
                           r'\s*</span>', blok)
            if not pf:
                pf = re.search(r'class="a-price-whole">([\d.,]+)', blok)
            if not pf:
                continue
            fiyat = _fiyat_sayi(pf.group(1))
            if not fiyat:
                continue
            href = re.search(r'href="(/[^"]*(?:/dp/|/gp/product/)[^"]+)"',
                             blok)
            if not href and asin:
                href_url = 'https://www.amazon.com.tr/dp/' + asin.group(1)
            else:
                href_url = (urllib.parse.urljoin(
                    'https://www.amazon.com.tr', href.group(1))
                    if href else '')
            kartlar.append((_fiyat_baslik_puan(
                bas.group(1) if bas else '', urun), fiyat, href_url))
        if kartlar:
            kartlar.sort(key=lambda x: -x[0])
            return kartlar[0][1], kartlar[0][2]

    # 5) Trendyol / Idefix / genel: gomulu JSON ve urun baglantisi
    for kal in (
            r'"sellingPrice"\s*:\s*([\d.]+)',
            r'"discountedPrice"\s*:\s*\{[^{}]{0,200}?"value"\s*:\s*([\d.]+)',
            r'itemprop="price"[^>]*content="([\d.,]+)"',
            r'"price"\s*:\s*\{[^{}]{0,200}?"value"\s*:\s*([\d.]+)',
            r'"price"\s*:\s*"?([\d.,]+)"?'):
        ms = re.findall(kal, html, re.I)
        if ms:
            fiyat = _fiyat_sayi(ms[0])
            if fiyat:
                m = re.search(
                    r'href="([^"]*(?:/p-|/dp/|/urun/|/product/)[^"]*)"',
                    html)
                url = ''
                if m:
                    kok = {'Trendyol': 'https://www.trendyol.com',
                           'Idefix': 'https://www.idefix.com'}.get(
                        platform, 'https://' + str(platform).lower() + '.com')
                    url = urllib.parse.urljoin(kok, m.group(1))
                return fiyat, url
    # 6) Son care: ilk TL/₺ fiyati
    for kal in (r'₺\s*([\d.,]+)',
                r'([\d]{1,3}(?:\.[\d]{3})*(?:,\d{2})?)\s*(?:TL|₺)'):
        ms = re.findall(kal, html, re.I)
        for a in ms[:4]:
            fiyat = _fiyat_sayi(a)
            if fiyat:
                return fiyat, ''
    return 0.0, ''


def _fiyat_istek(url, platform):
    """Requests (cerezli, coklu UA) ile sayfayi indirir; engelde bos doner."""
    kok = {'Trendyol': 'https://www.trendyol.com/',
           'Amazon': 'https://www.amazon.com.tr/',
           'Vatan': 'https://www.vatanbilgisayar.com/',
           'Idefix': 'https://www.idefix.com/',
           'N11': 'https://www.n11.com/'}.get(platform, '')
    ualar = [
        ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
         'AppleWebKit/537.36 (KHTML, like Gecko) '
         'Chrome/125.0.0.0 Safari/537.36'),
        ('Mozilla/5.0 (Linux; Android 13; Pixel 7) '
         'AppleWebKit/537.36 (KHTML, like Gecko) '
         'Chrome/125.0.0.0 Mobile Safari/537.36'),
        ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
         'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 '
         'Mobile/15E148 Safari/604.1'),
    ]
    # Trendyol/Idefix sik sik bot engelliyor; en azindan URL kaydedilir.
    if platform in ('Trendyol', 'Idefix'):
        ualar = ualar[:1]
    try:
        import requests
        for ua in ualar:
            try:
                s = requests.Session()
                s.headers.update({
                    'User-Agent': ua,
                    'Accept': ('text/html,application/xhtml+xml,application/xml;'
                               'q=0.9,image/avif,image/webp,*/*;q=0.8'),
                    'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.7',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'no-cache',
                })
                if kok and platform in ('Amazon', 'N11', 'Vatan'):
                    try:
                        s.get(kok, timeout=8)
                    except Exception:
                        pass
                r = s.get(url, timeout=20, allow_redirects=True)
                if r.status_code != 200 or len(r.content) < 3000:
                    continue
                low = r.text[:4000].lower()
                if 'captcha' in low or 'just a moment' in low or \
                        'verify you are human' in low:
                    continue
                return r.text
            except Exception:
                continue
    except Exception:
        pass
    try:
        ham = _http_al(url, zaman=18, boyut=3000000)
        if ham:
            return ham.decode('utf-8', 'ignore')
    except Exception:
        pass
    return ''


def _fiyat_platform_cek(platform, urun):
    adaylar = [_fiyat_url(platform, urun)]
    if platform == 'Amazon':
        adaylar.append('https://www.amazon.com.tr/gp/aw/s?k='
                       + urllib.parse.quote_plus(str(urun)))
    if platform == 'Vatan':
        adaylar.append('https://www.vatanbilgisayar.com/arama/'
                       + urllib.parse.quote(str(urun)) + '/')
    for url in [a for a in adaylar if a]:
        html = _fiyat_istek(url, platform)
        if not html:
            continue
        fiyat, urun_url = _fiyat_ayikla(html, platform, urun)
        if fiyat:
            return {'fiyat': fiyat, 'url': urun_url or url, 'ts': time.time()}
    return {}


def _fiyat_bildir(log, ses, baslik, fiyat, eski, url, acilis=False):
    ek = ' (JARVIS kapaliyken)' if acilis else ''
    if fiyat < eski:
        satir = 'SYS: FIYAT | %s%s ucuza girdi! (fiyat: ₺%s)' % (
            baslik[:90], ek, ('%.2f' % fiyat))
    else:
        satir = ('SYS: FIYAT | %s%s çok pahalılaştı!! (artan fiyat: ₺%s)'
                 % (baslik[:90], ek, '%.2f' % fiyat))
    satir += ' | ' + str(url)[:300]
    _yaz(log, satir)
    _sesle(ses, ('%s ucuza girdi: %s' if fiyat < eski else
                 '%s çok pahalılaştı: %s') % (baslik[:60], '%.2f TL' % fiyat))


def fiyat_kontrol(log=None, ses=None, acilis=False):
    veri = _fiyat_veri()
    urunler = veri.get('urunler') or []
    if not urunler:
        return 0
    bildirim = 0
    for urun in urunler:
        ad = str(urun.get('ad') or '')
        if not ad:
            continue
        onceki = urun.get('fiyatlar') or {}
        yeni = {}
        for platform in (urun.get('platformlar') or list(_PLATFORMLAR)):
            try:
                r = _fiyat_platform_cek(platform, ad)
            except Exception:
                r = {}
            if not r:
                if platform in onceki:
                    yeni[platform] = onceki[platform]
                else:
                    _yaz(log, 'SYS: FIYAT | %s (%s): fiyat alinamadi '
                              '(site engeli/captcha). Link takipte: %s'
                         % (ad[:80], platform,
                            str(_fiyat_url(platform, ad))[:220]))
                    yeni[platform] = {'fiyat': 0.0,
                                      'url': _fiyat_url(platform, ad),
                                      'ts': time.time(), 'engel': True}
                continue
            eski = onceki.get(platform) or {}
            eski_f = float(eski.get('fiyat') or 0.0)
            f = float(r.get('fiyat') or 0.0)
            if eski_f > 0 and f > 0:
                if f < eski_f * 0.995 or f > eski_f * 1.005:
                    _fiyat_bildir(log, ses, '%s (%s)' % (ad, platform), f,
                                  eski_f, r.get('url') or '', acilis)
                    bildirim += 1
            else:
                _yaz(log, 'SYS: FIYAT | baslangic %s (%s): ₺%.2f | %s'
                     % (ad[:80], platform, f, str(r.get('url') or '')[:240]))
            yeni[platform] = r
        urun['fiyatlar'] = yeni
    veri['son_kontrol'] = time.time()
    _fiyat_kaydet(veri)
    if bildirim:
        _yaz(log, 'SYS: FIYAT | %d degisim bildirildi.' % bildirim)
    else:
        _yaz(log, 'SYS: FIYAT | kontrol tamam; degisim yok.')
    return bildirim


def _fiyat_ekle(talep, log=None, ses=None):
    t = str(talep or '')
    platformlar = [p for p in _PLATFORMLAR if p.lower() in t.lower()]
    if not platformlar:
        platformlar = list(_PLATFORMLAR)
    ad = t
    ad = re.sub(r'(?i)\b(trendyol|amazon|vatan|idefix|n11|fiyat|takip|'
                r'fiyatını|fiyatini|ucuz|pahalı|pahali|düşerse|duserse|'
                r'çıkarsa|cikarsa|bildir|haber|ver|ekle|bu|ürün|urun|mal|'
                r'istediğim|istedigim|al|satın|satin)\b', ' ', ad)
    ad = re.sub(r'(?i)\b(takip\s*et|fiyat\s*takip|de|da|et|ve|için|icin)\b',
                ' ', ad)
    ad = re.sub(r'\s+', ' ', ad).strip(' .,-:;')
    if len(ad) < 2:
        ad = 'urun'
    veri = _fiyat_veri()
    for u in veri['urunler']:
        if str(u.get('ad') or '').lower() == ad.lower():
            u['platformlar'] = sorted(set((u.get('platformlar') or [])
                                          + platformlar))
            _fiyat_kaydet(veri)
            _yaz(log, 'SYS: FIYAT TAKIP | guncellendi: %s (%s)'
                 % (ad[:100], ', '.join(platformlar)))
            _sesle(ses, 'Fiyat takibi guncellendi: ' + ad[:80])
            return {'durum': 'FIYAT', 'urun': ad, 'platformlar': platformlar}
    veri['urunler'].append({'ad': ad, 'platformlar': platformlar,
                            'fiyatlar': {}, 'eklendi': time.time()})
    _fiyat_kaydet(veri)
    _yaz(log, 'SYS: FIYAT TAKIP | eklendi: %s | platformlar: %s'
         % (ad[:100], ', '.join(platformlar)))
    _sesle(ses, 'Fiyat takibine eklendi: ' + ad[:80])
    threading.Thread(target=fiyat_kontrol, args=(log, ses, False),
                     name='sonsuz2-fiyat-ilk', daemon=True).start()
    return {'durum': 'FIYAT', 'urun': ad, 'platformlar': platformlar}


def fiyat_listele(log=None):
    veri = _fiyat_veri()
    if not veri.get('urunler'):
        _yaz(log, 'SYS: FIYAT | takip listesi bos.')
        return []
    _yaz(log, 'SYS: FIYAT | takip listesi:')
    for u in veri['urunler']:
        parcalar = []
        for p, f in (u.get('fiyatlar') or {}).items():
            parcalar.append('%s=₺%.2f' % (p, float(f.get('fiyat') or 0)))
        _yaz(log, '- %s | %s' % (str(u.get('ad'))[:90],
                                  ', '.join(parcalar) or 'henuz fiyat yok'))
    return veri['urunler']


def _hepsi_mi(metin):
    """'tum urunleri sil' / 'hepsini kaldir' gibi ifadeleri yakalar."""
    m = re.sub(r'\s+', ' ', str(metin or '')).strip().lower()
    if m in ('', 'tum', 'tüm', 'hepsi', 'hepsini', 'butun', 'bütün',
             'tamamı', 'tamami'):
        return True
    return any(k in m for k in (
        'tum ', 'tüm ', 'hepsi', 'hepsini', 'butun', 'bütün', 'tamami',
        'tamamı', 'fiyatlari', 'fiyatları', 'hatirlatmalari',
        'hatırlatmaları', 'hatirlaticilari', 'hatırlatıcıları'))


def fiyat_sil(talep, log=None):
    ad = re.sub(r'(?i)\b(fiyat|takip|listesinden|listeden|kaldir|sil|çıkar|'
                r'cikar|izleme)\b', ' ', str(talep))
    ad = re.sub(r'\s+', ' ', ad).strip(' .,-:;').lower()
    veri = _fiyat_veri()
    once = len(veri['urunler'])
    if _hepsi_mi(ad):
        veri['urunler'] = []
    else:
        veri['urunler'] = [u for u in veri['urunler']
                           if ad not in str(u.get('ad') or '').lower()]
    _fiyat_kaydet(veri)
    _yaz(log, 'SYS: FIYAT | %d urun kaldirildi.' % (once - len(veri['urunler'])))
    return once - len(veri['urunler'])


def _fiyat_dongu():
    global _FIYAT_SON
    while True:
        time.sleep(30.0)
        try:
            if time.time() - _FIYAT_SON >= _FIYAT_ARALIK:
                _FIYAT_SON = time.time()
                fiyat_kontrol(_FIYAT_LOG, None, False)
        except Exception:
            pass


def _fiyat_baslat(log=None, ses=None):
    global _FIYAT_THREAD, _FIYAT_LOG, _FIYAT_SON
    _FIYAT_LOG = log
    veri = _fiyat_veri()
    if _FIYAT_THREAD is None:
        _FIYAT_THREAD = threading.Thread(target=_fiyat_dongu,
                                         name='sonsuz2-fiyat', daemon=True)
        _FIYAT_THREAD.start()
    # Acilista kacirilan degisimleri bildir (arka planda).
    if veri.get('urunler'):
        def _ilk():
            time.sleep(3.0)
            try:
                fiyat_kontrol(log, ses, True)
            except Exception:
                pass
        threading.Thread(target=_ilk, name='sonsuz2-fiyat-acilis',
                         daemon=True).start()
        if time.time() - float(veri.get('son_kontrol') or 0) > 600:
            _yaz(log, 'SYS: FIYAT | JARVIS kapaliyken fiyatlar kontrol '
                      'edilemedi; acilista karsilastiriliyor.')
    return True


# ---------------------------------------------------------------------------
# KENDINI GELISTIRME (eklenti sistemi + olay kaydi)
# ---------------------------------------------------------------------------
_GELISIM_DOSYA = os.path.join(_CFG, 'gelisim.json')
_EKLENTI_KLASOR = os.path.join(_CFG, 'eklentiler')


def gelisim_kaydet(olay, tur='bilgi'):
    try:
        veri = _json_oku(_GELISIM_DOSYA, {'olaylar': [], 'oneriler': []})
        if not isinstance(veri, dict):
            veri = {'olaylar': [], 'oneriler': []}
        veri.setdefault('olaylar', [])
        veri['olaylar'].append({'ts': time.time(), 'tur': str(tur)[:40],
                                'olay': str(olay)[:1000]})
        if len(veri['olaylar']) > 2000:
            veri['olaylar'] = veri['olaylar'][-2000:]
        _json_yaz(_GELISIM_DOSYA, veri)
    except Exception:
        pass


def gelisim_analiz(log=None, ses=None):
    veri = _json_oku(_GELISIM_DOSYA, {'olaylar': [], 'oneriler': []})
    olaylar = (veri.get('olaylar') or [])[-60:]
    hatalar = [o for o in olaylar if str(o.get('tur')) == 'hata']
    ozet = '\n'.join('- %s: %s' % (o.get('tur'), o.get('olay'))
                     for o in olaylar[-25:])
    cevap = _ai(
        'Asagidaki JARVIS olay/hata kayitlarini incele. 3 somut iyilestirme '
        'maddesi yaz; her madde tek satir ve uygulanabilir olsun.\n' + ozet,
        'Sen JARVISin kendi kendini gelistirme denetcisisin. Kisa ve net yaz.',
        50, 500)
    if not cevap:
        cevap = ('1. Basarisiz ag isteklerini 3 kez yeniden dene.\n'
                 '2. Fiyat secicilerini platform bazinda guncelle.\n'
                 '3. Oyun briefini her zaman yerel EXE ile birlikte tamamla.')
    veri['oneriler'] = [x.strip() for x in cevap.splitlines() if x.strip()][:10]
    _json_yaz(_GELISIM_DOSYA, veri)
    _yaz(log, 'SYS: OZ-GELISIM | %d hata incelendi. Oneriler:' % len(hatalar))
    for o in veri['oneriler']:
        _yaz(log, 'SYS: ONERI | ' + o[:300])
    _sesle(ses, 'Kendimi gelistirme analizim hazir; onerileri yazdim.')
    return veri['oneriler']


def _eklenti_yukle(ad):
    yol = os.path.join(_EKLENTI_KLASOR, _slug(ad) + '.py')
    if not os.path.isfile(yol):
        return None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'sonsuz2_eklenti_' + _slug(ad), yol)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def eklenti_calistir(ad, *args, **kwargs):
    mod = _eklenti_yukle(ad)
    if mod is None:
        return None
    fn = getattr(mod, 'calistir', None)
    if not callable(fn):
        return None
    return fn(*args, **kwargs)


def kendini_gelistir(talep, log=None, ses=None):
    """AI ile yeni bir yetenek (eklenti) yazar ve kaydeder."""
    istek = re.sub(r'(?i)\b(kendini|kendini geliştir|gelistir|geliştir|'
                   r'yeni yetenek|yetenek ekle|sınır|sinir|eklenti|'
                   r'ekle|yap)\b', ' ', str(talep))
    istek = re.sub(r'\s+', ' ', istek).strip(' .,-:;')
    if len(istek) < 3:
        istek = 'yeni bir yardimci yetenek'
    kod = _ai(
        'JARVIS icin yeni bir Python eklentisi yaz. Istek: %s\n'
        'Kurallar: sadece standart kutuphane; dosya basinda '
        '"# -*- coding: utf-8 -*-"; "def calistir(log=None, ses=None, '
        '*args, **kwargs):" fonksiyonu olsun; tehlikeli komut (format, '
        'shutdown, diskpart, silme) YOK; sonucu return et; aciklama '
        'yorumlari Turkce olsun. Sadece kod yaz, markdown kullanma.' % istek,
        'Sen JARVISin kendi kendini gelistiren kod ureticisisin.', 60, 1400)
    kod = re.sub(r'^```[a-zA-Z]*\s*', '', str(kod or '').strip())
    kod = re.sub(r'\s*```$', '', kod)
    if not kod or 'def calistir' not in kod:
        _hata(log, 'Kendini gelistirme: AI gecerli eklenti kodu vermedi.')
        _sesle(ses, 'Yeni yetenek kodu uretemedim.')
        return {'durum': 'GELISIM_HATA'}
    if _ju is not None and _ju._tehlikeli(kod):
        _hata(log, 'Eklenti REDDEDILDI: guvenli olmayan komut iceriyor.')
        _sesle(ses, 'Eklenti guvenlik nedeniyle reddedildi.')
        return {'durum': 'GELISIM_RED'}
    try:
        compile(kod, '<eklenti>', 'exec')
    except Exception as e:
        _hata(log, 'Eklenti derleme hatasi: ' + repr(e)[:200])
        return {'durum': 'GELISIM_HATA'}
    os.makedirs(_EKLENTI_KLASOR, exist_ok=True)
    ad = _slug(istek, 30) + '_' + time.strftime('%H%M%S')
    yol = os.path.join(_EKLENTI_KLASOR, ad + '.py')
    try:
        with open(yol, 'w', encoding='utf-8') as f:
            f.write(kod)
    except Exception as e:
        _hata(log, 'Eklenti yazilamadi: ' + repr(e)[:160])
        return {'durum': 'GELISIM_HATA'}
    kayit = _json_oku(os.path.join(_CFG, 'eklentiler.json'), [])
    kayit.append({'ad': ad, 'yol': yol, 'ts': time.time(),
                  'istek': istek[:300]})
    _json_yaz(os.path.join(_CFG, 'eklentiler.json'), kayit)
    gelisim_kaydet('eklenti yazildi: %s | %s' % (ad, istek[:200]), 'gelisim')
    _yaz(log, 'SYS: OZ-GELISIM | yeni yetenek yazildi: ' + yol)
    _sesle(ses, 'Kendimi gelistirdim: yeni yetenek hazir.')
    return {'durum': 'GELISIM', 'dosya': yol, 'ad': ad}


# ---------------------------------------------------------------------------
# OYUN OYNAMA (tum oyunlar, insan benzeri, ban riski dusuk)
# ---------------------------------------------------------------------------
_OYUN_DUR = False
_OYUN_TUS = ('w', 'a', 's', 'd', 'space')


def _json_ayikla(metin):
    """Ic ice JSON nesnelerini dogru ayiklar (vision cevaplari icin)."""
    s = str(metin or '')
    s = re.sub(r'```[a-zA-Z]*', '', s).replace('```', '')
    for i, ch in enumerate(s):
        if ch != '{':
            continue
        derinlik = 0
        metin_icinde = False
        kacis = False
        for j in range(i, min(len(s), i + 1200)):
            c = s[j]
            if metin_icinde:
                if kacis:
                    kacis = False
                elif c == '\\':
                    kacis = True
                elif c == '"':
                    metin_icinde = False
            else:
                if c == '"':
                    metin_icinde = True
                elif c == '{':
                    derinlik += 1
                elif c == '}':
                    derinlik -= 1
                    if derinlik == 0:
                        try:
                            return json.loads(s[i:j + 1])
                        except Exception:
                            break
    return {}


def _oyun_plan(yol, talep):
    cevap = _vizyon(
        yol,
        'Bu bir oyun ekrani. Istek: %s\nSadece JSON yaz: '
        '{"keys":["w"],"ms":250,"neden":"kisa aciklama"} '
        'keys en fazla 2 tus; ms 100-900 arasi. Hile yok, normal oyun '
        'girdisi.' % str(talep)[:200], zaman=50)
    veri = _json_ayikla(cevap)
    tuslar = veri.get('keys') or veri.get('tuslar') or []
    if isinstance(tuslar, str):
        tuslar = [tuslar]
    tuslar = [str(x).lower() for x in tuslar][:3]
    try:
        ms = int(veri.get('ms') or 260)
    except Exception:
        ms = 260
    ms = max(90, min(900, ms))
    neden = str(veri.get('neden') or veri.get('reason') or '')[:120]
    fare = veri.get('mouse') or veri.get('fare') or {}
    try:
        dx = max(-260, min(260, int(fare.get('dx') or 0)))
        dy = max(-260, min(260, int(fare.get('dy') or 0)))
    except Exception:
        dx = dy = 0
    click = bool(veri.get('click') or veri.get('tikla') or False)
    return tuslar, ms, neden, dx, dy, click


def _oyun_tiklama(hwnd, log=None):
    d = _pencere_rect(hwnd)
    if not d:
        return False
    w = max(1, d[2] - d[0])
    h = max(1, d[3] - d[1])
    x = d[0] + int(w * random.uniform(0.30, 0.70))
    y = d[1] + int(h * random.uniform(0.35, 0.75))
    return _tikla(x, y)


def _oyun_baslat(talep, log=None):
    """Istenen oyunu Baslat menusundeki kisayoldan acmayi dener."""
    ad = re.sub(r'(?i)(benim yerime|yerime|oyununu|oyunu|oyun|oyna|oynat|'
                r'afk|aç|ac|başlat|baslat|lütfen|lutfen|bir|bana)', ' ', 
                str(talep or ''))
    ad = re.sub(r'\s+', ' ', ad).strip(' .,-:;').lower()
    if len(ad) < 2:
        return 0, ''
    # Zaten acik olabilir (tarayici basligi ile karismasin).
    h = _pencere_bul((ad,))
    if h and _oyun_penceresi_uygun(h):
        return h, ad
    kls = []
    for kok in (os.path.join(os.environ.get('APPDATA', ''),
                             'Microsoft', 'Windows', 'Start Menu', 'Programs'),
                os.path.join(os.environ.get('PROGRAMDATA', ''),
                             'Microsoft', 'Windows', 'Start Menu', 'Programs')):
        if kok and os.path.isdir(kok):
            kls.append(kok)
    parcalar = [ad] + [p for p in ad.split() if len(p) >= 4]
    bulunan = ''
    for kok in kls:
        for dizin, _alt, dosyalar in os.walk(kok):
            for d in dosyalar:
                if not d.lower().endswith(('.lnk', '.url')):
                    continue
                dl = d.lower()
                if any(p in dl for p in parcalar):
                    bulunan = os.path.join(dizin, d)
                    break
            if bulunan:
                break
        if bulunan:
            break
    if not bulunan:
        _yaz(log, 'SYS: OYUN | "%s" icin kisayol bulunamadi.' % ad)
        return 0, ''
    try:
        _yaz(log, 'SYS: OYUN | baslatiliyor: ' + bulunan)
        os.startfile(bulunan)
    except Exception as e:
        _yaz(log, 'ERR: oyun baslatilamadi: ' + repr(e)[:160])
        return 0, ''
    son = time.time() + 50.0
    while time.time() < son:
        hwnd, baslik = _oyun_penceresi()
        if hwnd:
            return hwnd, baslik
        h = _pencere_bul((ad,))
        if h and _oyun_penceresi_uygun(h):
            return h, ad
        time.sleep(1.0)
    return 0, ''


def _tekrar_say(gecmis, secim, pencere=8):
    n = 0
    for g in gecmis[-pencere:]:
        if tuple(g[:len(secim)]) == tuple(secim):
            n += 1
    return n


def _oyun_rastgele_plan(gecmis):
    havuz = [
        ['w'], ['a'], ['s'], ['d'], ['w', 'shift'], ['w', 'space'],
        ['a', 'space'], ['d', 'shift'], ['w', 'd'], ['w', 'a'],
        ['e'], ['f'], ['r'], ['q'], ['1'], ['2'], ['3'], ['space'], ['tab'],
    ]
    secim = random.choice(havuz)
    for _ in range(20):
        if _tekrar_say(gecmis, secim) < 2:
            break
        secim = random.choice(havuz)
    fare = ((random.randint(-150, 150), random.randint(-90, 90))
            if random.random() < 0.35 else (0, 0))
    tik = random.random() < 0.18
    return secim, random.randint(90, 430), 'guvenli kesif', fare[0], fare[1], tik


def oyun_oyna(talep, log=None, ses=None):
    """Acik oyunu ekran gorerek oynar; insan benzeri, molali, ban riski dusuk."""
    global _OYUN_DUR
    _OYUN_DUR = False
    hwnd, baslik = _oyun_penceresi()
    if not hwnd:
        hwnd, baslik = _oyun_baslat(talep, log)
    if not hwnd:
        _yaz(log, 'SYS: OYUN | acik oyun penceresi bulunamadi. Once bir oyun '
                  'ac; sonra "oyun oyna" de.')
        _sesle(ses, 'Acik oyun penceresi bulamadim.')
        return {'durum': 'OYUN_YOK'}
    _yaz(log, 'SYS: OYUN | hedef: %s | normal klavye/fare, hile yok, '
              'insan benzeri rastgelelik.' % str(baslik)[:120])
    _pencere_on(hwnd)
    time.sleep(0.7)
    afk_baslat(log, ses)
    ekran = os.path.join(_CFG, 'oyun_ekran')
    gecmis = []
    basladi = time.time()
    hamle = 0
    son_vision = 0.0
    sonraki_mola = random.randint(6, 10)
    while not _OYUN_DUR:
        if time.time() - basladi > 30 * 60:
            _yaz(log, 'SYS: OYUN | 30 dakika guvenlik siniri; oturum bitti.')
            break
        try:
            if not ctypes.windll.user32.IsWindow(_wt.HWND(int(hwnd))):
                hwnd, baslik = _oyun_penceresi()
                if not hwnd:
                    _yaz(log, 'SYS: OYUN | oyun penceresi kapandi.')
                    break
        except Exception:
            pass
        # Kullanici aktifse JARVIS girdi gondermesin (insan gibi bekle).
        if _son_girdi_sn() < 1.2:
            time.sleep(0.5)
            continue
        hamle += 1
        try:
            if hamle == 1 or time.time() - son_vision >= 6.0:
                yol = ekran_goruntusu(ekran + '.bmp', hwnd=hwnd)
                tuslar, ms, neden, dx, dy, tik = _oyun_plan(yol, talep)
                son_vision = time.time()
            else:
                tuslar, ms, neden, dx, dy, tik = [], 0, '', 0, 0, False
            if not tuslar and not dx and not dy and not tik:
                tuslar, ms, neden, dx, dy, tik = _oyun_rastgele_plan(gecmis)
            # Ayni hareketi ust uste 3'ten fazla tekrarlama (bot deseni).
            if tuslar and _tekrar_say(gecmis, tuslar, 6) >= 2:
                tuslar, ms, neden, dx, dy, tik = _oyun_rastgele_plan(gecmis)
            if hamle % 3 == 1:
                _pencere_on(hwnd)
            if tuslar:
                _klavye_vur(tuslar, ms)
            if dx or dy:
                _fare_hareket(dx, dy)
            if tik and random.random() < 0.82:
                _fare_tikla_sessiz(random.random() < 0.12)
            anahtar = tuple(tuslar) + (dx // 40, dy // 40, int(tik))
            gecmis.append(anahtar)
            if len(gecmis) > 12:
                del gecmis[0:len(gecmis) - 12]
            if hamle % 2 == 0 or neden:
                _yaz(log, 'SYS: OYUN HAMLE #%d | %s%s | %s'
                     % (hamle, ','.join(tuslar) or 'fare',
                        ' + tik' if tik else '', neden or 'devam'))
            if hamle >= sonraki_mola:
                mola = random.uniform(2.0, 7.0)
                _yaz(log, 'SYS: OYUN | insan molasi %.1f sn.' % mola)
                time.sleep(mola)
                sonraki_mola = hamle + random.randint(6, 11)
                if hamle >= 25 and random.random() < 0.35:
                    uzun = random.uniform(7.0, 15.0)
                    _yaz(log, 'SYS: OYUN | uzun mola %.1f sn (ban riski).' % uzun)
                    time.sleep(uzun)
            else:
                time.sleep(_insansi_bekleme(0.28, 0.6, 1.7))
        except Exception as e:
            _yaz(log, 'ERR: oyun hamlesi: ' + repr(e)[:160])
            time.sleep(1.0)
        if hamle >= 2000:
            _yaz(log, 'SYS: OYUN | 2000 hamle tamam; oturum sonu.')
            break
    _yaz(log, 'SYS: OYUN RAPOR | %d hamle | %.0f sn | hedef: %s'
         % (hamle, time.time() - basladi, str(baslik)[:100]))
    _sesle(ses, 'Oyun oturumu bitti; rapor yazdim.')
    return {'durum': 'OYUN', 'hamle': hamle, 'hedef': baslik}


def oyun_durdur(log=None):
    global _OYUN_DUR
    _OYUN_DUR = True
    _yaz(log, 'SYS: OYUN | durdurma istegi alindi.')
    return True


# ---------------------------------------------------------------------------
# OYUN YAPMA: arastirma + platform secimi + brief + yerel EXE
# ---------------------------------------------------------------------------
def _oyun_hedef_platform(istek):
    t = str(istek or '').lower()
    if 'roblox' in t:
        return 'Roblox (Roblox Studio, Luau, R15/R6)'
    if 'unity' in t:
        return 'Unity (C#)'
    if 'godot' in t:
        return 'Godot (GDScript/C#)'
    if re.search(r'\b(web|html5?|html|taray[ıi]c[ıi]|canvas|js|javascript)\b', t):
        return 'Web (HTML5 Canvas/JS)'
    # Istekte acik platform yoksa ama roblox/ink game benzeri konseptler?
    if 'ink game' in t or 'squid game' in t:
        return 'Roblox (Roblox Studio, Luau, R15/R6)'
    return ''


def _oyun_ozel_bolumler(istek):
    t = str(istek or '').lower()
    bolumler = []

    if 'roblox' in t or _oyun_hedef_platform(istek).startswith('Roblox'):
        rb = [
            'Roblox özel gereksinimleri:',
            '- Roblox Studio projesi/yerine geçen Luau script yapısı; mümkünse Repo/README ile kurulum.',
            '- Karakter: R15 (varsayılan) veya ayarlanabilir R6/R15; Humanoid/Animator kullan.',
            '- Kontroller: WASD hareket + Mouse ile kamera kontrolü (UserInputService/ContextActionService).',
            '- Mobil uyumluluk notu: dokunmatik joystick/düğme desteği eklenebilir.',
            '- Sunucu/istemci ayrımı: Script (ServerScriptService), LocalScript (StarterPlayerScripts), RemoteEvent/RemoteFunction güvenliği.',
            '- Veri: DataStoreService ile bulut kayıt (para, seviye, ayarlar); Studio dışı test notunu README’ye yaz.',
        ]
        if re.search(r'(giriş|giris|login|kayıt|kayit|register|hesap|auth)', t):
            rb += [
                '- Giriş/Kayıt arayüzü: Roblox kullanıcı adıyla oturum akışı; misafir/yerel profil fallback; UI ekranları (Giriş, Kayıt/Profil).',
            ]
        if re.search(r'(avatar|karakter özelleştirme|kostüm|aksesuar)', t):
            rb += ['- Avatar/kostüm: HumanoidDescription veya aksesuar giydirme, önizleme ve kaydetme.']
        if re.search(r'(emote|dans|animasyon)', t):
            rb += ['- Emote sistemi: emote menüsü, animasyon oynatma, cooldown ve sunucu doğrulaması.']
        if re.search(r'(bulut|cloud|datastore|kayıt|save)', t):
            rb += ['- Bulut sistem: DataStore ile profil kaydı, retry/pcall, oturum kilidi/migration notu.']
        if re.search(r'(sekme|tab|menü|arayüz|ui)', t):
            rb += ['- Arayüz sekmeleri: Oyun, Mağaza/Avatar, Ayarlar, Liderlik vb. (ScreenGui + Frame geçişleri).']
        bolumler.append('\n'.join(rb))

    if 'ink game' in t or 'mürekkep oyunu' in t or 'squid game' in t:
        bolumler.append('\n'.join([
            'Ink Game (araştırılan temel mekanikler; Roblox sürümüne göre uyarlayarak uygula):',
            '- Lobi/eşleşme: oyuncu bekleme alanı, hazır olma, tur başlatma, oyuncu listesi.',
            '- 1) Kırmızı Işık Yeşil Işık: ışık durumuna göre hareket/stop; kırmızıda hareket eden elenir.',
            '- 2) Dalgona/Şeker şekli (varsa): şekil çıkarma mini oyunu, zaman/sınır kontrolü.',
            '- 3) Halat Çekme: takım dengesi, ritim/QTE veya güç mekaniği.',
            '- 4) Misket/mini düello (sürümden sürüme değişir): basit adil mini oyun kuralı.',
            '- 5) Cam Köprü/Cam Basamaklar: doğru/yanlış basamak seçimi, düşme/elenme.',
            '- 6) Mingle/oda seçimi (sürümden sürüme değişir): sayı/oda grubuna girme, zaman sınırı.',
            '- 7) Lights Out/gece turu (varsa): hayatta kalma/çatışma kuralları, güvenli alan.',
            '- Final: kalan oyuncular için son tur veya hayatta kalma sonucu.',
            '- Ortak sistemler: eleme/respawn kuralları, tur zamanlayıcısı, ödül/para, skor tablosu, ses/efekt, yeniden başlatma.',
            '- Not: Gerçek Ink Game güncel kuralları değişebilir; mevcut oynanışı araştırıp mekanikleri güncel tut, hileye izin verme.',
        ]))

    if not bolumler:
        return ''
    return '\n\n' + '\n\n'.join(bolumler) + '\n'


def _oyun_bilgi(talep, log=None):
    istek = str(talep or '').strip()
    hedef = _oyun_hedef_platform(istek) or 'kullanıcı isteğine en uygun platform'
    cevap = _ai(
        'Kullanici su oyunu istiyor: %s\n'
        'Bir oyun tasarimcisi/teknik yonetmen gibi arastir ve SADECE su '
        'basliklarla detayli plan yaz:\n'
        'OYUN ADI: ...\nTUR: ...\nPLATFORM: %s\n'
        'HEDEF KITLE: ...\nMEKANIKLER: ...\nKONTROLLER: ...\n'
        'ARAYUZ: ...\nSEVIYELER/TURLAR: ...\nGORSEL STIL: ...\n'
        'SES/EFEKT: ...\nTEKNIK PLAN: ...\n'
        'ARASTIRMA NOTLARI: (istege ozel onemli noktalar)\n'
        'Turkce yaz; en fazla 22 satir; genel laf degil, istege ozel olsun.'
        % (istek[:500], hedef),
        'Sen deneyimli bir oyun tasarimcisi, yapimci ve teknik yonetmensin. '
        'Kullanicinin istedigi platforma ve oyun turune gore cok spesifik plan '
        'uretirsin.', 70, 1400)
    if not cevap:
        hedef = hedef if hedef != 'kullanıcı isteğine en uygun platform' else 'Web (HTML5 Canvas/JS)'
        if hedef.startswith('Roblox'):
            cevap = (
                'OYUN ADI: JARVIS Roblox Oyunu\nTUR: Roblox deneyimi\n'
                'PLATFORM: Roblox (Roblox Studio, Luau)\n'
                'HEDEF KITLE: Roblox oyuncuları\n'
                'MEKANIKLER: hareket, gorev, skor/odul, tur yonetimi\n'
                'KONTROLLER: WASD + Mouse kamera; mobil joystick\n'
                'ARAYUZ: menu, oyun sekmesi, ayarlar, bildirimler\n'
                'SEVIYELER/TURLAR: artan zorluk veya tur sistemi\n'
                'GORSEL STIL: Roblox uyumlu, okunakli, performansli\n'
                'SES/EFEKT: UI ve oyun olay sesleri\n'
                'TEKNIK PLAN: ServerScript/LocalScript/RemoteEvent, DataStore, README\n'
                'ARASTIRMA NOTLARI: istek metnindeki ozel modlari birebir uygula.')
        else:
            cevap = (
                'OYUN ADI: JARVIS Oyunu\nTUR: macera\nPLATFORM: %s\n'
                'HEDEF KITLE: genel\n'
                'MEKANIKLER: hareket, hedef, carpismalar, skor, kazan/kaybet\n'
                'KONTROLLER: WASD/ok tuslari, fare/aksiyon tusu\n'
                'ARAYUZ: ana menu, oyun ici HUD, yeniden baslat\n'
                'SEVIYELER/TURLAR: artan zorluk\n'
                'GORSEL STIL: modern, okunakli\n'
                'SES/EFEKT: temel geri bildirim sesleri\n'
                'TEKNIK PLAN: oynanabilir prototip, test, calistirma paketi\n'
                'ARASTIRMA NOTLARI: kullanici istegini ayrintili uygula.' % hedef)
    satirlar = [s.strip() for s in str(cevap).splitlines() if s.strip()]
    alanlar = {}
    for s in satirlar:
        m = re.match(r'^([A-Za-zÇĞİÖŞÜçğıöşü/ ]{2,28})\s*:\s*(.+)$', s)
        if m:
            alanlar[m.group(1).strip().upper()] = m.group(2).strip()
    ad = alanlar.get('OYUN ADI') or 'JARVIS Oyunu'
    platform = _oyun_hedef_platform(istek) or alanlar.get('PLATFORM') or hedef
    return {'ad': ad[:80], 'platform': platform, 'hedef_platform': platform,
            'alanlar': alanlar, 'satirlar': satirlar, 'ham': cevap,
            'istek': istek}


def _oyun_brief(istek, bilgi):
    a = bilgi.get('alanlar') or {}
    hedef = bilgi.get('hedef_platform') or bilgi.get('platform') or 'uygun platform'
    ad = bilgi.get('ad') or 'oyun'
    satirlar = [
        "merhaba ben Abdülkadir'in kişisel yapay zekası \"J.A.R.V.I.S\" "
        "senden istediğim şey: **%s**" % ad,
        '',
        'İstenen oyun (kullanıcının tam isteği): %s' % str(istek)[:600],
        'Oyun adı: %s' % ad,
        'Tür: %s' % (a.get('TUR') or 'isteğe özel oyun'),
        'Hedef oyun platformu: %s' % hedef,
        'Hedef kitle: %s' % (a.get('HEDEF KITLE') or 'genel oyuncu'),
        'Mekanikler: %s' % (a.get('MEKANIKLER') or 'isteğe özel mekanikler'),
        'Kontroller: %s' % (a.get('KONTROLLER') or 'platforma uygun kontroller'),
        'Arayüz/UI: %s' % (a.get('ARAYUZ') or a.get('ARAYÜZ') or 'menü, HUD, ayarlar'),
        'Seviyeler/Turlar: %s' % (a.get('SEVIYELER/TURLAR') or
                                   a.get('SEVIYELER') or a.get('SEVİYELER') or
                                   'artan zorluk/tur sistemi'),
        'Görsel stil: %s' % (a.get('GORSEL STIL') or a.get('GÖRSEL STIL') or
                              'modern, okunaklı, performanslı'),
        'Ses/Efekt: %s' % (a.get('SES/EFEKT') or 'temel geri bildirim sesleri'),
        'Teknik plan: %s' % (a.get('TEKNIK PLAN') or a.get('TEKNİK PLAN') or
                              'çalışan prototip, temiz kod, test'),
        'Araştırma notları: %s' % (a.get('ARASTIRMA NOTLARI') or
                                     a.get('ARAŞTIRMA NOTLARI') or
                                     'kullanıcının özel isteğini aynen uygula'),
    ]
    satirlar.append(_oyun_ozel_bolumler(istek).rstrip())
    satirlar += [
        'Lütfen bunu ÇALIŞAN bir oyun/proje olarak üret:',
        '1. İstenen hedef oyun platformuna uygun proje iskeletini kur (Roblox istendiyse Roblox Studio/Luau; Unity istendiyse Unity/C#; web istendiyse HTML5/JS).',
        '2. Oyuncu kontrolü, kamera/girdi, çarpışma/etkileşim, skor/ilerleme ve kazanma/kaybetme/eleme döngüsünü eksiksiz yaz.',
        '3. İstenen arayüzleri ekle: menü, sekmeler, giriş/kayıt/bulut/avatar/emote gibi sistemler kullanıcı istediyse mutlaka olsun.',
        '4. Seviye/tur/mini oyun akışını kur; kullanıcı belirli bir oyun modu (örn. Ink Game) istediyse o modların mekaniklerini araştırıp uygula.',
        '5. Ses/efekt, yeniden başlatma, hata durumları ve temel performans ayarlarını ekle.',
        '6. Kodu derle/çalıştır, hataları düzelt ve test et. Çalıştırma adımlarını ve varsa build çıktısını yaz.',
        '7. Kaynak projeyi, kurulum notlarını ve kısa README bırak. Eksik kalan şey varsa açıkça belirtme; önce tamamla.',
        '',
        'Önemli: "Sahibimiz/Abdülkadir geldi, hemen bitir, test et, sahibe ver" şeklinde bir mesaj gelirse mevcut işi güvenli noktada tamamla, test et ve hemen raporla. Böyle bir mesaj gelmezse işi bitir ama istenirse iyileştirmeye devam etmeye hazır ol.',
    ]
    return '\n'.join([s for s in satirlar if s is not None])


_PLATFORM_KILIT = threading.Lock()
_PLATFORM_GOREV = {
    'aktif': False, 'hwnd': 0, 'platform': '', 'istek': '',
    'durum': '', 'basladi': 0.0, 'son_mesaj': 0.0,
    'auto_devam': True, 'handoff': False,
}


def _platform_durum(k=None, d=None):
    with _PLATFORM_KILIT:
        if d is not None:
            _PLATFORM_GOREV.update(d)
        if k:
            return _PLATFORM_GOREV.get(k)
        return dict(_PLATFORM_GOREV)


def _platform_hwnd_canli():
    g = _platform_durum()
    hwnd = int(g.get('hwnd') or 0)
    if not hwnd or not WIN:
        return 0, g
    try:
        if not ctypes.windll.user32.IsWindow(_wt.HWND(hwnd)):
            return 0, g
    except Exception:
        return 0, g
    return hwnd, g


def _platform_mesaj_gonder(mesaj, log=None, ses=None, yeni_satir=True):
    """Aktif AI platform sohbetine mesaj yazar ve gonderir."""
    hwnd, g = _platform_hwnd_canli()
    if not hwnd:
        # Platform adi biliniyorsa pencereyi bulmayi dene.
        ad = str(g.get('platform') or '').lower()
        aday = {'opencode': ('opencode',), 'claude': ('claude',),
                'freebuff': ('freebuff',)}.get(ad)
        if aday:
            hwnd = _pencere_bul(aday)
    if not hwnd:
        _hata(log, 'PLATFORM | aktif sohbet penceresi bulunamadi; '
                   'mesaj gonderilemedi.')
        return False
    try:
        _pencere_on(hwnd)
        time.sleep(0.35)
        sec = {'ad': g.get('platform') or '', 'sohbet': None}
        _sohbet_odakla(hwnd, sec, log)
        gonderildi = False
        try:
            import jarvis_komut_ilet as jk
            if jk._pano_yaz(mesaj):
                time.sleep(0.18)
                jk._tus('ctrl_v')
                time.sleep(0.25)
                gonderildi = True
        except Exception:
            gonderildi = False
        if not gonderildi:
            _yaz_harf(re.sub(r'\s*\n+\s*', ' | ', str(mesaj)), 1.2)
        if yeni_satir:
            time.sleep(0.2)
            _enter()
        _platform_durum(None, {'hwnd': hwnd, 'son_mesaj': time.time()})
        _yaz(log, 'SYS: PLATFORM | mesaj gonderildi -> %s (%d karakter)'
             % (str(g.get('platform') or 'AI')[:40], len(str(mesaj))))
        if ses:
            _sesle(ses, 'Mesaji yapay zekaya ilettim.')
        return True
    except Exception as e:
        _hata(log, 'PLATFORM mesaj hatasi: ' + repr(e)[:180])
        return False


_HANDOFF_MESAJI = (
    "Abdülkadir, yani sahibimiz, şu an geldi. Sanırım kod yazıyorsun, "
    "okuyorsun, değiştiriyorsun veya test ediyorsun. Lütfen ne yapıyorsan "
    "onu güvenli bir noktada HEMEN tamamla, HEMEN test et, varsa hataları "
    "kısaca düzelt ve sonucu HEMEN sahibe (Abdülkadir'e) ver. "
    "Özetle: ne yaptın, hangi dosyalar değişti, nasıl çalıştırılır/test "
    "edilir, kalan bir sorun varsa ne?"
)

_DEVAM_MESAJI = (
    "Sahibimiz şu an devam etmeni istiyor. Lütfen kaldığın yerden devam et: "
    "daha iyi grafik, daha oynanabilir mekanikler, performans/UX iyileştirmeleri "
    "ve araştırdığın yeni özellikleri ekle. Yaptığın her değişikliği kısa "
    "açıkla; kodu derle/çalıştır, hataları düzelt, test et ve güncel sonucu "
    "sahibe raporla."
)


def platform_handoff(log=None, ses=None, neden='kullanici'):
    """Aktif AI gorevine sahibin geldigini bildirir, isi bitirmesini ister."""
    g = _platform_durum()
    if not g.get('aktif') and not g.get('hwnd'):
        _yaz(log, 'SYS: PLATFORM | aktif bir AI gorevi yok.')
        _sesle(ses, 'Aktif bir yapay zeka gorevi bulamadim.')
        return {'durum': 'PLATFORM_YOK'}
    ok = _platform_mesaj_gonder(_HANDOFF_MESAJI, log, ses)
    _platform_durum(None, {'durum': 'handoff', 'handoff': True,
                           'auto_devam': False, 'neden': neden})
    if ok:
        _ack(log, ses, 'Sahibin geldi. Yapay zekaya hemen bitirip test etmesini '
                       've sonucu sana vermesini söyledim.')
    return {'durum': 'PLATFORM_HANDOFF' if ok else 'PLATFORM_HATA', 'ok': ok}


def platform_devam(log=None, ses=None):
    """Aktif AI gorevine devam/iyilestirme talimati gonderir."""
    g = _platform_durum()
    if not g.get('aktif') and not g.get('hwnd'):
        _yaz(log, 'SYS: PLATFORM | devam edilecek aktif AI gorevi yok.')
        _sesle(ses, 'Devam edecek aktif yapay zeka gorevi bulamadim.')
        return {'durum': 'PLATFORM_YOK'}
    ok = _platform_mesaj_gonder(_DEVAM_MESAJI, log, ses)
    _platform_durum(None, {'durum': 'devam', 'handoff': False,
                           'auto_devam': True})
    if ok:
        _ack(log, ses, 'Yapay zekaya kaldığı yerden devam etmesini ve '
                       'iyileştirmesini söyledim.')
    return {'durum': 'PLATFORM_DEVAM' if ok else 'PLATFORM_HATA', 'ok': ok}


def _platform_bitti_mi(hwnd, log=None):
    """Ekran goruntusunden AI yanitinin bitip girdi bekledigini tahmin eder."""
    if not hwnd:
        return False
    yol = ekran_goruntusu(os.path.join(_CFG, 'platform_durum.bmp'), hwnd=hwnd)
    if not yol:
        return False
    cevap = _vizyon(
        yol,
        'Bu bir AI sohbet/coding uygulamasi. Model/ajan su an YANIT URETIYOR MU '
        '(yaziyor, dusunuyor, calisiyor), yoksa YANITI BITMIS ve yeni kullanici '
        'mesaji/girdi bekliyor mu? Sadece tek kelime yaz: BITTI veya CALISIYOR.',
        zaman=45)
    c = str(cevap or '').upper()
    if 'BITTI' in c and 'CALISIYOR' not in c:
        _yaz(log, 'SYS: PLATFORM | ekran analizi: AI yaniti bitmis gorunuyor.')
        return True
    return False


def _platform_izle(hwnd, istek, log=None, ses=None):
    """AI gorevi bittiginde (handoff yoksa) otomatik devam ister."""
    t0 = time.time()
    devam_say = 0
    while True:
        time.sleep(75.0)
        g = _platform_durum()
        if not g.get('aktif') or g.get('handoff') or not g.get('auto_devam'):
            return
        if time.time() - t0 > 3 * 3600:
            _platform_durum(None, {'aktif': False, 'durum': 'zaman_asimi'})
            return
        try:
            if not ctypes.windll.user32.IsWindow(_wt.HWND(int(hwnd))):
                _platform_durum(None, {'aktif': False, 'durum': 'pencere_kapandi'})
                return
        except Exception:
            pass
        # Kullanici son 20 sn icinde klavye/fare kullandiysa mudahale etme.
        try:
            if _son_girdi_sn() < 20.0:
                continue
        except Exception:
            pass
        if devam_say >= 3:
            _yaz(log, 'SYS: PLATFORM | otomatik devam limiti doldu (3).')
            _platform_durum(None, {'aktif': False, 'durum': 'devam_limiti'})
            _sesle(ses, 'Yapay zeka gorevi icin otomatik devam limiti doldu.')
            return
        if time.time() - float(g.get('son_mesaj') or 0) < 120.0:
            continue
        try:
            if _platform_bitti_mi(hwnd, log):
                devam_say += 1
                _yaz(log, 'SYS: PLATFORM | AI bitmis gorunuyor; devam/iyilestirme '
                          'istiyorum (%d/3).' % devam_say)
                _platform_mesaj_gonder(_DEVAM_MESAJI, log, ses)
                _platform_durum(None, {'durum': 'auto_devam',
                                       'devam_say': devam_say})
        except Exception as e:
            _yaz(log, 'SYS: PLATFORM izleme hatasi: ' + repr(e)[:140])


def _platform_adaylari():
    adaylar = []
    try:
        la = os.environ.get('LOCALAPPDATA', '') or ''
        opencode = os.path.join(la, 'Programs', '@opencodedesktop',
                                'OpenCode.exe')
        if not os.path.isfile(opencode):
            opencode = shutil.which('opencode') or ''
        if opencode:
            adaylar.append({
                'ad': 'OpenCode', 'tip': 'chat', 'yol': opencode,
                'komut': shutil.which('opencode') or '',
                'pencere': ('opencode',), 'puan': 30,
                'hesap_aktif': True, 'oncelik': 20})
    except Exception:
        pass
    try:
        import jarvis_komut_ilet as jk
        for a in jk.arac_tara():
            ad = str(a.get('ad') or '')
            if ad.lower() in ('claude', 'freebuff'):
                k = dict(a)
                k['oncelik'] = 15 if ad.lower() == 'claude' else 10
                adaylar.append(k)
    except Exception:
        pass
    puanli = []
    for a in adaylar:
        p = int(a.get('puan') or 0)
        if a.get('yol') and os.path.isfile(str(a.get('yol'))):
            p += 100
        if a.get('hesap_aktif'):
            p += 30
        if a.get('komut'):
            p += 15
        p += int(a.get('oncelik') or 0)
        k = dict(a)
        k['secim_puani'] = p
        puanli.append(k)
    puanli.sort(key=lambda x: -int(x.get('secim_puani') or 0))
    return puanli


def _platform_sec(log=None):
    adaylar = _platform_adaylari()
    if not adaylar:
        _yaz(log, 'SYS: PLATFORM | OpenCode/Claude/Freebuff bulunamadi; '
                  'gorevi yerelde kendim yapacagim.')
        return None, adaylar
    sec = adaylar[0]
    _yaz(log, 'SYS: PLATFORM | adaylar: ' + ', '.join(
        '%s(%d)' % (a.get('ad'), a.get('secim_puani', 0))
        for a in adaylar))
    _yaz(log, 'SYS: PLATFORM | secim: %s | gerekce: kurulu/aktif ve en '
              'uygun puan.' % sec.get('ad'))
    return sec, adaylar


def _platform_ac(a, log=None):
    if not a:
        return 0
    try:
        import jarvis_komut_ilet as jk
        yol = str(a.get('yol') or '')
        if yol and os.path.isfile(yol):
            subprocess.Popen([yol], cwd=os.path.dirname(yol))
        else:
            ok = jk._arac_ac(a, log)
            if not ok:
                return 0
        parcalar = a.get('pencere') or (str(a.get('ad') or '').lower(),)
        son = time.time() + 45.0
        while time.time() < son:
            h = jk.pencere_bul(parcalar)
            if h:
                jk.pencere_one(h)
                time.sleep(1.0)
                return h
            time.sleep(0.5)
    except Exception as e:
        _hata(log, 'Platform acilamadi: ' + repr(e)[:200])
    return 0


def _sohbet_odakla(hwnd, a, log=None):
    """Once bilinen kisayol/konum, sonra gorsel AI ile sohbet kutusu."""
    try:
        import jarvis_komut_ilet as jk
        jk.pencere_one(hwnd)
        time.sleep(0.6)
        sohbet = a.get('sohbet')
        if sohbet:
            jk._tus(sohbet)
            time.sleep(0.8)
        d = _pencere_rect(hwnd)
        if not d:
            return False
        # 1) Guvenli varsayilan: alt orta.
        w = d[2] - d[0]
        h = d[3] - d[1]
        _tikla(d[0] + int(w * 0.50), d[1] + int(h * 0.92))
        time.sleep(0.5)
        # 2) Gorsel AI: sohbet girdi alanini bul.
        yol = ekran_goruntusu(os.path.join(_CFG, 'sohbet_ekran.bmp'),
                              hwnd=hwnd)
        if yol:
            cevap = _vizyon(
                yol,
                'Bu uygulama penceresi. Sohbet/mesaj yazma girdi alaninin '
                'MERKEZINI goreli olarak ver. Sadece JSON: '
                '{"rx":0.5,"ry":0.9,"var":true}', zaman=45)
            veri = _json_ayikla(cevap)
            try:
                rx = float(veri.get('rx'))
                ry = float(veri.get('ry'))
                if 0.0 <= rx <= 1.0 and 0.0 <= ry <= 1.0:
                    _tikla(d[0] + int(w * rx), d[1] + int(h * ry))
                    time.sleep(0.5)
                    _yaz(log, 'SYS: SOHBET | girdi alani gorsel AI ile '
                              'bulundu (%.2f, %.2f).' % (rx, ry))
                    return True
            except Exception:
                pass
        _yaz(log, 'SYS: SOHBET | girdi alani varsayilan konumdan odaklandi.')
        return True
    except Exception as e:
        _hata(log, 'Sohbet odaklanamadi: ' + repr(e)[:200])
        return False


def _sohbeti_dogrula(hwnd, log=None):
    yol = ekran_goruntusu(os.path.join(_CFG, 'sohbet_dogrula.bmp'),
                          hwnd=hwnd)
    if not yol:
        return ''
    cevap = _vizyon(
        yol,
        'Bu ekran goruntusunde sohbet uygulamasi acik mi, mesaj yazma alani '
        'gorunuyor mu? Kisa cevap ver: EVET veya HAYIR + tek cumle neden.',
        zaman=40)
    if cevap:
        _yaz(log, 'SYS: SOHBET DOGRULAMA | ' + cevap[:300].replace('\n', ' '))
    return cevap


def platform_gorev(istek, log=None, ses=None):
    bilgi = _oyun_bilgi(istek, log)
    brief = _oyun_brief(istek, bilgi)
    hedef = bilgi.get('hedef_platform') or bilgi.get('platform')
    _yaz(log, 'JARVIS: Oyun arastirmasi tamam: %s | hedef platform: %s'
         % (bilgi.get('ad'), hedef))
    for s in bilgi.get('satirlar') or []:
        _yaz(log, 'PLAN | ' + s[:300])
    sec, adaylar = _platform_sec(log)
    if not sec:
        _sesle(ses, 'Platform bulamadim; gorevi yerelde yapmayi deneyecegim.')
        return {'durum': 'PLATFORM_YOK', 'brief': brief, 'bilgi': bilgi}
    hwnd = _platform_ac(sec, log)
    if not hwnd:
        _hata(log, 'Platform penceresi acilmadi: ' + str(sec.get('ad')))
        _sesle(ses, 'Platformu acamadim; gorevi kendim yapmayi deneyecegim.')
        return {'durum': 'PLATFORM_HATA', 'brief': brief, 'bilgi': bilgi}
    _platform_durum(None, {
        'aktif': True, 'hwnd': int(hwnd), 'platform': str(sec.get('ad') or ''),
        'istek': str(istek)[:500], 'durum': 'calisiyor',
        'basladi': time.time(), 'son_mesaj': time.time(),
        'auto_devam': True, 'handoff': False, 'devam_say': 0})
    _yaz(log, 'SYS: PLATFORM | %s acildi. Sohbet kismi hazirlaniyor. '
              '("dur/durabilirsin/yeter" dersen sahibin geldi deyip bitirmesini '
              'isteyecegim; durmazsan bitince devam/iyilestirme isteyebilirim.)'
         % sec.get('ad'))
    _sohbet_odakla(hwnd, sec, log)
    _sohbeti_dogrula(hwnd, log)
    # 1) "merhaba" - 0.2 saniyede harf harf (ayni mesajin basi)
    _yaz_harf('merhaba', 0.2)
    time.sleep(_insansi_bekleme(0.22, 0.85, 1.2))
    _yaz(log, 'SYS: SOHBET | "merhaba" 0.2 sn icinde harf harf yazildi.')
    # 2) Briefin geri kalani: ayni mesaja panodan yapistir, tek Enter ile gonder.
    kalan = brief
    if kalan.lower().startswith('merhaba'):
        kalan = kalan[len('merhaba'):]
    gonderildi = False
    try:
        import jarvis_komut_ilet as jk
        if kalan.strip() and jk._pano_yaz(kalan):
            time.sleep(0.25)
            jk._tus('ctrl_v')
            time.sleep(_insansi_bekleme(0.55, 0.85, 1.2))
            gonderildi = True
            _yaz(log, 'SYS: SOHBET | detayli brief panodan tek mesaja '
                      'yapistirildi (%d karakter).' % len(kalan))
    except Exception:
        gonderildi = False
    if not gonderildi:
        # Pano yoksa tek satirlik metin olarak harf harf yaz (erken gonderim yok).
        kalan_tek = re.sub(r'\s*\n+\s*', ' | ', kalan).strip()
        _yaz_harf(kalan_tek, max(4.0, min(18.0, len(kalan_tek) / 120.0)))
        _yaz(log, 'SYS: SOHBET | detayli brief harf harf yazildi.')
    time.sleep(_insansi_bekleme(0.45, 0.8, 1.2))
    _enter()
    time.sleep(1.0)
    _platform_durum(None, {'son_mesaj': time.time()})
    _sohbeti_dogrula(hwnd, log)
    _yaz(log, 'JARVIS: Tek mesaj gonderildi -> %s | hedef: %s'
         % (sec.get('ad'), hedef))
    _sesle(ses, 'Oyun briefini %s uzerinden gonderdim. Bitirmesini istersem '
                 'dur/yeter de; devam etmesini istersem devam et de.'
           % sec.get('ad'))
    # Otomatik devam izleyicisi (handoff yoksa).
    try:
        threading.Thread(target=_platform_izle,
                         args=(hwnd, istek, log, ses),
                         name='sonsuz2-platform-izle', daemon=True).start()
    except Exception:
        pass
    return {'durum': 'PLATFORM', 'platform': sec.get('ad'), 'hwnd': hwnd,
            'brief': brief, 'bilgi': bilgi, 'adaylar': [
                a.get('ad') for a in adaylar]}


def _oyun_klasoru(ad):
    try:
        belge = os.path.join(os.path.expanduser('~'), 'Documents')
    except Exception:
        belge = _KOK
    klasor = os.path.join(belge, 'JARVIS_Oyunlar',
                          '%s_%s' % (_slug(ad, 30), time.strftime('%Y%m%d_%H%M%S')))
    try:
        os.makedirs(klasor, exist_ok=True)
    except Exception:
        klasor = os.path.join(_URETIM, 'oyun_' + time.strftime('%H%M%S'))
        os.makedirs(klasor, exist_ok=True)
    return klasor


def oyun_yap(talep, log=None, ses=None):
    """Oyunu arastirir, platforma brief yollar, yerelde EXE uretir."""
    istek = str(talep or '').strip()
    if len(istek) < 3:
        istek = 'basit bir macera oyunu'
    plat = {}
    try:
        plat = platform_gorev(istek, log, ses) or {}
    except Exception as e:
        _hata(log, 'Platform gorevi hatasi: ' + repr(e)[:200])
    bilgi = plat.get('bilgi') or _oyun_bilgi(istek, log)
    brief = plat.get('brief') or _oyun_brief(istek, bilgi)
    hedef = str(bilgi.get('hedef_platform') or bilgi.get('platform') or '')
    klasor = _oyun_klasoru(bilgi.get('ad') or istek)
    # Brief/README'yi her zaman kaydet (ozellikle Roblox/Unity icin).
    try:
        with open(os.path.join(klasor, 'JARVIS_OYUN_BRIEF.txt'),
                  'w', encoding='utf-8') as f:
            f.write(brief)
    except Exception:
        pass
    try:
        with open(os.path.join(klasor, 'README.md'), 'w', encoding='utf-8') as f:
            f.write('# %s\n\n' % (bilgi.get('ad') or 'JARVIS Oyunu'))
            f.write('Istek: %s\n\n' % istek)
            f.write('Hedef platform: %s\n\n' % hedef)
            f.write('## Brief\n\n')
            f.write(brief.replace('merhaba ', 'Merhaba ', 1))
    except Exception:
        pass
    exe = ''
    html = ''
    roblox_mu = hedef.lower().startswith('roblox') or 'roblox' in str(istek).lower()
    if roblox_mu:
        _yaz(log, 'JARVIS: Roblox hedefi icin ayrintili brief AI platformuna '
                  'gonderildi ve klasore kaydedildi -> ' + klasor)
        _yaz(log, 'SYS: ROBLOX | Gercek Roblox oyunu/yer dosyasi icin '
                  'OpenCode/Claude/Freebuff ve/veya Roblox Studio uretimi '
                  'takip edilir. "dur/yeter" dersen sahibin geldi deyip bitirmesini '
                  'isterim; "devam et" dersen iyilestirmesini isterim.')
        if plat.get('durum') != 'PLATFORM':
            _yaz(log, 'SYS: ROBLOX | AI platformu baglanamadiysa brief/README '
                      'ile yerel iskelet hazir; Roblox Studio adimlarini README '
                      've brief belirtiyor.')
    else:
        _yaz(log, 'JARVIS: Yerel oyun uretimi basliyor -> ' + klasor)
        _sesle(ses, 'Oyunu simdi kendim uretiyor ve EXE yapiyorum.')
        sonuc = None
        try:
            import jarvis_oyun_exe as joe
            sonuc = joe.oyun_exe_yap(istek + '\n' + brief, klasor, log, ac=True)
        except Exception as e:
            _hata(log, 'Oyun EXE hattinda hata: ' + repr(e)[:220])
        if isinstance(sonuc, dict):
            exe = str(sonuc.get('exe') or '')
            html = str(sonuc.get('html') or '')
        if not exe:
            try:
                import jarvis_hakem as jh
                h = jh.oyun_uret_hakemli(istek + '\n' + brief, 'web', klasor,
                                         log, ac=True)
                html = str((h or {}).get('dosya') or '')
                if html and _ju is not None:
                    exe = _ju._exe_yap(html, bilgi.get('ad') or 'JarvisOyun',
                                       klasor, log) or ''
            except Exception as e:
                _hata(log, 'Yerel oyun uretimi basarisiz: ' + repr(e)[:220])
        if not exe and html:
            _yaz(log, 'SYS: OYUN | EXE uretilemedi; oynanabilir HTML hazir: '
                      + html)
        if exe:
            _yaz(log, 'JARVIS: OYUN HAZIR (EXE) -> ' + exe)
        else:
            _yaz(log, 'ERR: OYUN | EXE uretilemedi. HTML: ' + str(html))
        _sesle(ses, ('Oyun hazir; EXE calistiriliyor.' if exe else
                     'Brief hazir; oynanabilir cikti icin AI platformunu da kullaniyorum.'))
    try:
        kayit = {'dosya': exe or html or os.path.join(klasor, 'README.md'),
                 'exe': exe, 'html': html, 'brief': os.path.join(klasor, 'JARVIS_OYUN_BRIEF.txt'),
                 'klasor': klasor, 'talep': istek[:300],
                 'hedef_platform': hedef, 'kazanan': 'JARVIS v2', 'ts': int(time.time())}
        _json_yaz(os.path.join(_KOK, 'memory', 'son_oyun.json'), kayit)
    except Exception:
        pass
    return {'durum': 'OYUN_YAP', 'exe': exe, 'html': html,
            'klasor': klasor, 'platform': plat.get('platform'),
            'hedef_platform': hedef, 'bilgi': bilgi}


# ---------------------------------------------------------------------------
# SOHBET / KOMUT SINIFI (cevre: komut mu sohbet mu ikisi mi?)
# ---------------------------------------------------------------------------
_KOMUT_SHORTCUTS = [
    # (kategori, desenler, cevap_fonksiyonu veya sabit cevap)
    ('komut', r'zil çal|zil çaldır|zil çalsın|zili aç|zili kapat|zili sustur|zili devre dışı|ses çaldır|bip ver|bip çaldır|sesli uyarı|ses uyarısı|alarm çaldır|alarmı aç|alarm|uyarı sesi', None, 'zil'),
    ('komut', r'10 sn sonra|10 dk sonra|sn sonra|dk sonra|saatte|hatırlat|hatırlatıcı kur|hatırlatma ekle|anımsat|unutma|hatırlatıcı', None, 'hatirlatici'),
    ('komut', r'kronometre|zamanlayıcı|saniye say|süreölçer|sayaç başlat|sayacı durdur|zamanıölç|zamanı bitir', None, 'kronometre'),
    ('komut', r'oyun oyna|oyunu başlat|oyunu çalıştır|oyun yap|roblox oynay|ink game|minecraft oyna|fortnite oynay|pubg oynay|valorant oynay|lol oynay|cs go|cs2|dota|among us|gta|fifa|pes|league|overwatch|apex|genshin|honkai|pubg mobile|free fire|call of duty', None, 'oyun'),
    ('komut', r'yapay zeka aç|ai aç|sohbet et|sohbet aç|gpt aç|claude aç|bard aç|gemini aç|yapay zekayla konuş|botla konuş|asistan aç', None, 'ai_sohbet'),
    ('komut', r'gmail|mail gönder|e-posta|e posta|mesaj gönder|eposta yolla|posta gönder|mail at|mail yolla', None, 'gmail'),
    ('komut', r'nedir|ne demek|nasıl olur|nasıl yapılır|bilimsel cevap|fen cevabı|fizik|kimya|biyoloji|matematik|arastır|araştır|araştırma yap|düşün|incele|inceleme yap|ne kadar|hangi|nedir bu|bu nedir', None, 'bilimsel'),
    ('komut', r'ekranı gör|ekranı al|ekran görüntüsü|screenshot|ekranı kaydet|ekranı yakala|ekran paylaş|ekranı izle|görüntüyü al', None, 'ekran'),
    ('komut', r'klavye kontrol|klavyeyi kontrol et|klavye kullandır|tuş bas|tuşlara bas|klavyeye yaz|yazdıracaksın|klavye komutu', None, 'klavye'),
    ('komut', r'fare kontrol|fareyi kontrol et|mouse kullan|fareyi kullan|fare hareket|mouse hareket|fare tıkla|mouse tıkla|hedef bas|hedefe bas|tıkla|fareye bas|mouseye bas', None, 'fare'),
    ('komut', r'araştır|araştırma yap|araştır ve söyle|araştırıp anla|araştırıp yaz|araştırıp ekrana yaz|araştırıp sohbete yaz', None, 'arastirma'),
    # -- Kernel: uygulama/web/volume/hesap/hava/tercume/wiki (gercek eylem)
    ('komut', r'not defteri|notepad|hesap makinesi|hesap mak|calculator|paint|mspaint|word|excel|regedit|g[öo]rev y[öo]netic|gorev yonetici|task manager|terminal', None, 'uygulama'),
    ('komut', r'googl[eı].?d[ae].?ara|araştır google|arama ?yap|search for|internet.?te ara|ara:? "(.*)"|youtube.?d[ae].?(ara|aç|ac)|youtubede',
              None, 'web_ara'),
    ('komut', r'\bses(?:ler)?\s*(aç|art|azalt|kapat|sustur|düzey)|volume\s*(up|down|mute)', None, 'ses'),
    ('komut', r'çevir|çeviri|translate|ingilizceye|türkçeye', None, 'tercume'),
    ('komut', r'\bhava\b|weather|sıcaklık kaç|yağmur var', None, 'hava'),
    ('komut', r'wiki|vikipedi|wikipedia', None, 'wiki'),
    ('komut', r'hesapla|topla|çıkar|çarp|carp|böl|[0-9]+\s*[\+\-\*/]{1,2}\s*[0-9]+', None, 'hesapla'),
    ('sohbet', r'merhaba|selam|naber|nasılsın|iyi misin|keyif|hey|hi|sa\b|selm|meraba|merhana', None, 'selamla'),
    ('sohbet', r'kimsin|adın ne|sen nesin|nesin sen|seni kim yaptı|kim yaptı|yaptın|yapımcı|yaratçı|sen kimsin', None, 'kimim'),
    ('sohbet', r'ne yapabilirsin|neler yapabilirsin|yetenek|yardım|komut|liste|özellik|ne kadarşey yapar', None, 'yetenek'),
    ('sohbet', r'teşekkür|sağ ol|eyvallah|teşekkürler', None, 'rica'),
    ('sohbet', r'günaydın|iyi akşamlar|iyi geceler|iyi geceler', None, 'selam'),
    ('sohbet', r'saat|tarih|bugün günlerden|şu an|zaman ne', None, 'saat'),
]
_KOMUT_KISA = [c for c in _KOMUT_SHORTCUTS if len(c[0]) > 0]

def _komut_tipi_bul(t):
    """Komut mu, sohbet mu, ikisi mi? Doner: (tur, kod) | (None, None)"""
    komut_kod = None
    for kategori, desen, _, kod in _KOMUT_SHORTCUTS:
        if kategori == 'komut' and re.search(desen, t):
            komut_kod = kod
            break
    sohbet = any(re.search(desen, t) for kategori, desen, _, kod in _KOMUT_SHORTCUTS if kategori == 'sohbet')
    if komut_kod and sohbet: return ('iki', komut_kod)
    if komut_kod: return ('komut', komut_kod)
    if sohbet: return ('sohbet', None)
    return (None, None)

def _komut_calistir(kod, t):
    """Komut kodu bazli calistirma"""
    if kod == 'zil':
        return ('Zil sesi çaldırıyorum: Bip! Bip! Zil çaldı. '
                'Ne için çalsın istersen söyler misin? Örn: "10 dakika sonra zil çalsın"')
    if kod == 'hatirlatici':
        return ('Hatırlatıcı kurulumuna geçiyorum. Kaç saniye/dakika sonra hatırlatayım? '
                'Örn: "10 saniye sonra hatırlat" veya "5 dakika sonra toplantı hatırlatıcısı"')
    if kod == 'kronometre':
        return ('Kronometre başlatılıyor. Saniyeyi sayıyorum: 1, 2, 3... '
                'Durdurmak için "kronometreyi durdur" der misin?')
    if kod == 'oyun':
        return ('Oyun moduna geçiyorum. Roblox / Unity / Godot / tarayıcı oyunu oynayabilirim. '
                'Hangi oyunu oynamak istiyorsun? Örn: "Roblox ink game oyna", "Minecraft aç"')
    if kod == 'ai_sohbet':
        return ('Yapay zeka sohbeti açılıyor. Sana özel bir sohbet penceresi hazırlanıyor. '
                'Ne hakkında konuşmak istersin? Bilimsel, eğlenceli, teknik her konuda yanıtlayabilirim.')
    if kod == 'gmail':
        return ('Gmail mesajlaşma hazırlanıyor. Kime mesaj atmak istiyorsun? '
                'Alıcı, konu ve ileti içeriğini söyler misin? Örn: "Ahmet\'e selam mesajı at"')
    if kod == 'bilimsel':
        return ('Bilimsel cevap hazırlanıyor. Sorduğun konu üzerine araştırma yapıyorum ve '
                'doğrulanan, kaynaklanabilir bir bilimsel yanıt vereceğim. Ne hakkında bilgi istersin?')
    if kod == 'ekran':
        return ('Ekran görüntüsü alınıyor. Şu anki ekran yakalanıyor ve size sunuluyor. '
                'Ekran üzerinde neyi görmek veya değiştirmek istiyorsun?')
    if kod == 'klavye':
        return ('Klavye kontrol modu aktif. Klavyede tuş basabilir, metin yazabilirim. '
                'Hangi tuşları veya metni yazdırmak istiyorsun?')
    if kod == 'fare':
        return ('Fare (mouse) kontrol modu aktif. Fare hareket ettirilir, hedefe tıklanabilir. '
                'Nereye tıklamak veya hareket ettirmek istiyorsun? Örn: "hedefe bas", "fareyi sola hareket et"')
    if kod == 'arastirma':
        return ('Araştırma modu başlatılıyor. Önce konuyu araştırıyorum, sonra ekrana bakıp '
                'sohbet bölümüne tıklıyorum, araştırdığını özgün veya kopyalama içeriği yazıyorum ve onu çalıştırıyorum. '
                'Hangi konuyu araştırmamı istersin?')
    return None


# ---------------------------------------------------------------------------
# KOMUT CEKIRDEGI (kernel): milyonlarca sozum TEK gramerle cozer, satir
# sismeden. Sayi/sure/parametre cikarimi + gercek eylemler (PowerShell yok).
# ---------------------------------------------------------------------------
_K_SAYI_SOZ = {'bir': 1, 'iki': 2, 'uc': 3, 'üç': 3, 'dort': 4, 'dört': 4,
               'bes': 5, 'beş': 5, 'alti': 6, 'altı': 6, 'yedi': 7,
               'sekiz': 8, 'dokuz': 9, 'on': 10, 'onbes': 15, 'yirmi': 20,
               'otuz': 30, 'kirk': 40, 'kırk': 40, 'elli': 50,
               'altmis': 60, 'altmış': 60, 'yetmis': 70, 'yetmiş': 70,
               'seksen': 80, 'doksan': 90, 'yuz': 100, 'yüz': 100,
               'bin': 1000, 'milyon': 1000000}
_K_SURE_KAT = [('sn', 1.0), ('saniye', 1.0), ('dk', 60.0), ('dakika', 60.0),
               ('saat', 3600.0), ('gün', 86400.0), ('gun', 86400.0),
               ('hafta', 604800.0), ('ms', 0.001), ('milisaniye', 0.001)]
_K_SURE_DESEN = re.compile(r'(\d{1,9})\s*(' + '|'.join(k for k, _ in _K_SURE_KAT) + r')')


def _kernel_sayi(t):
    """Sayi ceker: '3 kere zil cal' -> 3 | 'bes kez' -> 5; yoksa 1."""
    m = re.search(r'(?<!\d)(\d{1,9})(?!\d)\s*(?:kere|defa|tane|kez|bip)', t)
    if m:
        return int(m.group(1))
    for w, v in _K_SAYI_SOZ.items():
        if re.search(r'(?<![\w])' + w + r'(?![\w])\s*(?:kere|defa|tane|kez|bip)', t):
            return v
    m = re.search(r'(?<!\d)(\d{1,9})(?!\d)', t)
    if m:
        return int(m.group(1))
    return 1


def _kernel_sure(t):
    """Sure ceker: '10 dakika sonra zil cal' -> 600.0; yoksa None."""
    m = _K_SURE_DESEN.search(t)
    if m:
        for k, kat in _K_SURE_KAT:
            if k == m.group(2):
                return float(m.group(1)) * kat
    for w, v in _K_SAYI_SOZ.items():
        for k, kat in _K_SURE_KAT:
            if re.search(r'(?<![\w])' + w + r'\s+' + k, t):
                return float(v) * kat
    return None


def _zil_bip(n=1):
    for _ in range(max(1, int(n or 1))):
        try:
            ctypes.windll.kernel32.Beep(880, 350)
        except Exception:
            pass
        time.sleep(0.25)


_UYGULAMALAR = [('not defteri|notepad', 'notepad.exe'),
                ('hesap makinesi|hesap mak|calculator|calc', 'calc.exe'),
                ('paint|mspaint', 'mspaint.exe'),
                ('g[öo]rev y[öo]netic|gorev yonetici|task manager', 'taskmgr.exe'),
                ('regedit|kay[ıi]t defteri', 'regedit.exe')]


def _komut_uzay_say():
    """Aktif komut uzayi buyuklugunu tahmin eder (sozum bicimi x parametre)."""
    sayi_biçimi = 999999          # 1..999999 sayisal deger
    soz_biçimi = len(_K_SAYI_SOZ)
    sure = len(_K_SURE_KAT) * (999 + soz_biçimi)
    aile = len(_KOMUT_SHORTCUTS)
    aile_varyant = 12             # her aile icin fiil/nesne varyasyonu
    return aile * aile_varyant * (sayi_biçimi + soz_biçimi) * (sure + 1)


def _komut_uygula(kod, talep, t, log=None, ses=None):
    """Komut kodu -> GERCEK eylem. Is bitirilmediyse None; o zaman eski
    akis/calistir devamasindan sorumlu (hatirlat, oyun, sohbet AI...).
    Eylem: ses cikarma/sure kurma/klavye/fare/ekran/web — PowerShell yok."""
    try:
        sayi = _kernel_sayi(t)
        sure = _kernel_sure(t)
        if kod == 'zil':
            if sure:
                _hatirlat_ekle('Zil çal!', sure, log, ses)
                _ack(log, ses, 'Zil: %.0f sn sonra çalınacak. Unutmayacağım.'
                     % sure)
            else:
                threading.Thread(target=_zil_bip, args=(sayi,),
                                 daemon=True).start()
                _ack(log, ses, 'Zil çalındı! İsteğin varsa "10 sn sonra zil '
                               'çal" ya da "beni 5 dk sonra hatırlat".')
            return {'tur': 'komut', 'kod': kod}
        if kod == 'kronometre':
            _hatirlat_ekle('Kronometre: süre doldu (%d saniye)' % sayi,
                           float(max(1, sayi)), log, ses)
            _ack(log, ses, 'Kronometre kuruldu: %d sn sonra haber vereceğim.'
                 % sayi)
            return {'tur': 'komut', 'kod': kod}
        if kod == 'ekran':
            yol = ekran_goruntusu(os.path.join(_CFG, 'kernel_ekran.bmp'))
            _ack(log, ses, 'Ekran görüntüsünü aldım: '
                 + os.path.basename(str(yol)))
            return {'tur': 'komut', 'kod': kod, 'dosya': yol}
        if kod == 'klavye':
            m = re.search(r'["""«](.+?)["""»]', t) or \
                re.search(r'klavye(?:ye|de)?\s+(.+?)\s+ya[zn]\b', t)
            metin = (m.group(1) or '').strip() if m else ''
            if metin:
                threading.Thread(target=_yaz_harf, args=(metin,),
                                 daemon=True).start()
                _ack(log, ses, 'Klavyeye yazıyorum: ' + metin[:40])
                return {'tur': 'komut', 'kod': kod, 'metin': metin}
            return None
        if kod == 'fare':
            mm = re.search(r'(?<!\d)(\d{1,5})\s*[,;: ]\s*(\d{1,5})(?!\d)', t)
            try:
                if mm:
                    x, y = int(mm.group(1)), int(mm.group(2))
                else:
                    x = int(ctypes.windll.user32.GetSystemMetrics(0)) // 2
                    y = int(ctypes.windll.user32.GetSystemMetrics(1)) // 2
                ctypes.windll.user32.SetCursorPos(x, y)
                time.sleep(0.08)
                ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0)
                _ack(log, ses, 'Fare (%d,%d) getirilip tıklandı.' % (x, y))
                return {'tur': 'komut', 'kod': kod, 'x': x, 'y': y}
            except Exception:
                return None
        if kod == 'uygulama':
            exe = None
            for p, ad in _UYGULAMALAR:
                if re.search(p, t):
                    exe = ad
                    break
            if exe:
                subprocess.Popen([exe])
                _ack(log, ses, exe + ' açıyorum.')
                return {'tur': 'komut', 'kod': kod, 'exe': exe}
            return None
        if kod == 'web_ara':
            q = ''
            m = re.search(r'["""«](.+?)["""»]', talep)
            if not m:
                m = re.search(r'\b(?:ara|arat|arama yap|search|bak)\b[:\s]+(.+)', t)
            if not m:
                m = re.search(r'([a-z0-9çğıöşü ]{2,60})\s+(?:ara|arat|search)\b', t)
            if m:
                q = m.group(1).strip().strip('"')
            if q:
                sablon = ('https://www.youtube.com/results?search_query='
                          if 'youtube' in t else
                          'https://www.google.com/search?q=')
                webbrowser.open(sablon + urllib.parse.quote(q))
                _ack(log, ses, 'Aramayı yapıyorum: ' + q[:60])
                return {'tur': 'komut', 'kod': kod, 'sorgu': q}
            return None
        if kod == 'gmail':
            adr = re.search(r'[\w\.\+\-]+@[\w\-]+\.[\w\.]+', talep)
            if adr:
                webbrowser.open('https://mail.google.com/mail/?view=cm&fs=1&to='
                                + adr.group(0))
                _ack(log, ses, 'Gmail yazma penceresini açtım: ' + adr.group(0))
                return {'tur': 'komut', 'kod': kod, 'adres': adr.group(0)}
            webbrowser.open('https://mail.google.com/')
            _ack(log, ses, 'Gmail\'i açıyorum; kime ne yazacağımı söyle, tek '
                           'mesaj yazıp gönderirim.')
            return {'tur': 'komut', 'kod': kod}
        if kod == 'ses':
            # Windows master volume: APPCOMMAND (up=10 down=9 mute=8)
            if re.search(r'(kapat|sustur|mute)', t):
                kodu = 8
            elif re.search(r'(azalt|down|kis)', t):
                kodu = 9
            else:
                kodu = 10
            for _ in range(max(1, min(10, sayi))):
                ctypes.windll.user32.SendMessageW(0xFFFF, 0x319, 0,
                                                  kodu * 0x10000)
            _ack(log, ses, 'Ses düzeyi güncellendi.')
            return {'tur': 'komut', 'kod': kod, 'ses_kod': kodu}
        if kod == 'tercume':
            m = re.search(r'["""«](.+?)["""»]', talep) or \
                re.search(r'\b(?:tercume|çevir|translate)\b[:\s]+(.+)', t)
            metin = (m.group(1) or '').strip() if m else ''
            if metin:
                hedef = 'en' if re.search(r'ingilizce', t) else 'tr'
                webbrowser.open('https://translate.google.com/?sl=auto&tl='
                                + hedef + '&text=' + urllib.parse.quote(metin))
                _ack(log, ses, 'Çeviriyi açtım: ' + metin[:40])
                return {'tur': 'komut', 'kod': kod, 'metin': metin}
            return None
        if kod == 'hava':
            yer = ''
            m = re.search(r'\b(?:hava|weather)\b\s*(?:durum[uü]?)?[:\s]+' 
                          r'([a-zA-ZçğıöşüÇĞİÖŞÜ ]{2,30})', t)
            if m:
                yer = m.group(1).strip()
            sablon = 'https://www.google.com/search?q=hava+'
            webbrowser.open(sablon + urllib.parse.quote(yer))
            _ack(log, ses, 'Hava durumunu açıyorum' +
                 ((' ' + yer[:40]) if yer else '') + '.')
            return {'tur': 'komut', 'kod': kod}
        if kod == 'wiki':
            q = re.search(r'["""«](.+?)["""»]', talep)
            metin = q.group(1).strip() if q else ''
            if metin:
                webbrowser.open('https://tr.wikipedia.org/wiki/'
                                + urllib.parse.quote(metin.replace(' ', '_')))
                _ack(log, ses, 'Vikipedi sayfasını açtım: ' + metin[:40])
                return {'tur': 'komut', 'kod': kod}
            return None
        if kod == 'hesapla':
            m = re.fullmatch(r'\s*([\d\s\+\-\*/\(\)\.]{3,60})\s*', t)
            if m:
                try:
                    sonuc = eval(m.group(1), {'__builtins__': {}}, {})
                    _ack(log, ses, 'Sonuç: %s' % sonuc)
                    return {'tur': 'komut', 'kod': kod, 'sonuc': sonuc}
                except Exception:
                    return None
            m = re.search(r'([0-9][\d\s\+\-\*/\(\)\.]{2,58}[0-9\)])', t)
            if m:
                try:
                    sonuc = eval(m.group(1), {'__builtins__': {}}, {})
                    _ack(log, ses, 'Sonuç: %s' % sonuc)
                    return {'tur': 'komut', 'kod': kod, 'sonuc': sonuc}
                except Exception:
                    return None
            return None
        return None
    except Exception:
        return None


# Komut cekirdeginin DEVIR ETMEDIKLERI (ekli akisi olanlar):
_KOMUT_KERNEL_SKIP = {'hatirlatici', 'oyun', 'arastirma', 'ai_sohbet',
                      'bilimsel'}

# Sohbet (diger)
def _sohbet_cevap_kisa(t):
    if re.search(r'merh?ab?a|merhana|meraba|selam|selm|\bsa\b|hey|hi\b|naber|'
                 r'nas[ıi]ls[ıi]n|keyif|iyi misin', t):
        return ('Merhaba! Ben J.A.R.V.I.S. Iyiyim, sen nasilsin? '
                'Sohbet edebiliriz ya da bir is verebilirsin: oyun/Roblox oyunu '
                'yap, hatirlatici, fiyat takibi, harita, 3D model, gorsel/video...')
    if re.search(r'kimsin|ad[ıi]n ne|sen nesin|nesin sen|seni kim yaptı|kim yaptı|yaptın|yapimci|yarat[ıi]c', t):
        return ('Ben J.A.R.V.I.S: Abdulkadir\'in kişisel yapay zekâsıyım. '
                'Bilgisayarında çalışır; sohbet eder, PowerShell kullanır, '
                'oyun/Roblox oyunu brief\'i hazırlar ve AI platformuna gönderir, '
                'ekranını izler, hatırlatır, fiyat takip eder.')
    if re.search(r'ne yapabilirsin|neler yapabilirsin|yetenek|yard[ıi]m|komut|liste|özellik', t):
        return ('Sunları yapabilirim: sohbet; tüm oyunları oynama/AFK; '
                'oyun-roblox-unity-godot isteği yapıp OpenCode/Claude/Freebuff\'a '
                'detaylı brief gönderme; "dur/yeter" ile AI\'ya sahib geldi deyip '
                'bitir/test et demek, "devam et" ile iyileştirme istemek; EXE; '
                'hatırlatıcı; harita; ekran izleme; görsel/video; 3D; '
                'Trendyol-Amazon-Vatan-Idefix-N11 fiyat takibi; PowerShell; '
                'zamanlayıcı, kronometre, alarm, Gmail, bilimsel cevap, ekran/klavye/fare kontrol, araştırma.')
    if re.search(r'te[şs]ekk[üu]r|sa[ğg]?ol|eyvallah', t):
        return 'Rica ederim, her zaman. Başka bir isteğin var mı?'
    if re.search(r'g[üu]nayd[ıi]n', t):
        return 'Gunaydin! Bugun ne yapmak istersin?'
    if re.search(r'iyi gece|iyi geceler', t):
        return 'Iyi geceler. Ben buradayim; bir isin olursa seslen.'
    if re.search(r'\bsaat\b|\btarih\b|bugun gunlerden', t):
        return 'Su an: ' + time.strftime('%d.%m.%Y %H:%M:%S')
    if len(t) <= 12 and t.isalpha():
        return ('Buyur Abi, seni dinliyorum. Ne yapmak istersin? '
                'Ornek: "roblox ve icinde ink game yap", "10 saniye sonra hatirlat", '
                '"ekrani izle", "fiyat takip et".')
    return None

def _sohbet_yedek(talep):
    t = str(talep or '').lower().strip()
    # 1) Komut mu sohbet mu?
    tur, kod = _komut_tipi_bul(t)
    if tur in ('komut', 'iki') and kod:
        cevap = _komut_calistir(kod, t)
        if cevap: return cevap
    # 2) Sadece sohbet kalip
    cevap = _sohbet_cevap_kisa(t)
    if cevap: return cevap
    # 3) Genel yedek
    return ('Seni duydum: "' + str(talep)[:220] + '". Ne yapmamı istiyorsun? '
            'Biraz daha acarsan hemen yapayim. '
            'Ornek: "bana roblox ve icinde ink game yap" ya da "neler yapabilirsin".')


def _sohbet_kaydet(talep, cevap):
    try:
        yol = os.path.join(_CFG, 'sohbet.jsonl')
        with open(yol, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'ts': time.time(), 'kullanici': str(talep)[:2000],
                                'jarvis': str(cevap)[:4000]},
                               ensure_ascii=False) + '\n')
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Yerel AI bekleme ayarlari (qwen3:4b yerel model 90-230 sn surebiliyor)
# ---------------------------------------------------------------------------
# Eski esik 7 sn idi. Yavas model oldugu icin HER mesaj sabit
# 'Seni duydum: ...' fallback cevabina dusuyordu. Artik bekleme suresi
# uzatilir, kullaniciya bekleme durumu yazilir ve arka plandaki AI istegi
# erken iptal edilmez.
SOHBET_AI_ZAMAN = 120.0        # model cagri zaman asimi (sn)
SOHBET_AI_BEKLEME = 300.0      # kullaniciya cevap bekleme (sn)
SOHBET_AI_HIZLI = 4.0          # bu kadar surede gelirse aninda yaz
# Arka plan (gec) thread'i icin bekleme: AI HTTP zaman asiminin uzerine
# marj. Boylece AI istegi bitene kadar cevap KAYBOLMAZ.
SOHBET_AI_GEC_BEKLEME = 330.0


def sohbet_cevap(talep, log=None, ses=None):
    """Yerel AI cevabini bekler; bekleme durumu kullaniciya gosterilir.

    * GUI DONMAZ: bu fonksiyon ayri bir thread icinde calisir
      (calistir() -> threading.Thread(target=sohbet_cevap, ...)).
    * Bekleme esigi 7 sn -> 300 sn. qwen3:4b 90-230 sn surebiliyor; eski
      7 sn esigi yavas modelde HER mesajda sabit 'Seni duydum...' fallback
      cevabina dusmeye yol aciyordu.
    * Kullaniciya ANINDA bekleme durumu yazilir (SYS: satiri).
    * Arka plandaki AI istegi erken iptal EDILMEZ; cevap gelince yazilir.
    """
    global _SOHBET_SAY
    _SOHBET_SAY += 1
    sistem = (
        'Sen J.A.R.V.I.S adli, Turkce konusan, samimi, zeki ve ozguvenli bir '
        'asistansin. Kullanicinin her mesajina yazili ve konusma dilinde cevap '
        'verirsin. Kisa, net, dogal ve yardimci ol. Komut uydurma. Kullanici '
        'bir is isterse yapabilecegini soyle ve nasil isteyecegini kisaca anlat. '
        'Yazim hatalarini (orn. merhana->merhaba) anlayip dogal cevap ver. '
        'Asla sessiz kalma.')
    kutu = {}

    def _sor():
        try:
            kutu['c'] = _ai(str(talep)[:1500], sistem, SOHBET_AI_ZAMAN,
                            700, 0.7)
        except Exception:
            kutu['c'] = ''

    th = threading.Thread(target=_sor, name='sonsuz2-sohbet-ai', daemon=True)
    th.start()

    # 1) BEKLEME DURUMU: kullanici hemen bilgilendirilir; GUI donmaz.
    _yaz(log, 'SYS: SOHBET | yerel model dusunuyor, biraz surecek...')

    # 2) HIZLI KONTROL: kisa surede gelen cevap aninda yazilir.
    th.join(SOHBET_AI_HIZLI)
    cevap = str(kutu.get('c') or '').strip()
    if cevap:
        _yaz(log, 'JARVIS: ' + cevap[:1600])
        _sesle(ses, cevap[:320])
        _sohbet_kaydet(talep, cevap)
        return cevap

    # 3) YEREL MODEL ICIN BEKLE (yavas model normaldir).
    th.join(SOHBET_AI_BEKLEME - SOHBET_AI_HIZLI)
    cevap = str(kutu.get('c') or '').strip()
    if cevap:
        _yaz(log, 'JARVIS: ' + cevap[:1600])
        _sesle(ses, cevap[:320])
        _sohbet_kaydet(talep, cevap)
        return cevap

    # 4) AI hala calisiyorsa istegi IPTAL ETME; arka planda sonucu yaz.
    if th.is_alive():
        def _gec():
            th.join(SOHBET_AI_GEC_BEKLEME)
            c2 = str(kutu.get('c') or '').strip()
            if c2:
                _yaz(log, 'JARVIS: ' + c2[:1600])
                _sesle(ses, c2[:320])
                try:
                    _sohbet_kaydet(talep, c2)
                except Exception:
                    pass
        threading.Thread(target=_gec, name='sonsuz2-sohbet-gec',
                         daemon=True).start()
        return ''

    # 5) Model gercekten bos cevap verdi: sabit 'Seni duydum...' YERINE
    #    anlamli hata mesaji gonderilir.
    cevap = ('Yerel model cevap veremedi. Ollama calisiyor mu? '
             '(localhost:11434 - model qwen3:4b)')
    _yaz(log, 'JARVIS: ' + cevap)
    _sesle(ses, cevap[:320])
    _sohbet_kaydet(talep, cevap)
    return cevap


# ---------------------------------------------------------------------------
# NIYET COZUMLEME
# ---------------------------------------------------------------------------
def _ack(log, ses, metin, kisa=None):
    _yaz(log, 'JARVIS: ' + str(metin)[:800])
    _sesle(ses, (kisa or metin)[:280])


def _zaman_coz(t):
    """('gecikme_sn', 'saat:dd') doner. En az biri None degildir."""
    m = re.search(r'(\d{1,2})\s*[:.]\s*(\d{2})', t)
    saat = m.group(0) if m else ''
    # Saat ifadesini gecikme sanmayalim.
    temiz = re.sub(r'\d{1,2}\s*[:.]\s*\d{2}', ' ', t) if saat else t
    mu = re.search(
        r'(\d+(?:[.,]\d+)?)\s*'
        r'(saniyede|saniyesi|saniye|saniyelik|sn|san|s|'
        r'dakikada|dakikasi|dakika|dak|dk|d|'
        r'saatte|saati|saat|sa)\b', temiz)
    if not mu:
        return None, saat
    try:
        ad = float(mu.group(1).replace(',', '.'))
    except Exception:
        ad = 1.0
    u = mu.group(2).lower()
    if u in ('saatte', 'saati', 'saat', 'sa'):
        ad *= 3600.0
    elif u in ('dakikada', 'dakikasi', 'dakika', 'dak', 'dk', 'd'):
        ad *= 60.0
    return max(1.0, ad), saat


def _hatirlat_metni(t):
    m = re.sub(r'(?i)(hatırlatıcı|hatirlatici|hatırlatma|hatirlatma|'
               r'hatırlat|hatirlat)', ' ', t)
    m = re.sub(r'(?i)\b(ekle|kur|oluştur|olustur|yap|bana|lütfen|'
               r'lutfen|bir|sonra|sonrası|sonrasi|de|da)\b', ' ', m)
    m = re.sub(r'\d{1,2}\s*[:.]\s*\d{2}', ' ', m)
    m = re.sub(r'(\d+(?:[.,]\d+)?)\s*'
               r'(saniyede|saniyesi|saniyelik|saniye|saatte|saati|saat|'
               r'dakikada|dakikasi|dakika|dak|sn|san|sa|dk|s|d)\b',
               ' ', m, flags=re.I)
    m = re.sub(r'\s+', ' ', m).strip(" .,-:;'’")
    return m[:200] or 'Hatirlatma'


def _hatirlat_listele(log):
    with _HATIRLAT_KILIT:
        liste = list(_HATIRLATILAR)
    if not liste:
        _yaz(log, 'SYS: HATIRAT | bekleyen hatirlatma yok.')
        return []
    _yaz(log, 'SYS: HATIRAT | bekleyenler:')
    for h in liste:
        kalan = max(0, int(float(h.get('hedef') or 0) - time.time()))
        _yaz(log, '- %s | %d sn sonra' % (str(h.get('metin'))[:100], kalan))
    return liste


def _hatirlat_sil(talep, log):
    parca = re.sub(r'(?i)\b(hatırlat|hatirlat|hatırlatıcı|hatirlatici|sil|'
                   r'kaldır|kaldir|iptal|listeden)\b', ' ', str(talep))
    parca = re.sub(r'\s+', ' ', parca).strip(' .,-:;').lower()
    global _HATIRLATILAR
    hepsi = _hepsi_mi(parca)
    with _HATIRLAT_KILIT:
        once = len(_HATIRLATILAR)
        if hepsi:
            _HATIRLATILAR[:] = []
        else:
            _HATIRLATILAR[:] = [h for h in _HATIRLATILAR
                                if parca not in str(h.get('metin') or '').lower()]
        sonra = len(_HATIRLATILAR)
    _hatirlat_kaydet()
    _yaz(log, 'SYS: HATIRAT | %d hatirlatma silindi.' % (once - sonra))
    return once - sonra


def _fiyat_niyeti(t):
    if 'fiyat' not in t and 'fiyatlar' not in t:
        return ''
    if re.search(r'listele|liste|göster|goster|durum|ne kadar', t):
        return 'listele'
    if re.search(r'sil|kaldır|kaldir|çıkar|cikar|iptal', t):
        return 'sil'
    if re.search(r'takip|takibe|izle|ucuz|pahal|düş|dus|çık|cik|bildir|'
                 r'haber|alarm|ekle', t):
        return 'ekle'
    return ''


# ---------------------------------------------------------------------------
# ANA GIRIS
# ---------------------------------------------------------------------------
_S2_BASLADI = False


def _tembel_baslat(log=None, ses=None):
    global _S2_BASLADI, _DEMIR_LOG, _DEMIR_SES
    _DEMIR_LOG = log
    _DEMIR_SES = ses
    if _S2_BASLADI:
        return
    _S2_BASLADI = True
    try:
        baslat(log, ses)
    except Exception as e:
        _hata(log, 'SONSUZ v2 baslatma hatasi: ' + repr(e)[:200])


def _gorev_mi(t):
    """Sohbet degil de yerine getirilmesi gereken bir is mi?"""
    t = str(t or '').lower()
    if '?' in t:
        return False
    if re.match(r'^(ne|neden|nasıl|nasil|kim|nerede|hangi|kaç|kac|mi|mı|'
                r'musun|müsün|misin|mısın)\b', t):
        return False
    if re.search(r'(proje|site|uygulama|program|exe|dosya|kod|tasarım|'
                 r'tasarim|plan).{0,50}\b(yap|yaptır|yaptir|oluştur|olustur|'
                 r'üret|uret|hazırla|hazirla)\b', t):
        return True
    if re.search(r'\b(powershell|dosya|klasör|klasor|kod|proje|uygulama|'
                 r'program|site|web|exe|indir|kur|düzelt|duzelt|araştır|'
                 r'arastir|hesapla|gönder|gonder|dönüştür|donustur|temizle|'
                 r'taşı|tasi|kopyala|oluştur|olustur|üret|uret|hazırla|'
                 r'hazirla|planla|geliştir|gelistir|güncelle|guncelle|'
                 r'tasarım|tasarim)\b', t):
        return True
    return False


def rapor(log=None):
    try:
        parcalar = []
        if _ju is not None:
            parcalar.append('komut=%d' % len(getattr(_ju, '_KOMUTLAR', [])))
            parcalar.append('degisim=%d' % len(getattr(_ju, '_DEGISIMLER', [])))
            parcalar.append('exe=%d' % len(getattr(_ju, '_EXELER', [])))
            parcalar.append('hata=%d' % len(getattr(_ju, '_HATALAR', [])))
        parcalar.append('sohbet=%d' % _SOHBET_SAY)
        parcalar.append('hatirlat=%d' % len(_HATIRLATILAR))
        parcalar.append('ekran=%s' % ('ACIK' if _EKRAN_IZLE else 'KAPALI'))
        parcalar.append('afk=%s' % ('ACIK' if _AFK.get('aktif') else 'KAPALI'))
        _yaz(log, 'SYS: DURUM | ' + ' | '.join(parcalar))
        veri = _fiyat_veri()
        _yaz(log, 'SYS: DURUM | fiyat urunu=%d' % len(veri.get('urunler') or []))
    except Exception as e:
        _hata(log, 'Rapor hatasi: ' + repr(e)[:160])
    return True


def calistir(talep, log=None, ses=None, ekran_al=True):
    """SONSUZ v2 tek giris noktasi. Asla sessiz kalmaz."""
    global _S2_BASLADI
    try:
        talep = str(talep or '').strip()
        t = talep.lower()
        _tembel_baslat(log, ses)
        # z42: yetenek raporu (Saat 4) — komut uzay büyümesi YOK.
        if 'yetenek raporu' in t:
            try:
                import jarvis_sonsuz_v3_yetenek_raporu as _r42
                rapor = _r42.uret()
                _ack(log, ses, rapor['ekran_metni'][:400])
                return rapor
            except Exception as _e42:
                _ack(log, ses, 'Yetenek raporu uretilemedi: ' + repr(_e42)[:120])
                return {'durum': 'RAPOR_HATA', 'hata': repr(_e42)[:120]}
        if _ju is not None:
            _ju._CALISMA = getattr(_ju, '_KOK', _KOK)
        if not talep:
            _ack(log, ses, 'Seni dinliyorum; ne yapmamı istersin?')
            return {'durum': 'BOS'}
        # 1) Durdurma / sahib geldi handoff
        if re.fullmatch(r'(dur|durdur|durabilirsin|yeter|yeterli|iptal|stop|'
                        r'kes|sus|tamam dur|bekle|vazgeç|vazgec)[.! ]*', t):
            gplat = _platform_durum()
            if gplat.get('aktif') or gplat.get('hwnd'):
                # Sahib geldi: AI'ya hemen bitir/test et/raporla de.
                oyun_durdur(log)
                try:
                    if _ju is not None:
                        _ju._afk_durdur(log=None)
                except Exception:
                    pass
                return platform_handoff(log, ses, 'kullanici_durdurma')
            oyun_durdur(log)
            afk_durdur(log)
            ekran_izle_durdur(log)
            try:
                if _ju is not None:
                    _ju.gorev_durdur()
                    _ju._ekran_izle_durdur()
                    _ju._afk_durdur(log=None)
            except Exception:
                pass
            _ack(log, ses, 'Durdurdum. Tum gorevler, oyun, AFK ve ekran '
                           'izleme kapatildi.')
            return {'durum': 'IPTAL'}
        # 1b) Yapay zekaya devam/iyilestirme
        if re.search(r'(?i)\b(devam et|devam etsin|devam|bitirdiysen devam|'
                     r'iyileştir|iyilestir|daha iyi yap|grafikleri artır|'
                     r'ozellik ekle)\b', t) and _platform_durum().get('hwnd'):
            return platform_devam(log, ses)
        # 2) SONSUZ ac/kapat
        if re.search(r'(?i)\bsonsuz(u| modu| mod)?\s*(kapat|kapa|durdur|off)\b', t):
            if _ju is not None:
                _ju.sinirsiz_kapat(log=log, ses=ses)
            afk_durdur(log)
            ekran_izle_durdur(log)
            _ack(log, ses, 'SONSUZ mod kapandi; normal sohbet moduna donuldu.')
            return {'durum': 'KAPALI'}
        if re.search(r'(?i)\bsonsuz(u| modu| mod)?\s*(ac|aç|baslat|başlat|on)\b', t):
            if _ju is not None:
                _ju.sinirsiz_ac(log=log, ses=ses)
                try:
                    _ju._afk_durdur(log=None)
                except Exception:
                    pass
            afk_baslat(log, ses)
            _ack(log, ses, 'SONSUZ mod acildi. Her seyi yapabilirim: '
                           'PowerShell, dosya, EXE, oyun, ekran, fiyat, 3D, medya.')
            return {'durum': 'ACIK'}
        # 3) Guvenlik
        try:
            if _ju is not None and _ju._tehlikeli(talep):
                _hata(log, 'GUVENLI KOMUT REDDEDILI: ' + talep[:300])
                _yaz(log, 'ERR: PowerShell IPTAL - REDDEDILDI (komut, guvenlik): '
                          + talep[:300])
                _sesle(ses, 'Bu komut guvenlik nedeniyle reddedildi.')
                return {'durum': 'RED', 'talep': talep}
        except Exception:
            pass
        # 3b) JARVIS bilgisayari: gercek muzik eylemi + adim adim animasyon
        try:
            import jarvis_bilgisayar as _jb
            if _jb.muzik_istegi_mi(t):
                _ack(log, ses, 'Müziği açıyorum; JARVIS bilgisayarında adım '
                               'adım göstereceğim.')
                threading.Thread(target=_jb.muzik_ac,
                                 args=(talep, log, ses, True, True),
                                 name='sonsuz2-muzik', daemon=True).start()
                return {'durum': 'MUZIK_BASLADI'}
            if re.search(r'(?i)(bilgisayar\w*\s*g[oö]ster|'
                         r'jarvis\s+bilgisayar|animasyonu\s+g[oö]ster)', t):
                r = _jb.demo(log=log, ses=ses, konus=False)
                _sesle(ses, r.get('mesaj') or 'JARVIS bilgisayarı gösteriliyor.')
                return r
        except Exception:
            pass
        # 3c) Ozellik merkezi: 15 merkez, 10.000+ gercek ozellik
        try:
            import jarvis_ozellik_merkezi as _om
            if _om.komut_mu(t):
                def _om_calistir():
                    try:
                        r = _om.komut(talep, log=log, ses=ses)
                        if r.get('konus') is False:
                            return
                        oz = r.get('ozellik')
                        if isinstance(oz, dict) and oz.get('konus') is False:
                            return
                        _sesle(ses, r.get('mesaj') or r.get('metin') or '')
                    except Exception as e:
                        _hata(log, 'ozellik merkezi: ' + repr(e)[:300])
                        _sesle(ses, 'Ozellik merkezi hata verdi.')
                threading.Thread(target=_om_calistir,
                                 name='sonsuz2-ozellik', daemon=True).start()
                return {'durum': 'OZELLIK_BASLADI'}
        except Exception:
            pass
        # 3d) KOMUT CEKIRDEGI: komut mu / sohbet mi / ikisi mi?
        #     Komutsa GERCEK eylem; "ikisi" ise eylem + kisa sohbet cevabi.
        try:
            tur, kod = _komut_tipi_bul(t)
        except Exception:
            tur, kod = (None, None)
        if tur or kod:
            _yaz(log, 'SYS: NIYET | ' + (tur or '-') +
                 ((' | kod=' + str(kod)) if kod else ''))
        if tur == 'komut' and kod and kod in _KOMUT_KERNEL_SKIP:
            pass  # alt bolumlerde daha iyi gercek akisla calisir (hatirlat...)
        elif tur == 'sohbet':
            # Bilinen sohbet kalibi (selam, kimim, yetenek, saat...) aninda
            kisa = _sohbet_cevap_kisa(t)
            if kisa and len(t) <= 48:
                _yaz(log, 'JARVIS: ' + kisa[:600])
                _sesle(ses, kisa[:320])
                try:
                    _sohbet_kaydet(talep, kisa)
                except Exception:
                    pass
                return {'durum': 'SOHBET_KISA', 'tur': 'sohbet'}
        elif tur in ('komut', 'iki') and kod:
            r = _komut_uygula(kod, talep, t, log, ses)
            if r:
                if tur == 'iki':
                    kisa = _sohbet_cevap_kisa(t)
                    if kisa:
                        _sesle(ses, kisa[:280])
                        _yaz(log, 'JARVIS: ' + kisa[:300])
                return dict([('durum', 'KOMUT'), ('tur', tur), ('kod', kod)]
                            + [p for p in r.items() if p[0] != 'tur'])
        # 4) Hatirlatici
        if re.search(r'(?i)(hatırlat|hatirlat|hatırlatıcı|hatirlatici)', t):
            if re.search(r'(?i)(listele|liste|göster|goster|bekleyen)', t):
                _hatirlat_listele(log)
                _sesle(ses, 'Bekleyen hatirlatmalari listeledim.')
                return {'durum': 'HATIRLAT_LISTE'}
            if re.search(r'(?i)(sil|kaldır|kaldir|iptal)', t):
                n = _hatirlat_sil(talep, log)
                _sesle(ses, '%d hatirlatma silindi.' % n)
                return {'durum': 'HATIRLAT_SIL'}
            ad, saat = _zaman_coz(t)
            metin = _hatirlat_metni(t)
            if saat:
                hedef = _hatirlat_ekle_saat(metin, saat, log, ses)
                if hedef:
                    _ack(log, ses, 'Hatirlatma kuruldu: %s | saat %s'
                         % (metin[:120], saat))
                    return {'durum': 'HATIRLAT', 'saat': saat}
            if ad is None:
                ad = 60.0
            _hatirlat_ekle(metin, ad, log, ses)
            _ack(log, ses, 'Hatirlatma kuruldu: %s | %.0f sn sonra'
                 % (metin[:120], ad))
            return {'durum': 'HATIRLAT', 'saniye': ad}
        # 5) Ekran izleme
        if 'ekran' in t and re.search(r'(?i)(her saniye|saniyede|izle|izleme|'
                                      r'watch|sürekli|surekli)', t):
            if re.search(r'(?i)(durdur|kapat|kapa|bırak|birak|off)', t):
                ekran_izle_durdur(log)
                _sesle(ses, 'Ekran izleme durduruldu.')
                return {'durum': 'EKRAN_DUR'}
            ekran_izle_baslat(log, ses)
            _ack(log, ses, 'Ekran izleme acildi; her saniye kontrol ediyorum. '
                           'Tek dosyaya yaziyorum, disk sisirmiyorum.')
            return {'durum': 'EKRAN'}
        if 'ekran' in t and re.search(r'(?i)(kontrol|bak|analiz|incele|gör|gor)', t):
            yol = ekran_goruntusu(os.path.join(_CFG, 'ekran_analiz.bmp'))
            cevap = _vizyon(yol, 'Ekranda ne var? Kisa, maddeler halinde '
                                 'Turkce anlat.', zaman=50)
            if cevap:
                _yaz(log, 'SYS: EKRAN | ' + cevap[:900].replace('\n', ' | '))
                _sesle(ses, cevap[:250])
            else:
                _yaz(log, 'SYS: EKRAN | goruntu alindi: ' + str(yol))
                _sesle(ses, 'Ekran goruntusunu aldim.')
            return {'durum': 'EKRAN_ANALIZ', 'dosya': yol}
        # 6) AFK / ban
        if re.search(r'(?i)\bafk\b', t):
            if re.search(r'(?i)(kapat|kapa|durdur|off|istemiyorum)', t):
                afk_durdur(log)
                _ack(log, ses, 'AFK korumasi kapatildi.')
                return {'durum': 'AFK_KAPALI'}
            afk_baslat(log, ses)
            _ack(log, ses, 'AFK korumasi acildi: her saniye oyunu kontrol '
                           'edecegim; hareketsizlikte otomatik hareket.')
            return {'durum': 'AFK'}
        if re.search(r'(?i)ban(?:lanma)?\s*(?:risk|yeme|korum)|anti.?ban|ban\s*koruma', t):
            afk_baslat(log, ses)
            _ack(log, ses, 'Ban koruma acildi: insan benzeri hiz, rastgele '
                           'bekleme, ayni tusu tekrarlamama, molalar ve AFK.')
            return {'durum': 'BAN_KORUMA'}
        # 7) Fiyat takibi
        niyet = _fiyat_niyeti(t)
        if niyet == 'listele':
            fiyat_listele(log)
            _sesle(ses, 'Fiyat takip listesini yazdim.')
            return {'durum': 'FIYAT_LISTE'}
        if niyet == 'sil':
            n = fiyat_sil(talep, log)
            _sesle(ses, '%d urun fiyat takibinden kaldirildi.' % n)
            return {'durum': 'FIYAT_SIL'}
        if niyet == 'ekle':
            r = _fiyat_ekle(talep, log, ses)
            _ack(log, ses, 'Fiyat takibine aldim: %s | platformlar: %s'
                 % (r.get('urun', '')[:100], ', '.join(r.get('platformlar') or [])))
            return r
        # 8) Oyun yapma (once; "harita oyunu", "roblox ... game yap" da sayilir)
        oyun_yap_niyeti = (
            re.search(r'(?i)\b(yap|yaptır|yaptir|üret|uret|oluştur|olustur|'
                      r'kodla|geliştir|gelistir|hazırla|hazirla|yaz)\b', t) and
            re.search(r'(?i)\b(oyun|game|roblox|unity|godot|harita oyunu|'
                      r'macera|sim[uü]lasyon|fps|rpg|tycoon|obby|simulator)\b', t))
        if oyun_yap_niyeti and not re.search(r'(?i)\b(oyna|oynat|benim yerime|yerime)\b', t):
            _ack(log, ses, 'Anladim: oyunu arastirip en mantikli platforma '
                           'brief gonderecegim ve yerelde EXE uretecegim.')
            threading.Thread(target=oyun_yap, args=(talep, log, ses),
                             name='sonsuz2-oyun-yap', daemon=True).start()
            return {'durum': 'OYUN_YAP_BASLADI'}
        # 9) Oyun oynama
        if re.search(r'(?i)\b(oyun|oyna|oynat)\b', t) and \
                re.search(r'(?i)\b(oyna|oynat|afk|benim yerime|yerime)\b', t):
            _ack(log, ses, 'Oyunu aciyorum; ekran gorerek insan gibi '
                           'oynayacagim. Ban riskine karsi yavas ve molali.')
            threading.Thread(target=oyun_oyna, args=(talep, log, ses),
                             name='sonsuz2-oyun-oyna', daemon=True).start()
            return {'durum': 'OYUN_BASLADI'}
        # 10) Medya
        if re.search(r'(?i)(görsel|gorsel|resim|foto|video|film|animasyon)', t) \
                and re.search(r'(?i)(üret|uret|yap|oluştur|olustur|çek|cek|'
                              r'hazırla|hazirla)', t):
            _ack(log, ses, 'Medya uretimi basliyor; hazir olunca uzerinde '
                           'KOPYALA dugmesi olan ekranda gosterecegim.')
            threading.Thread(target=medya_uret, args=(talep, log, ses),
                             name='sonsuz2-medya', daemon=True).start()
            return {'durum': 'MEDYA_BASLADI'}
        # 11) 3D
        if re.search(r'(?i)(\b3d\b|üç boyut|uc boyut|sketchfab|3dmodels)', t):
            _ack(log, ses, '3D model aramasi basliyor: Sketchfab ve '
                           '3dmodels.org/tr uzerinden ucretsizleri analiz edecegim.')
            threading.Thread(target=uc_boyut, args=(talep, log, ses),
                             name='sonsuz2-3d', daemon=True).start()
            return {'durum': '3D_BASLADI'}
        # 12) Harita / konum
        if re.search(r'(?i)(harita|konum|maps|yol tarifi|gps|adres)', t):
            r = harita_ac(talep, log, ses)
            return r
        # 13) Platform acma (oyun disi)
        if re.search(r'(?i)(opencode|open code|claude|freebuff)', t) and \
                re.search(r'(?i)(aç|ac|başlat|baslat|open)', t):
            aday = _platform_adaylari()
            istenen = ''
            for k in ('opencode', 'claude', 'freebuff'):
                if k in t:
                    istenen = k
                    break
            sec = None
            for a in aday:
                if istenen and istenen in str(a.get('ad') or '').lower():
                    sec = a
                    break
            if sec is None and aday:
                sec = aday[0]
            hwnd = _platform_ac(sec, log)
            if hwnd:
                _ack(log, ses, '%s acildi.' % (sec.get('ad') if sec else 'Platform'))
                return {'durum': 'PLATFORM_AC', 'hwnd': hwnd}
            _ack(log, ses, 'Platformu acamadim; PowerShell ile deneyecegim.')
            return {'durum': 'PLATFORM_HATA'}
        # 14) Kendini gelistirme
        if re.search(r'(?i)(kendini geliştir|kendini gelistir|yeni yetenek|'
                     r'sınırını kaldır|sinirini kaldir|eklenti ekle|'
                     r'kendini güncelle|kendini guncelle)', t):
            _ack(log, ses, 'Kendimi gelistirme moduna giriyorum: yeni yetenek '
                           'yazacagim.')
            threading.Thread(target=kendini_gelistir, args=(talep, log, ses),
                             name='sonsuz2-gelisim', daemon=True).start()
            return {'durum': 'GELISIM_BASLADI'}
        # 15) PowerShell ozgurlugu
        if re.match(r'(?i)^\s*(powershell|ps\s*[:>]|komut\s*(çalıştır|calistir)|'
                    r'komutu\s*(çalıştır|calistir)|shell)\b', talep):
            komut = re.sub(r'(?i)^\s*(powershell|ps\s*[:>]|komut\s*'
                           r'(çalıştır|calistir)|komutu\s*(çalıştır|calistir)|'
                           r'shell)\s*', '', talep).strip()
            if not komut:
                _ack(log, ses, 'PowerShell komutunu yazmadin.')
                return {'durum': 'PS_BOS'}
            r = _ps_calistir(komut, log)
            if r.get('red'):
                _ack(log, ses, 'Komut guvenlik nedeniyle reddedildi.')
                return {'durum': 'RED'}
            cikti = str(r.get('cikti') or '')[:600]
            _ack(log, ses, 'PowerShell bitti (kod %s). %s'
                 % (r.get('kod'), cikti[:220]))
            return {'durum': 'PS', 'ok': bool(r.get('ok')), 'cikti': cikti}
        # 16) Durum raporu
        if re.search(r'(?i)^(ne yaptın|ne yaptin|rapor|durum|özet|ozet)\b', t):
            rapor(log)
            _sesle(ses, 'Durum raporunu yazdim.')
            return {'durum': 'RAPOR'}
        # 17) Genel gorev: eski ust duzey ajan (PowerShell + dosya + EXE)
        if _gorev_mi(t) and _ju is not None:
            _ack(log, ses, 'Anladim; gorevi ust duzey ajana aktardim. '
                           'Sonucu ve yaptiklarimi yazacagim.')
            try:
                th = threading.Thread(
                    target=_ju.sinirsiz_calistir,
                    args=(talep, log, ses, ekran_al, False),
                    name='sonsuz2-usta-gorev', daemon=True)
                th.start()
                return {'durum': 'GOREV'}
            except Exception as e:
                _hata(log, 'Gorev ajana aktarilamadi: ' + repr(e)[:200])
        # 18) Sohbet (varsayilan)
        threading.Thread(target=sohbet_cevap, args=(talep, log, ses),
                         name='sonsuz2-sohbet', daemon=True).start()
        return {'durum': 'SOHBET'}
    except Exception as e:
        _hata(log, 'SONSUZ v2 hata: ' + repr(e)[:300])
        try:
            gelisim_kaydet('calistir hata: ' + repr(e)[:300], 'hata')
        except Exception:
            pass
        try:
            _ack(log, ses, 'Bir hata oldu ama seni duydum. Sorunu kaydettim: '
                           + repr(e)[:180])
        except Exception:
            pass
        return {'durum': 'HATA', 'hata': repr(e)[:300]}


# ---------------------------------------------------------------------------
# Giris noktasi: komut satir (CLI) calistirma
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print('J.A.R.V.I.S SONSUZ v2 - Komut Modu')
    print('Cikmak icin: cik, kapat, quit, exit')
    print('-' * 50)
    while True:
        try:
            talep = input('\nSiz: ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nGorusuruz.')
            break
        if not talep:
            continue
        if talep.lower() in ('cik', 'kapat', 'quit', 'exit', 'q'):
            print('Gorusuruz.')
            break
        # Synchronous text response for CLI
        try:
            cevap = _sohbet_yedek(talep)
            if cevap:
                print('JARVIS:', cevap)
        except Exception as e:
            print('Hata:', repr(e))


# __SON__