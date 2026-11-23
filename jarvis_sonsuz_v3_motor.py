# -*- coding: utf-8 -*-
"""JARVIS SONSUZ v3 — MOTOR (ince sarmalayici, z42).

V4 spec: motor dosyasi COK BUYUMEZ; gercek beyin jarvis_sonsuz2 icinde
kalir (komut/sohbet/ikisi ayrimi + param-grammar kernel). Bu dosya
yalnizca tek giris sarmalayicisidir:

  - v3_talep(talep, log, ses)  -> sonsuz2.calistir(talep, ...)
  - v3_baslat(log, ses)        -> sonsuz2.baslat(...)

Hatalar ASLA sessiz kalmaz: her except log'a yazar ve durum_dict doner.
"""

MODULE_TAG = 'sonsuz_v3_motor'


def _log_yaz(log, metin):
    """Log yaz; log yoksa stdout."""
    metin = str(metin or '')
    try:
        if callable(log):
            log(metin)
            return
    except Exception:
        pass
    try:
        print('[' + MODULE_TAG + '] ' + metin, flush=True)
    except Exception:
        pass


def v3_talep(talep, log=None, ses=None, ekran_al=True):
    """SONSUZ v2 beyinine ince gecis. Hata dondurmez, dict dondurur."""
    try:
        import jarvis_sonsuz2 as s2
    except Exception as e:
        _log_yaz(log, 'ERR: sonsuz2 modulu yuklenemedi: ' + repr(e)[:160])
        return {'durum': 'MODUL_HATA', 'hata': repr(e)[:160]}
    try:
        return s2.calistir(talep, log=log, ses=ses, ekran_al=ekran_al)
    except Exception as e:
        _log_yaz(log, 'ERR: sonsuz2.calistir patladi: ' + repr(e)[:200])
        try:
            s2.oyun_durdur(log)
        except Exception:
            pass
        return {'durum': 'CALISTIR_HATA', 'hata': repr(e)[:200]}


def v3_baslat(log=None, ses=None):
    """Arka plan servisleri (hatirlatici, fiyat, AFK) tek kapidan."""
    try:
        import jarvis_sonsuz2 as s2
        s2.baslat(log=log, ses=ses)
        return True
    except Exception as e:
        _log_yaz(log, 'ERR: sonsuz2.baslat patladi: ' + repr(e)[:160])
        return False


def v3_donustur_uyari():
    """Eski modul adi destek: motor kendi kimligini bildirir."""
    return {'motor': MODULE_TAG, 'surum': 'v3'}

import json
import time
import threading
import traceback
from pathlib import Path

class JarvisTaskEngine:

    def __init__(self, log_path=None, max_steps=30):
        self.tools = {}
        self.max_steps = max_steps
        self.lock = threading.Lock()
        self.cancel_event = threading.Event()
        self.running = False
        self.last_result = None

        self.log_path = (
            Path(log_path) if log_path
            else Path(__file__).parent / "memory" / "sonsuz_v3_log.jsonl"
        )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event, **data):
        record = {
            "time": time.time(),
            "event": event,
            "data": data
        }
        try:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def register_tool(self, name, function, description="", risk="safe"):
        if not isinstance(name, str) or not name.replace("_", "").isalnum():
            raise ValueError("Gecersiz arac adi.")
        if not callable(function):
            raise TypeError("Arac bir fonksiyon olmali.")
        if risk not in ("safe", "confirm", "blocked"):
            raise ValueError("Gecersiz risk seviyesi.")

        self.tools[name] = {
            "function": function,
            "description": description,
            "risk": risk
        }
        self.log("TOOL_REGISTERED", name=name)
        return True

    def tool_catalog(self):
        return [
            {
                "name": name,
                "description": tool["description"],
                "risk": tool["risk"]
            }
            for name, tool in self.tools.items()
        ]

    def stop(self):
        self.cancel_event.set()
        self.log("STOP_REQUESTED")

    def status(self):
        return {
            "running": self.running,
            "tools": len(self.tools),
            "cancel_requested": self.cancel_event.is_set()
        }

    def create_plan(self, task, planner):
        raw = planner(task, self.tool_catalog())

        if isinstance(raw, str):
            raw = json.loads(raw)

        if not isinstance(raw, dict):
            raise ValueError("AI plani gecersiz.")

        steps = raw.get("steps")

        if not isinstance(steps, list):
            raise ValueError("Plan steps listesi icermeli.")

        if len(steps) > self.max_steps:
            raise ValueError("Adim siniri asildi.")

        for step in steps:
            if not isinstance(step, dict):
                raise ValueError("Gecersiz adim.")

            name = step.get("tool")
            args = step.get("args", {})

            if name not in self.tools:
                raise ValueError("Kayitsiz arac: " + str(name))

            if not isinstance(args, dict):
                raise ValueError("Gecersiz arac argumanlari.")

        return steps

    def run(self, task, planner=None, confirm=None):
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "error": "Baska gorev calisiyor."}

        self.running = True
        self.cancel_event.clear()
        results = []

        try:
            self.log("TASK_STARTED", task=task)

            if not callable(planner):
                return {"ok": False, "error": "AI planlayici baglanmamis."}

            steps = self.create_plan(task, planner)

            for number, step in enumerate(steps, 1):
                if self.cancel_event.is_set():
                    return {
                        "ok": False,
                        "cancelled": True,
                        "results": results
                    }

                name = step["tool"]
                args = step.get("args", {})
                tool = self.tools[name]

                if tool["risk"] == "blocked":
                    results.append({
                        "tool": name,
                        "ok": False,
                        "error": "Arac engellendi."
                    })
                    continue

                if tool["risk"] == "confirm":
                    approved = False
                    if callable(confirm):
                        try:
                            approved = bool(confirm(name, step, args))
                        except Exception:
                            approved = False

                    if not approved:
                        results.append({
                            "tool": name,
                            "ok": False,
                            "error": "Onay verilmedi."
                        })
                        continue

                try:
                    output = tool["function"](**args)
                    tool_ok = not (
                        isinstance(output, dict)
                        and output.get("ok") is False
                    )

                    result_item = {
                        "tool": name,
                        "ok": tool_ok,
                        "result": repr(output)[:3000]
                    }

                    if not tool_ok:
                        result_item["error"] = str(
                            output.get("error")
                            or output.get("hata")
                            or "Arac basarisiz sonuc bildirdi."
                        )[:1000]

                    results.append(result_item)

                    self.log(
                        "TOOL_COMPLETED" if tool_ok else "TOOL_REPORTED_FAILURE",
                        name=name,
                        step=number
                    )

                except Exception as exc:
                    results.append({
                        "tool": name,
                        "ok": False,
                        "error": repr(exc)
                    })
                    self.log("TOOL_ERROR", name=name, error=repr(exc))

            final = {
                "ok": all(item["ok"] for item in results),
                "task": task,
                "steps": len(steps),
                "results": results
            }

            self.last_result = final
            self.log("TASK_FINISHED", ok=final["ok"])
            return final

        except Exception as exc:
            self.log(
                "ENGINE_ERROR",
                error=repr(exc),
                traceback=traceback.format_exc()
            )
            return {"ok": False, "error": repr(exc)}

        finally:
            self.running = False
            self.lock.release()
