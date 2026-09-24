"""
Wrapper tipis untuk CoinGecko public API (tanpa API key, tunduk rate limit
publik ~10-30 request/menit).
"""
import requests
from typing import List, Dict, Any, Optional

BASE_URL = "https://api.coingecko.com/api/v3"
TIMEOUT = 15

# Mapping chainId DexScreener -> asset_platform_id CoinGecko
_PLATFORM_MAP = {
    "ethereum": "ethereum",
    "bsc": "binance-smart-chain",
    "polygon": "polygon-pos",
    "arbitrum": "arbitrum-one",
    "base": "base",
    "avalanche": "avalanche",
    "optimism": "optimistic-ethereum",
    "solana": "solana",
}


def get_trending_coins() -> List[Dict[str, Any]]:
    """7 koin paling banyak dicari di CoinGecko dalam ~3 jam terakhir --
    sinyal awal narasi yang sedang ramai dibicarakan."""
    try:
        resp = requests.get(f"{BASE_URL}/search/trending", timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data.get("coins", []) or []
    except requests.RequestException as e:
        print(f"[coingecko] request gagal: {e}")
        return []


def get_coin_by_contract(chain_id: str, token_address: str) -> Optional[Dict[str, Any]]:
    """Cari data lengkap sebuah token via alamat kontraknya: deskripsi
    proyek, link resmi (website/twitter/telegram), dan community_data
    (jumlah follower Twitter, anggota Telegram, watchlist_portfolio_users).

    Ini SEMUA gratis & tanpa API key -- tapi token yang baru diluncurkan
    (hitungan jam/hari) biasanya BELUM terindeks di CoinGecko, sehingga
    fungsi ini wajar mengembalikan None untuk token semacam itu. Itu bukan
    berarti token buruk, hanya berarti belum ada data komunitas dari sumber
    ini (skor narasi dari sumber lain -- profil DexScreener -- tetap bisa
    dipakai, lihat narrative.py).
    """
    platform = _PLATFORM_MAP.get((chain_id or "").lower())
    if not platform:
        return None
    try:
        resp = requests.get(
            f"{BASE_URL}/coins/{platform}/contract/{token_address}",
            timeout=TIMEOUT,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"[coingecko] request gagal (contract lookup): {e}")
        return None
