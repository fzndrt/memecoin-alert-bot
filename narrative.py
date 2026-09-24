"""
Skoring kekuatan narasi/identitas proyek sebuah token.

Filosofi: token dengan TUJUAN YANG JELAS (website, sosial media aktif,
deskripsi proyek yang jelas) dan yang MULAI BANYAK DIBICARAKAN (follower
Twitter/anggota Telegram yang tumbuh, jumlah watchlist CoinGecko) lebih
layak diprioritaskan dibanding token yang cuma naik volume tanpa identitas
jelas. Ini yang membedakan token bernarasi kuat (identitas & cerita jelas,
komunitas terbangun sebelum harga bergerak) dari token yang harganya naik
murni karena bot/wash-trading tanpa cerita di baliknya.

Ada 2 sumber skor:
1. Profil token di DexScreener (tersedia untuk hampir semua token, bahkan
   yang sangat baru) -- deskripsi proyek + link resmi (website/sosmed).
2. Data komunitas CoinGecko (via lookup contract address, gratis tanpa
   API key) -- follower Twitter, anggota Telegram, watchlist_portfolio_users.
   Sumber ini kaya, TAPI token yang benar-benar baru biasanya belum
   terindeks -- karena itu skor ini bersifat BONUS, bukan syarat mutlak.
"""
import math
from typing import Dict, Any, List, Optional

from data_sources import coingecko


def _dex_profile_link_types(profile_item: Optional[Dict[str, Any]]) -> List[str]:
    if not profile_item:
        return []
    links = profile_item.get("links") or []
    return [l.get("type") or l.get("label") or "link" for l in links if isinstance(l, dict)]


def score_from_dexscreener_profile(profile_item: Optional[Dict[str, Any]]) -> float:
    """Skor dari data token-profiles DexScreener -- deskripsi & link resmi."""
    if not profile_item:
        return 0.0
    score = 0.0

    description = (profile_item.get("description") or "").strip()
    if len(description) >= 40:
        score += 2.0
    elif description:
        score += 0.5

    link_types = _dex_profile_link_types(profile_item)
    score += min(len(link_types), 4) * 0.75  # website, twitter, telegram, dst.

    return score


def score_from_coingecko(chain_id: str, token_address: str) -> Dict[str, Any]:
    """Skor & detail komunitas dari CoinGecko (jika token sudah terindeks)."""
    coin = coingecko.get_coin_by_contract(chain_id, token_address)
    if not coin:
        return {"score": 0.0, "found": False}

    community = coin.get("community_data") or {}
    links = coin.get("links") or {}
    description = ((coin.get("description") or {}).get("en") or "").strip()

    score = 0.0
    if description:
        score += 1.5
    if any(links.get("homepage") or []):
        score += 1.5
    if links.get("twitter_screen_name"):
        score += 1.0
    if links.get("telegram_channel_identifier"):
        score += 1.0

    twitter_followers = int(community.get("twitter_followers") or 0)
    telegram_users = int(community.get("telegram_channel_user_count") or 0)
    watchlist_users = int(coin.get("watchlist_portfolio_users") or 0)

    # Skala logaritmik: proyek dengan ribuan follower tidak membanjiri
    # skor dibanding proyek yang baru mulai tapi trennya jelas naik.
    if twitter_followers > 0:
        score += min(math.log10(twitter_followers + 1), 4.0)
    if telegram_users > 0:
        score += min(math.log10(telegram_users + 1), 4.0)
    if watchlist_users > 0:
        # Watchlist = orang aktif menandai koin ini untuk dipantau --
        # sinyal "orang mulai membicarakannya" yang cukup kuat & organik.
        score += min(math.log10(watchlist_users + 1), 3.0)

    return {
        "score": score,
        "found": True,
        "twitter_followers": twitter_followers,
        "telegram_users": telegram_users,
        "watchlist_users": watchlist_users,
        "description": description[:220],
        "has_website": any(links.get("homepage") or []),
        "has_twitter": bool(links.get("twitter_screen_name")),
        "has_telegram": bool(links.get("telegram_channel_identifier")),
    }


def label_for_score(score: float) -> str:
    if score >= 6.0:
        return "Kuat 🔥"
    if score >= 3.0:
        return "Sedang"
    if score > 0:
        return "Baru mulai"
    return "Minim data"


def evaluate(chain_id: str, token_address: str, profile_item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Gabungkan skor dari DexScreener profile + CoinGecko menjadi satu
    hasil evaluasi narasi yang siap dipakai analyzer & pesan alert."""
    dex_score = score_from_dexscreener_profile(profile_item)
    cg_result = score_from_coingecko(chain_id, token_address)

    total_score = dex_score + cg_result["score"]

    return {
        "score": round(total_score, 2),
        "label": label_for_score(total_score),
        "description": cg_result.get("description") or (profile_item or {}).get("description", "")[:220],
        "has_website": cg_result.get("has_website", False) or "website" in _dex_profile_link_types(profile_item),
        "has_twitter": cg_result.get("has_twitter", False) or "twitter" in _dex_profile_link_types(profile_item),
        "has_telegram": cg_result.get("has_telegram", False) or "telegram" in _dex_profile_link_types(profile_item),
        "twitter_followers": cg_result.get("twitter_followers", 0),
        "telegram_users": cg_result.get("telegram_users", 0),
        "watchlist_users": cg_result.get("watchlist_users", 0),
        "coingecko_indexed": cg_result.get("found", False),
    }
