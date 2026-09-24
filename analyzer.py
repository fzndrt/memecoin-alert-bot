"""
Logika inti: mengumpulkan kandidat token, menghitung metrik akumulasi &
narasi, menyaring berdasarkan kriteria, dan mengembalikan daftar token
yang layak dialert -- diurutkan dari narasi TERKUAT.
"""
import time
from typing import List, Dict, Any

import config
import narrative
from data_sources import dexscreener
from security import goplus


def _collect_candidate_pairs() -> List[Dict[str, Any]]:
    """Kumpulkan pair kandidat dari token yang baru di-boost & profil baru
    di DexScreener -- dua sinyal ini sering muncul saat sebuah narasi/koin
    mulai ramai dibicarakan sebelum harga bergerak besar."""
    seen_keys = set()
    candidates: List[Dict[str, Any]] = []

    boosted = dexscreener.get_latest_boosted_tokens() + dexscreener.get_top_boosted_tokens()
    profiles = dexscreener.get_latest_token_profiles()

    for item in boosted + profiles:
        chain_id = (item.get("chainId") or "").lower()
        address = item.get("tokenAddress")
        if not address or chain_id not in config.CHAINS:
            continue
        key = f"{chain_id}:{address.lower()}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

        pairs = dexscreener.get_pairs_for_token(chain_id, address)
        for pair in pairs:
            pair["_profile_item"] = item  # dipakai narrative.py utk skor deskripsi/link
            candidates.append(pair)

    return candidates


def _passes_filters(pair: Dict[str, Any]) -> bool:
    liquidity = (pair.get("liquidity") or {}).get("usd") or 0
    volume = pair.get("volume") or {}
    price_change = pair.get("priceChange") or {}
    txns_h1 = (pair.get("txns") or {}).get("h1") or {}

    vol_h1 = volume.get("h1") or 0
    vol_h24 = volume.get("h24") or 0
    avg_vol_per_hour_24h = vol_h24 / 24 if vol_h24 else 0

    change_h1 = price_change.get("h1") or 0
    change_h24 = price_change.get("h24") or 0

    buys_h1 = txns_h1.get("buys") or 0
    sells_h1 = txns_h1.get("sells") or 0
    buy_sell_ratio = (buys_h1 / sells_h1) if sells_h1 else (float("inf") if buys_h1 else 0)

    if liquidity < config.MIN_LIQUIDITY_USD:
        return False
    if vol_h1 < config.MIN_VOLUME_H1_USD:
        return False
    if avg_vol_per_hour_24h <= 0 or (vol_h1 / avg_vol_per_hour_24h) < config.MIN_VOLUME_SPIKE_RATIO:
        return False
    if not (config.MIN_PRICE_CHANGE_H1 <= change_h1 <= config.MAX_PRICE_CHANGE_H1):
        return False
    if change_h24 > config.MAX_PRICE_CHANGE_H24:
        return False  # kemungkinan sudah pump duluan, bukan lagi fase akumulasi
    if buy_sell_ratio < config.MIN_BUY_SELL_RATIO_H1:
        return False

    return True


def find_accumulation_candidates() -> List[Dict[str, Any]]:
    """Kandidat yang lolos filter market dasar + keamanan + skor narasi
    minimum, diurutkan dari yang narasinya PALING KUAT terlebih dahulu."""
    results = []
    candidates = _collect_candidate_pairs()

    for pair in candidates:
        if not _passes_filters(pair):
            continue

        chain_id = pair.get("chainId", "")
        base_token = pair.get("baseToken") or {}
        address = base_token.get("address", "")

        security_info = None
        if config.ENABLE_SECURITY_CHECK:
            security_info = goplus.check_token_security(chain_id, address)
            if not goplus.is_token_safe_enough(security_info, config.MAX_BUY_TAX_PCT, config.MAX_SELL_TAX_PCT):
                continue

        # Evaluasi narasi/identitas proyek -- ini penentu utama apakah
        # token cukup layak dialert, bukan sekadar lolos filter volume.
        narrative_result = narrative.evaluate(chain_id, address, pair.get("_profile_item"))
        time.sleep(config.CG_REQUEST_DELAY_SECONDS)  # jaga rate limit CoinGecko

        if narrative_result["score"] < config.MIN_NARRATIVE_SCORE:
            continue

        pair["_security_summary"] = goplus.summarize_security(security_info)
        pair["_narrative"] = narrative_result
        results.append(pair)

    # Urutkan: narasi terkuat di paling atas -> jadi fokus utama saat
    # membaca alert yang masuk berurutan ke Telegram.
    results.sort(key=lambda p: p["_narrative"]["score"], reverse=True)
    return results
