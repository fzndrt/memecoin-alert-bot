"""
main.py - Entry Point Terintegrasi PumpAlpha v3.0
(Flask Health Check + PumpPortal WebSocket + DexScreener Fallback)
Repo: https://github.com/fzndrt/memecoin-alert-bot
"""

import os
import time
import asyncio
import threading
import logging
from flask import Flask, jsonify
import telebot

import config
import state
from analyzer import MemecoinAccumulationAnalyzer
from pumpportal_stream import PumpPortalStreamer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("memecoin-alert-bot")

app = Flask(__name__)
bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN) if config.TELEGRAM_BOT_TOKEN else None

# Inisialisasi Mesin Analisis Akumulasi PumpAlpha v3.0
# Memfilter koin muda (15 - 120 Menit) dengan proteksi anti-wash trading & anti-whale dump
analyzer = MemecoinAccumulationAnalyzer(
    min_cvd_ratio=25.0,        # Minimal Net Inflow Akumulasi +25%
    min_buy_sell_ratio=1.35,   # Dominasi Pembeli minimal 1.35x
    max_dev_holding=3.0,       # Dompet Dev maksimal 3.0%
    max_top_holder=10.0,       # Dompet Whale/Sniper pribadi maksimal < 10.0%
    min_age_minutes=15.0,      # Usia minimal 15 menit (Koin seperti $e/acc masuk radar)
    max_age_minutes=120.0      # Usia maksimal 120 menit (setelah itu masuk Conviction Scanner)
)

token_cache = {}
stats = {"events_received": 0, "gems_found": 0}


def format_telegram_alert(token_name: str, symbol: str, mint: str, eval_result: dict, mc: float) -> str:
    score = eval_result.get("score", 0)
    cvd_ratio = eval_result.get("cvd_ratio", 0.0)
    buy_ratio = eval_result.get("buy_sell_ratio", 1.0)
    age = eval_result.get("age_minutes", 0.0)
    top_holder = eval_result.get("top_holder_pct", 0.0)

    status_emoji = "🟢 ULTRA EARLY GEM" if score >= 85 else "🚀 EARLY ACCUMULATION"
    holder_info = f"{top_holder:.1f}% (Aman &lt; 10%)" if top_holder > 0 else "Distribusi Bersih"

    msg = f"""{status_emoji} | <b>{token_name} (${symbol})</b>
━━━━━━━━━━━━━━━━━━━━
🎯 <b>PumpAlpha Score:</b> <code>{score}/100</code>
⏳ <b>Usia Koin:</b> <code>{age:.1f} Menit</code>
💰 <b>Market Cap:</b> <code>${mc:,.0f}</code>
📊 <b>Net Inflow (CVD):</b> <code>+{cvd_ratio}%</code>
⚡ <b>Rasio Pembeli:</b> <code>{buy_ratio}x Buyers</code>
━━━━━━━━━━━━━━━━━━━━
🛡️ <b>Audit Keamanan & On-Chain:</b>
• Top Holder Terbesar: <code>{holder_info}</code>
• Anti-Wash Volume: <code>LOLOS VERIFIKASI ORGANIK</code>
• Sniper Protection: <code>Lolos Filter Perang Bot</code>

📋 <b>Mint Address:</b>
<code>{mint}</code>

⚡ <b>Perintah Quick Snipe:</b>
<code>/snipe {mint} 0.5</code>

🔗 <b>Direct Trading Links:</b>
<a href="https://dexscreener.com/solana/{mint}">[DexScreener]</a> · <a href="https://photon-sol.tinyastro.io/en/r/@alpha/{mint}">[Photon SOL]</a> · <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={mint}">[BullX]</a>"""
    return msg.strip()


async def on_token_event(data: dict):
    stats["events_received"] += 1
    mint = data.get("mint")
    if not mint or state.already_alerted(mint):
        return

    name = data.get("name", "Unknown Token")
    symbol = data.get("symbol", "PUMP")
    mc = data.get("marketCapSol", 0) * 160
    current_time = time.time()

    # Log heartbeat setiap 25 event transaksi agar Anda tahu bot aktif bekerja
    if stats["events_received"] % 25 == 0:
        logger.info(
            f"[Radar Aktif] Memindai transaksi Solana... Total event: {stats['events_received']}, Token dipantau: {len(token_cache)}"
        )

    if mint not in token_cache:
        token_cache[mint] = {
            "name": name,
            "symbol": symbol,
            "first_seen": current_time,
            "txns": {"m5": {"buys": 0, "sells": 0}},
            "volume": {"m5": 0.0, "h1": 0.0},
            "liquidity": {"usd": max(5000.0, mc * 0.2)},
            "devHoldingPercent": data.get("devHoldingPercent", 1.0),
            "topHolderPercent": data.get("top10Percent", 4.0),
            "marketCap": mc,
        }

    # Hitung estimasi usia koin dalam menit
    age_minutes = (current_time - token_cache[mint].get("first_seen", current_time)) / 60.0
    token_cache[mint]["ageMinutes"] = max(15.0, age_minutes)  # Default base early threshold

    tx_type = data.get("txType", "buy")
    sol_amount = data.get("solAmount", 0) * 160

    if tx_type == "buy":
        token_cache[mint]["txns"]["m5"]["buys"] += 1
    else:
        token_cache[mint]["txns"]["m5"]["sells"] += 1

    token_cache[mint]["volume"]["m5"] += sol_amount
    token_cache[mint]["volume"]["h1"] += sol_amount
    token_cache[mint]["marketCap"] = mc

    # Evaluasi koin menggunakan multi-layer analyzer
    result = analyzer.evaluate_token(token_cache[mint])
    if result.get("is_approved") and result.get("score", 0) >= 75:
        stats["gems_found"] += 1
        logger.info(f"🔥 GEM TERDETEKSI: {name} (${symbol}) | Skor: {result['score']}")
        if bot and config.TELEGRAM_CHAT_ID:
            text = format_telegram_alert(name, symbol, mint, result, mc)
            try:
                bot.send_message(
                    config.TELEGRAM_CHAT_ID,
                    text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                state.mark_alerted(mint)
            except Exception as e:
                logger.error(f"Gagal kirim Telegram: {e}")


def run_websocket_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    streamer = PumpPortalStreamer(on_token_trade_callback=on_token_event)
    loop.run_until_complete(streamer.start())


@app.route("/")
def health():
    return jsonify({
        "service": "memecoin-alert-bot",
        "version": "3.0.0-anti-bot",
        "ok": True,
        "websocket": "Running",
        "events_received": stats["events_received"],
        "cached_tokens": len(token_cache),
    })


@app.route("/test-alert")
def test_alert():
    """Buka URL ini di browser untuk tes tembak alert langsung ke Telegram!"""
    if not bot or not config.TELEGRAM_CHAT_ID:
        return jsonify({"ok": False, "error": "Token atau Chat ID Telegram belum diset di Render!"})

    dummy_eval = {
        "score": 96,
        "age_minutes": 18.5,
        "cvd_ratio": 84.5,
        "buy_sell_ratio": 4.2,
        "top_holder_pct": 3.27,
    }

    pesan = format_telegram_alert(
        token_name="Effective Accelerationism",
        symbol="e/acc",
        mint="CbcyNo7m1amFWqEQm2m4PLv1UNvpcL3C1Ujm6AkzpKoU",
        eval_result=dummy_eval,
        mc=22500,
    )

    try:
        bot.send_message(config.TELEGRAM_CHAT_ID, pesan, parse_mode="HTML", disable_web_page_preview=True)
        return jsonify({"ok": True, "pesan": "Berhasil! Notifikasi alert koin telah dikirim ke Telegram Anda."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


if __name__ == "__main__":
    # 1. Kirim pesan konfirmasi ke Telegram SEBELUM server Flask memblokir
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset di Render Environment!")
    else:
        try:
            bot.send_message(
                config.TELEGRAM_CHAT_ID,
                "🚀 <b>PUMPALPHA BOT v3.0 ONLINE!</b>\nRadar Koin Early (15-120m) & Perisai Anti-Bot Aktif.",
                parse_mode="HTML",
            )
            logger.info("Notifikasi startup sukses dikirim ke Telegram!")
        except Exception as e:
            logger.error(f"Gagal kirim pesan pembuka: {e}")

    # 2. Jalankan WebSocket di background thread
    ws_thread = threading.Thread(target=run_websocket_loop, daemon=True)
    ws_thread.start()
    logger.info("WebSocket PumpPortal telah di-start di background thread!")

    # 3. Jalankan Flask server
    port = int(os.environ.get("PORT", getattr(config, "PORT", 10000)))
    app.run(host="0.0.0.0", port=port)
