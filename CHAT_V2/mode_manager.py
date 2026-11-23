#!/usr/bin/env python
"""ModeManager - Tek etkin mod yönetimi."""

import json
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any


# Mod tanımlamaları
MOD_ONLINE = "online"
MOD_OFFLINE = "offline"
MOD_AUTO = "auto"

MOD_LABELS = {
    MOD_ONLINE: "ONLINE (bulut AI)",
    MOD_OFFLINE: "OFFLINE (yerel AI)",
    MOD_AUTO: "AUTO (internet varsa bulut, yoksa yerel)",
}

# Config dosyası yolları
CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
CONFIG_MOD_PATH = CONFIG_DIR / "jarvis_mod.json"


class ModeManager:
    """Tek etkin mod yönetimi."""

    def __init__(self, config_path: Optional[Path] = None):
        self._mod: Optional[str] = None
        self._mod_time_ms: int = 0
        self._config_path = config_path or CONFIG_MOD_PATH
        self._load_count: int = 0
        self._last_load_time: float = 0
        self._loaded_config_signature: Optional[tuple[int, int]] = None
        self._load_mod()
        self._loaded_config_signature = self._config_signature()

    # --- Temel erişim ---

    def _config_signature(self) -> Optional[tuple[int, int]]:
        """Return a signature used to detect external config changes."""
        try:
            stat = self._config_path.stat()
            return (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    def get_mod(self) -> str:
        """Return the latest mode from the shared configuration."""
        signature = self._config_signature()
        if self._mod is None or signature != self._loaded_config_signature:
            self._load_mod()
            self._loaded_config_signature = self._config_signature()
        return self._mod or MOD_ONLINE

    def set_mod(self, mod: str, *, save: bool = True) -> None:
        """Modu değiştir ve optionally config'i kaydet."""
        mod = mod.lower().strip()
        if mod not in (MOD_ONLINE, MOD_OFFLINE, MOD_AUTO):
            raise ValueError(f"Geçersiz mod: {mod}")
        old_mod = self._mod
        self._mod = mod
        self._mod_time_ms = int(time.time() * 1000)
        if save:
            self._save_mod(mod)
            self._loaded_config_signature = self._config_signature()
        # Mod değişti bildirimi (gerçek UYGULAMA'da burada GUI/router bildirilir)
        # print(f"[ModeManager] Mod changed: {old_mod} -> {mod}")

    def get_mod_with_time(self) -> tuple[str, int]:
        """Return the latest mode and its change time."""
        mod = self.get_mod()
        return mod, self._mod_time_ms

    # --- Mod belirleme (internet kontrolü YAPMAZ) ---

    def resolve_mode(
        self,
        *,
        force: Optional[str] = None,
    ) -> str:
        """Resolve mode and return the effective mode string."""
        if force and force.lower().strip() in (MOD_ONLINE, MOD_OFFLINE, MOD_AUTO):
            self.set_mod(force, save=True)
        return self.get_mod()

    # --- Config okuma/yazma ---

    def _load_mod(self) -> None:
        """Config dosyasından modu oku (sadece bir kere/başlangıçta)."""
        try:
            if not self._config_path.exists():
                # Varsayılan: online
                self._mod = MOD_ONLINE
                self._mod_time_ms = int(time.time() * 1000)
                self._save_mod(MOD_ONLINE)
                return

            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # mod değerini farklı possible konumlarda ara
            stored_mod = (
                data.get("mod")
                or data.get("MODE")
                or data.get("aktif_mod")
                or None
            )
            stored_mod = (stored_mod or "").lower().strip() if stored_mod else None
            if stored_mod in (MOD_ONLINE, MOD_OFFLINE, MOD_AUTO):
                self._mod = stored_mod
            else:
                # Varsayılan: online
                self._mod = MOD_ONLINE
                # Config'e online kaydet (yoksa oluştur)
                self._save_mod(MOD_ONLINE)
        except (json.JSONDecodeError, IOError, KeyError):
            # Hata durumunda varsayılan: online
            self._mod = MOD_ONLINE
            self._save_mod(MOD_ONLINE)
        finally:
            self._load_count += 1
            self._last_load_time = time.time() * 1000

    def _save_mod(self, mod: str) -> None:
        """Atomically save mode while preserving other config fields."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {}
            if self._config_path.exists():
                try:
                    with self._config_path.open("r", encoding="utf-8") as f:
                        existing = json.load(f)
                    if isinstance(existing, dict):
                        data = existing
                except (json.JSONDecodeError, OSError):
                    data = {}
            data["mod"] = mod
            data["zaman"] = int(time.time())
            tmp_path = self._config_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._config_path)
        except OSError:
            pass

    # --- Bilgi ---

    def get_stats(self) -> Dict[str, Any]:
        """İstatistikleri döndür."""
        return {
            "current_mod": self.get_mod(),
            "mod_time_ms": self._mod_time_ms,
            "load_count": self._load_count,
            "last_load_time_ms": self._last_load_time,
            "available_modes": [MOD_ONLINE, MOD_OFFLINE, MOD_AUTO],
        }

    def get_label(self) -> str:
        """Kullanıcıya gösterilebilir mod etiketini döndür."""
        return MOD_LABELS.get(self.get_mod(), "BILINMEYEN")


# === Tek örnek (singleton) yardımcı fonksiyonlar ===

_global_manager: Optional[ModeManager] = None


def get_mode_manager() -> ModeManager:
    """Global ModeManager örneğini döndür."""
    global _global_manager
    if _global_manager is None:
        _global_manager = ModeManager()
    return _global_manager


def set_mode(mod: str, *, save: bool = True) -> None:
    """Kısayol: Modu değiştir."""
    get_mode_manager().set_mod(mod, save=save)


def get_mode() -> str:
    """Kısayol: Mevcut modu döndür."""
    return get_mode_manager().get_mod()


def get_mode_label() -> str:
    """Kısayol: Mod etiketini döndür."""
    return get_mode_manager().get_label()


def resolve_mode(*, force: Optional[str] = None) -> str:
    """Kısayol: Mod belirle."""
    return get_mode_manager().resolve_mode(force=force)


# Örnek kullanım
if __name__ == "__main__":
    mm = ModeManager()
    print(f"Başlangıç mod: {mm.get_mod()} ({mm.get_label()})")
    print(f"İstatistikler: {mm.get_stats()}")
    
    # Mod değiştirme testi
    mm.set_mod("offline")
    print(f"Değişik mod: {mm.get_mod()} ({mm.get_label()})")
    
    # Kısayol testleri
    print(f"Kısayol mod: {get_mode()}")
    print(f"Kısayol etiket: {get_mode_label()}")