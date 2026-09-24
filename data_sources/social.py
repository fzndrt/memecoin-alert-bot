"""
Integrasi sosial media (OPSIONAL).

Twitter/X API v2 versi gratis saat ini sangat terbatas dan pada praktiknya
membutuhkan tier berbayar untuk pencarian/pengukuran volume tweet secara
terjadwal. Modul ini disediakan sebagai kerangka jika Anda punya akses
tersebut; jika ENABLE_TWITTER=false, fungsi akan mengembalikan None dan
sistem akan mengandalkan sinyal dari DexScreener (boosts & token profiles)
sebagai proksi narasi -- lihat data_sources/dexscreener.py.
"""
from typing import Optional
import requests

import config

TIMEOUT = 15


def get_tweet_count_last_hour(query: str) -> Optional[int]:
    if not config.ENABLE_TWITTER or not config.TWITTER_BEARER_TOKEN:
        return None
    try:
        resp = requests.get(
            "https://api.twitter.com/2/tweets/counts/recent",
            headers={"Authorization": f"Bearer {config.TWITTER_BEARER_TOKEN}"},
            params={"query": query, "granularity": "hour"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        counts = data.get("data", [])
        return counts[-1]["tweet_count"] if counts else 0
    except requests.RequestException as e:
        print(f"[social] request gagal: {e}")
        return None
