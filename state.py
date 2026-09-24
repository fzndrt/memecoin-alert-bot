"""
Penyimpanan sederhana berbasis file JSON untuk mencegah alert duplikat
pada token yang sama dalam periode cooldown tertentu.

Catatan: pada Render free tier, disk bersifat ephemeral (akan direset saat
redeploy/instance baru). Untuk kebutuhan produksi yang lebih andal, ganti
implementasi ini dengan Redis atau database eksternal.
"""
import json
import os
import time
from typing import Dict

import config


def _load() -> Dict[str, float]:
    if not os.path.exists(config.STATE_FILE):
        return {}
    try:
        with open(config.STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: Dict[str, float]) -> None:
    try:
        with open(config.STATE_FILE, "w") as f:
            json.dump(data, f)
    except OSError as e:
        print(f"[state] gagal menyimpan state: {e}")


def already_alerted(address: str) -> bool:
    data = _load()
    ts = data.get(address.lower())
    if ts is None:
        return False
    cooldown_seconds = config.ALERT_COOLDOWN_HOURS * 3600
    return (time.time() - ts) < cooldown_seconds


def mark_alerted(address: str) -> None:
    data = _load()
    data[address.lower()] = time.time()
    _save(data)
