"""
Pengiriman alert ke Telegram menggunakan pyTelegramBotAPI (telebot).
"""
from typing import Dict, Any

import telebot

import config

bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN, parse_mode="Markdown") if config.TELEGRAM_BOT_TOKEN else None


def _fmt_usd(value) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_pct(value) -> str:
    try:
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def build_message(pair: Dict[str, Any]) -> str:
    base = pair.get("baseToken") or {}
    name = base.get("name", "Unknown")
    symbol = base.get("symbol", "?")
    address = base.get("address", "N/A")
    chain_id = pair.get("chainId", "N/A")
    url = pair.get("url", f"https://dexscreener.com/{chain_id}/{pair.get('pairAddress', '')}")

    volume = pair.get("volume") or {}
    price_change = pair.get("priceChange") or {}
    liquidity = (pair.get("liquidity") or {}).get("usd")
    price_usd = pair.get("priceUsd", "N/A")
    security_summary = pair.get("_security_summary", "tidak terverifikasi")

    nar = pair.get("_narrative", {})
    nar_score = nar.get("score", 0)
    nar_label = nar.get("label", "Minim data")
    nar_desc = nar.get("description") or "Belum ada deskripsi proyek yang terdeteksi."
    links_found = ", ".join(
        filter(None, [
            "Website" if nar.get("has_website") else None,
            "Twitter" if nar.get("has_twitter") else None,
            "Telegram" if nar.get("has_telegram") else None,
        ])
    ) or "belum ada link resmi terdeteksi"

    community_line = ""
    if nar.get("coingecko_indexed"):
        community_line = (
            f"👥 Twitter: {nar.get('twitter_followers', 0):,} | "
            f"Telegram: {nar.get('telegram_users', 0):,} | "
            f"Watchlist CG: {nar.get('watchlist_users', 0):,}\n"
        )

    return (
        "🚨 *POTENSI AKUMULASI TERDETEKSI*\n\n"
        f"🪙 *{name}* (`{symbol}`)\n"
        f"⛓ Chain: {chain_id}\n"
        f"📜 CA: `{address}`\n\n"
        f"🧭 *Kekuatan Narasi: {nar_label}* (skor {nar_score})\n"
        f"📝 {nar_desc}\n"
        f"🔗 Link resmi: {links_found}\n"
        f"{community_line}\n"
        f"📈 Vol 1H: {_fmt_usd(volume.get('h1'))} | Vol 24H: {_fmt_usd(volume.get('h24'))}\n"
        f"💧 Likuiditas: {_fmt_usd(liquidity)}\n"
        f"💵 Harga: ${price_usd} | Δ1H: {_fmt_pct(price_change.get('h1'))} | Δ24H: {_fmt_pct(price_change.get('h24'))}\n\n"
        f"🛡 Keamanan: {security_summary}\n\n"
        f"📊 Chart: {url}\n\n"
        "⚠️ _Bukan saran finansial. DYOR -- risiko memecoin sangat tinggi,_\n"
        "_termasuk kemungkinan scam/rug pull. Data keamanan & narasi bersifat_\n"
        "_heuristik, bukan jaminan._"
    )


def send_alert(pair: Dict[str, Any]) -> bool:
    if not bot or not config.TELEGRAM_CHAT_ID:
        print("[telegram] BOT_TOKEN / CHAT_ID belum diset, alert dilewati.")
        return False
    try:
        bot.send_message(
            config.TELEGRAM_CHAT_ID,
            build_message(pair),
            disable_web_page_preview=False,
        )
        return True
    except Exception as e:
        print(f"[telegram] gagal mengirim alert: {e}")
        return False
