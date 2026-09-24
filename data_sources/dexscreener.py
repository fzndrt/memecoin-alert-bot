"""
Wrapper untuk DexScreener public API (tanpa API key).
Referensi tidak resmi: https://docs.dexscreener.com/api/reference
"""
import requests
from typing import List, Dict, Any

BASE_URL = "https://api.dexscreener.com"
TIMEOUT = 15


def _get(path: str, params: dict = None) -> Any:
    try:
        resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"[dexscreener] request gagal ({path}): {e}")
        return None


def get_latest_boosted_tokens() -> List[Dict[str, Any]]:
    """Token yang baru saja di-'boost' (dipromosikan) di DexScreener.
    Kenaikan boost sering berkorelasi dengan lonjakan perhatian/narasi baru."""
    data = _get("/token-boosts/latest/v1")
    return data if isinstance(data, list) else []


def get_top_boosted_tokens() -> List[Dict[str, Any]]:
    """Token dengan boost aktif terbanyak saat ini."""
    data = _get("/token-boosts/top/v1")
    return data if isinstance(data, list) else []


def get_latest_token_profiles() -> List[Dict[str, Any]]:
    """Profil token baru (biasanya disertai deskripsi/narasi proyek)."""
    data = _get("/token-profiles/latest/v1")
    return data if isinstance(data, list) else []


def get_pairs_for_token(chain_id: str, token_address: str) -> List[Dict[str, Any]]:
    """Ambil semua pair (pasar) untuk satu alamat token di suatu chain."""
    data = _get(f"/token-pairs/v1/{chain_id}/{token_address}")
    return data if isinstance(data, list) else []


def search_pairs(query: str) -> List[Dict[str, Any]]:
    data = _get("/latest/dex/search", params={"q": query})
    if not data:
        return []
    return data.get("pairs", []) or []
