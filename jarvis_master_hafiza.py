# -*- coding: utf-8 -*-
"""
JARVIS MASTER V1 — Gelişmiş Hafıza ve Görev Yönetimi (Aşama 8).

SQLite tabanlı kalıcı hafıza sistemi:
  * Kullanıcı tercihleri
  * Proje hafızası (INK GAME, JARVIS vb.)
  * Görev geçmişi (kimlik, istek, zaman, araçlar, model, durum, sonuc, hata)
  * Görev adımları
  * Genel hafıza kayıtları (anahtar-değer, kategori, kaynak)
  * Kullanıcı onayları (kararlar)

Güvenlik:
  * API anahtarı, şifre, hassas bilgi kaydedilmez.
  * Kullanıcı istediğinde kayıtlar silinir.
  * Her kaydın kaynağı ve zamanı tutulur.
  * Hafıza içeriği çalıştırılabilir talimat olarak değerlendirilmez.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

sys_path = os.path.dirname(os.path.abspath(__file__))
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)

_DB_PATH = Path(__file__).resolve().parent / "memory" / "master" / "jarvis_hafiza.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_LOCK = threading.RLock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_db() -> None:
    with _LOCK:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS kullanici_tercihleri (
                    anahtar TEXT PRIMARY KEY,
                    deger TEXT,
                    kategori TEXT,
                    guncelleme_zamani REAL
                );

                CREATE TABLE IF NOT EXISTS projeler (
                    proje_adi TEXT PRIMARY KEY,
                    aciklama TEXT,
                    durum TEXT,
                    son_calisilan_sahne TEXT,
                    son_degistirilen_dosyalar TEXT,
                    bilinen_hatalar TEXT,
                    tamamlanan_ozellikler TEXT,
                    sonraki_adimlar TEXT,
                    olusturma_zamani REAL,
                    guncelleme_zamani REAL
                );

                CREATE TABLE IF NOT EXISTS gorevler (
                    gorev_id TEXT PRIMARY KEY,
                    istek TEXT,
                    baslangic_zamani REAL,
                    bitis_zamani REAL,
                    kullanilan_araclar TEXT,
                    kullanilan_model TEXT,
                    durum TEXT,
                    sonuc TEXT,
                    hata_bilgisi TEXT,
                    devam_etilebilir_asama TEXT,
                    proje_adi TEXT,
                    kaynak TEXT
                );

                CREATE TABLE IF NOT EXISTS gorev_adimlari (
                    adim_id TEXT PRIMARY KEY,
                    gorev_id TEXT,
                    sira INTEGER,
                    arac_adi TEXT,
                    args TEXT,
                    durum TEXT,
                    sonuc TEXT,
                    hata TEXT,
                    zaman REAL,
                    FOREIGN KEY(gorev_id) REFERENCES gorevler(gorev_id)
                );

                CREATE TABLE IF NOT EXISTS hafiza_kayitlari (
                    kayit_id TEXT PRIMARY KEY,
                    anahtar TEXT,
                    deger TEXT,
                    kategori TEXT,
                    zaman REAL,
                    kaynak TEXT
                );

                CREATE TABLE IF NOT EXISTS kararlar (
                    karar_id TEXT PRIMARY KEY,
                    islem TEXT,
                    onay_verildi INTEGER,
                    zaman REAL,
                    aciklama TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_gorevler_durum ON gorevler(durum);
                CREATE INDEX IF NOT EXISTS idx_gorevler_proje ON gorevler(proje_adi);
                CREATE INDEX IF NOT EXISTS idx_gorevler_zaman ON gorevler(baslangic_zamani);
                CREATE INDEX IF NOT EXISTS idx_hafiza_anahtar ON hafiza_kayitlari(anahtar);
                CREATE INDEX IF NOT EXISTS idx_hafiza_kategori ON hafiza_kayitlari(kategori);
                """
            )
            conn.commit()
        finally:
            conn.close()


# Veritabanını başlat
_init_db()


class HafizaYoneticisi:
    """Merkezi hafıza ve görev yöneticisi. Tek örne olarak kullanılır."""

    def __init__(self):
        self._db_path = _DB_PATH

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------
    @staticmethod
    def _filtrele_hassasi(metin: str) -> str:
        """API anahtarı, şifre gibi hassas bilgileri maskele."""
        import re
        s = str(metin)
        # Gemini / API anahtarı desenleri (30+ karakter)
        s = re.sub(r'AIza[0-9A-Za-z\-_]{30,}', '[API_ANAHTARI_GIZLENDI]', s)
        s = re.sub(r'sk-[0-9A-Za-z\-_]{20,}', '[API_ANAHTARI_GIZLENDI]', s)
        # Sifre / token / secret / gizli anahtar desenleri
        for anahtar in ('sifre', 'password', 'token', 'secret', 'api_key', 'apikey'):
            s = re.sub(
                anahtar + r'[^\n]{0,100}',
                anahtar + '=[GIZLENDI]',
                s,
                flags=re.IGNORECASE,
            )
        return s

    # ------------------------------------------------------------------
    # Kullanıcı tercihleri
    # ------------------------------------------------------------------
    def tercih_kaydet(self, anahtar: str, deger: Any, kategori: str = "genel") -> bool:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    conn.execute(
                        """INSERT INTO kullanici_tercihleri
                           (anahtar, deger, kategori, guncelleme_zamani)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(anahtar) DO UPDATE SET
                           deger=excluded.deger,
                           kategori=excluded.kategori,
                           guncelleme_zamani=excluded.guncelleme_zamani""",
                        (anahtar, json.dumps(deger, ensure_ascii=False),
                         kategori, time.time()),
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception:
            return False

    def tercih_oku(self, anahtar: str, varsayilan: Any = None) -> Any:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    cur = conn.execute(
                        "SELECT deger FROM kullanici_tercihleri WHERE anahtar=?",
                        (anahtar,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        return varsayilan
                    return json.loads(row["deger"])
                finally:
                    conn.close()
        except Exception:
            return varsayilan

    # ------------------------------------------------------------------
    # Proje hafızası
    # ------------------------------------------------------------------
    def proje_kaydet(
        self,
        proje_adi: str,
        aciklama: Optional[str] = None,
        durum: Optional[str] = None,
        son_calisilan_sahne: Optional[str] = None,
        son_degistirilen_dosyalar: Optional[List[str]] = None,
        bilinen_hatalar: Optional[List[str]] = None,
        tamamlanan_ozellikler: Optional[List[str]] = None,
        sonraki_adimlar: Optional[List[str]] = None,
    ) -> bool:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    simdi = time.time()
                    mevcut = conn.execute(
                        "SELECT olusturma_zamani FROM projeler WHERE proje_adi=?",
                        (proje_adi,),
                    ).fetchone()
                    ozaman = mevcut["olusturma_zamani"] if mevcut else simdi
                    conn.execute(
                        """INSERT INTO projeler
                           (proje_adi, aciklama, durum, son_calisilan_sahne,
                            son_degistirilen_dosyalar, bilinen_hatalar,
                            tamamlanan_ozellikler, sonraki_adimlar,
                            olusturma_zamani, guncelleme_zamani)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(proje_adi) DO UPDATE SET
                           aciklama=excluded.aciklama,
                           durum=excluded.durum,
                           son_calisilan_sahne=excluded.son_calisilan_sahne,
                           son_degistirilen_dosyalar=excluded.son_degistirilen_dosyalar,
                           bilinen_hatalar=excluded.bilinen_hatalar,
                           tamamlanan_ozellikler=excluded.tamamlanan_ozellikler,
                           sonraki_adimlar=excluded.sonraki_adimlar,
                           guncelleme_zamani=excluded.guncelleme_zamani""",
                        (
                            proje_adi,
                            aciklama,
                            durum,
                            son_calisilan_sahne,
                            json.dumps(son_degistirilen_dosyalar or [], ensure_ascii=False),
                            json.dumps(bilinen_hatalar or [], ensure_ascii=False),
                            json.dumps(tamamlanan_ozellikler or [], ensure_ascii=False),
                            json.dumps(sonraki_adimlar or [], ensure_ascii=False),
                            ozaman,
                            simdi,
                        ),
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception:
            return False

    def proje_oku(self, proje_adi: str) -> Optional[Dict[str, Any]]:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    cur = conn.execute(
                        "SELECT * FROM projeler WHERE proje_adi=?", (proje_adi,)
                    )
                    row = cur.fetchone()
                    if row is None:
                        return None
                    return {
                        "proje_adi": row["proje_adi"],
                        "aciklama": row["aciklama"],
                        "durum": row["durum"],
                        "son_calisilan_sahne": row["son_calisilan_sahne"],
                        "son_degistirilen_dosyalar": json.loads(row["son_degistirilen_dosyalar"] or "[]"),
                        "bilinen_hatalar": json.loads(row["bilinen_hatalar"] or "[]"),
                        "tamamlanan_ozellikler": json.loads(row["tamamlanan_ozellikler"] or "[]"),
                        "sonraki_adimlar": json.loads(row["sonraki_adimlar"] or "[]"),
                        "olusturma_zamani": row["olusturma_zamani"],
                        "guncelleme_zamani": row["guncelleme_zamani"],
                    }
                finally:
                    conn.close()
        except Exception:
            return None

    def projeleri_listele(self) -> List[Dict[str, Any]]:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    cur = conn.execute(
                        "SELECT * FROM projeler ORDER BY guncelleme_zamani DESC"
                    )
                    sonuc = []
                    for row in cur.fetchall():
                        sonuc.append({
                            "proje_adi": row["proje_adi"],
                            "aciklama": row["aciklama"],
                            "durum": row["durum"],
                            "son_calisilan_sahne": row["son_calisilan_sahne"],
                            "son_degistirilen_dosyalar": json.loads(row["son_degistirilen_dosyalar"] or "[]"),
                            "bilinen_hatalar": json.loads(row["bilinen_hatalar"] or "[]"),
                            "tamamlanan_ozellikler": json.loads(row["tamamlanan_ozellikler"] or "[]"),
                            "sonraki_adimlar": json.loads(row["sonraki_adimlar"] or "[]"),
                            "olusturma_zamani": row["olusturma_zamani"],
                            "guncelleme_zamani": row["guncelleme_zamani"],
                        })
                    return sonuc
                finally:
                    conn.close()
        except Exception:
            return []

    def proje_sil(self, proje_adi: str) -> bool:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    conn.execute("DELETE FROM projeler WHERE proje_adi=?", (proje_adi,))
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Görev hafızası
    # ------------------------------------------------------------------
    def gorev_baslat(
        self,
        istek: str,
        proje_adi: Optional[str] = None,
        kaynak: Optional[str] = None,
    ) -> str:
        """Yeni görev kaydı açar ve ID döndürür."""
        gid = "g_" + uuid.uuid4().hex[:12]
        try:
            with _LOCK:
                conn = _connect()
                try:
                    conn.execute(
                        """INSERT INTO gorevler
                           (gorev_id, istek, baslangic_zamani, bitis_zamani,
                            kullanilan_araclar, kullanilan_model, durum,
                            sonuc, hata_bilgisi, devam_etilebilir_asama,
                            proje_adi, kaynak)
                           VALUES (?, ?, ?, NULL, ?, ?, 'calisiyor', NULL, NULL,
                                   ?, ?, ?)""",
                        (
                            gid,
                            istek,
                            time.time(),
                            json.dumps([], ensure_ascii=False),
                            None,
                            None,
                            proje_adi,
                            kaynak,
                        ),
                    )
                    conn.commit()
                    return gid
                finally:
                    conn.close()
        except Exception:
            return gid

    def gorev_bitir(
        self,
        gorev_id: str,
        durum: str,
        sonuc: Optional[str] = None,
        hata_bilgisi: Optional[str] = None,
        kullanilan_araclar: Optional[List[str]] = None,
        kullanilan_model: Optional[str] = None,
        devam_etilebilir_asama: Optional[str] = None,
    ) -> bool:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    conn.execute(
                        """UPDATE gorevler
                           SET bitis_zamani=?, durum=?, sonuc=?,
                               hata_bilgisi=?, kullanilan_araclar=?,
                               kullanilan_model=?, devam_etilebilir_asama=?
                           WHERE gorev_id=?""",
                        (
                            time.time(),
                            durum,
                            sonuc,
                            hata_bilgisi,
                            json.dumps(kullanilan_araclar or [], ensure_ascii=False),
                            kullanilan_model,
                            devam_etilebilir_asama,
                            gorev_id,
                        ),
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception:
            return False

    def gorev_adim_ekle(
        self,
        gorev_id: str,
        sira: int,
        arac_adi: str,
        args: Dict[str, Any],
        durum: str,
        sonuc: Optional[str] = None,
        hata: Optional[str] = None,
    ) -> bool:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    conn.execute(
                        """INSERT INTO gorev_adimlari
                           (adim_id, gorev_id, sira, arac_adi, args, durum,
                            sonuc, hata, zaman)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            "a_" + uuid.uuid4().hex[:10],
                            gorev_id,
                            sira,
                            arac_adi,
                            json.dumps(args, ensure_ascii=False),
                            durum,
                            sonuc,
                            hata,
                            time.time(),
                        ),
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception:
            return False

    def gorevleri_listele(
        self,
        durum: Optional[str] = None,
        proje_adi: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    sql = "SELECT * FROM gorevler WHERE 1=1"
                    params: List[Any] = []
                    if durum:
                        sql += " AND durum=?"
                        params.append(durum)
                    if proje_adi:
                        sql += " AND proje_adi=?"
                        params.append(proje_adi)
                    sql += " ORDER BY baslangic_zamani DESC LIMIT ?"
                    params.append(limit)
                    cur = conn.execute(sql, params)
                    sonuc = []
                    for row in cur.fetchall():
                        sonuc.append({
                            "gorev_id": row["gorev_id"],
                            "istek": row["istek"],
                            "baslangic_zamani": row["baslangic_zamani"],
                            "bitis_zamani": row["bitis_zamani"],
                            "kullanilan_araclar": json.loads(row["kullanilan_araclar"] or "[]"),
                            "kullanilan_model": row["kullanilan_model"],
                            "durum": row["durum"],
                            "sonuc": row["sonuc"],
                            "hata_bilgisi": row["hata_bilgisi"],
                            "devam_etilebilir_asama": row["devam_etilebilir_asama"],
                            "proje_adi": row["proje_adi"],
                            "kaynak": row["kaynak"],
                        })
                    return sonuc
                finally:
                    conn.close()
        except Exception:
            return []

    def gorev_oku(self, gorev_id: str) -> Optional[Dict[str, Any]]:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    cur = conn.execute("SELECT * FROM gorevler WHERE gorev_id=?", (gorev_id,))
                    row = cur.fetchone()
                    if row is None:
                        return None
                    adimlar = []
                    for a in conn.execute(
                        "SELECT * FROM gorev_adimlari WHERE gorev_id=? ORDER BY sira",
                        (gorev_id,),
                    ):
                        adimlar.append({
                            "adim_id": a["adim_id"],
                            "sira": a["sira"],
                            "arac_adi": a["arac_adi"],
                            "args": json.loads(a["args"] or "{}"),
                            "durum": a["durum"],
                            "sonuc": a["sonuc"],
                            "hata": a["hata"],
                            "zaman": a["zaman"],
                        })
                    return {
                        "gorev_id": row["gorev_id"],
                        "istek": row["istek"],
                        "baslangic_zamani": row["baslangic_zamani"],
                        "bitis_zamani": row["bitis_zamani"],
                        "kullanilan_araclar": json.loads(row["kullanilan_araclar"] or "[]"),
                        "kullanilan_model": row["kullanilan_model"],
                        "durum": row["durum"],
                        "sonuc": row["sonuc"],
                        "hata_bilgisi": row["hata_bilgisi"],
                        "devam_etilebilir_asama": row["devam_etilebilir_asama"],
                        "proje_adi": row["proje_adi"],
                        "kaynak": row["kaynak"],
                        "adimlar": adimlar,
                    }
                finally:
                    conn.close()
        except Exception:
            return None

    def yarim_kalan_gorevleri(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Devam ettirilebilen (tamamlanmayan) görevleri döndürür."""
        return self.gorevleri_listele(
            durum="calisiyor", limit=limit
        )

    # ------------------------------------------------------------------
    # Genel hafıza kayıtları
    # ------------------------------------------------------------------
    def hafiza_yaz(
        self,
        anahtar: str,
        deger: Any,
        kategori: str = "genel",
        kaynak: Optional[str] = None,
    ) -> str:
        kid = "k_" + uuid.uuid4().hex[:12]
        try:
            with _LOCK:
                conn = _connect()
                try:
                    conn.execute(
                        """INSERT INTO hafiza_kayitlari
                           (kayit_id, anahtar, deger, kategori, zaman, kaynak)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            kid,
                            anahtar,
                            self._filtrele_hassasi(json.dumps(deger, ensure_ascii=False)),
                            kategori,
                            time.time(),
                            kaynak,
                        ),
                    )
                    conn.commit()
                    return kid
                finally:
                    conn.close()
        except Exception:
            return kid

    def hafiza_ara(
        self,
        sorgu: str,
        kategori: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Doğal dil ile hafıza kayıtlarında arama yapar."""
        try:
            with _LOCK:
                conn = _connect()
                try:
                    sql = (
                        "SELECT * FROM hafiza_kayitlari "
                        "WHERE (anahtar LIKE ? OR deger LIKE ?)"
                    )
                    params = ["%" + sorgu + "%", "%" + sorgu + "%"]
                    if kategori:
                        sql += " AND kategori=?"
                        params.append(kategori)
                    sql += " ORDER BY zaman DESC LIMIT ?"
                    params.append(limit)
                    cur = conn.execute(sql, params)
                    sonuc = []
                    for row in cur.fetchall():
                        sonuc.append({
                            "kayit_id": row["kayit_id"],
                            "anahtar": row["anahtar"],
                            "deger": row["deger"],
                            "kategori": row["kategori"],
                            "zaman": row["zaman"],
                            "kaynak": row["kaynak"],
                        })
                    return sonuc
                finally:
                    conn.close()
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Kullanıcı onayları (kararlar)
    # ------------------------------------------------------------------
    def karar_kaydet(
        self,
        islem: str,
        onay_verildi: bool,
        aciklama: Optional[str] = None,
    ) -> str:
        cid = "c_" + uuid.uuid4().hex[:12]
        try:
            with _LOCK:
                conn = _connect()
                try:
                    conn.execute(
                        """INSERT INTO kararlar
                           (karar_id, islem, onay_verildi, zaman, aciklama)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            cid,
                            islem,
                            1 if onay_verildi else 0,
                            time.time(),
                            aciklama,
                        ),
                    )
                    conn.commit()
                    return cid
                finally:
                    conn.close()
        except Exception:
            return cid

    # ------------------------------------------------------------------
    # Silme / temizleme
    # ------------------------------------------------------------------
    def sil_hafiza(self, kayit_id: str) -> bool:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    conn.execute("DELETE FROM hafiza_kayitlari WHERE kayit_id=?", (kayit_id,))
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception:
            return False

    def sil_proje(self, proje_adi: str) -> bool:
        return self.proje_sil(proje_adi)

    def sil_gorev(self, gorev_id: str) -> bool:
        try:
            with _LOCK:
                conn = _connect()
                try:
                    conn.execute("DELETE FROM gorev_adimlari WHERE gorev_id=?", (gorev_id,))
                    conn.execute("DELETE FROM gorevler WHERE gorev_id=?", (gorev_id,))
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception:
            return False

    def veritabani_bosu_mu(self) -> bool:
        """Veritabanının okunabilir ve bozuk olmadığını test eder."""
        try:
            with _LOCK:
                conn = _connect()
                try:
                    conn.execute("SELECT COUNT(*) FROM gorevler").fetchone()
                    return False
                finally:
                    conn.close()
        except Exception:
            return True


# Tekil örnek
hafiza = HafizaYoneticisi()

if __name__ == "__main__":
    # Hızlı test
    print("Hafıza testi başlatılıyor...")
    gid = hafiza.gorev_baslat("test görev", proje_adi="JARVIS", kaynak="test")
    print("Görev ID:", gid)
    hafiza.gorev_adim_ekle(gid, 1, "sistem_durumu", {}, "tamam", "OK")
    hafiza.gorev_bitir(gid, "tamamlandi", sonuc="basarili")
    print("Görevler:", hafiza.gorevleri_listele(limit=5))
    hafiza.hafiza_yaz("tercih:tema", "koyu", kategori="arayuz", kaynak="test")
    print("Hafıza ara:", hafiza.hafiza_ara("tema", limit=5))
    print("Projeler:", hafiza.projeleri_listele())
    print("Yarım kalan:", hafiza.yarim_kalan_gorevleri())
    print("Tüm testler tamamlandı.")
