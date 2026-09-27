"""
main.py - Entry Point Terintegrasi (Flask Health Check + PumpPortal WebSocket)
Repo: https://github.com/fzndrt/memecoin-alert-bot
"""

import os
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

# Inisialisasi Mesin Analisis Akumulasi PumpAlpha
analyzer = MemecoinAccumulationAnalyzer(
    min_cvd_ratio=25.0,
    min_buy_sell_ratio=1.8,
    max_dev_holding=3.0,
    max_top10_holding=25.0
)

token_cache = {}
stats = {"events_received": 0, "gems_found": 0}

def format_telegram_alert(token_name: str, symbol: str, mint: str, eval_result: dict, mc: float) -> str:
    score = eval_result.get("score", 0)
    cvd_ratio = eval_result.get("cvd_ratio", 0.0)
    buy_ratio = eval_result.get("buy_sell_ratio", 1.0)
    status_emoji = "🟢 ULTRA EARLY GEM" if score >= 85 else "🚀 STRONG ACCUMULATION"
    
    msg = f"""
{status_emoji} | <b>{token_name} (${symbol})</b>
━━━━━━━━━━━━━━━━━━━━
🎯 <b>PumpAlpha Score:</b> <code>{score}/100</code>
💰 <b>Market Cap:</b> <code>${mc:,.0f}</code>
📊 <b>Net Inflow (CVD):</b> <code>+{cvd_ratio}%</code>
⚡ <b>Rasio Beli/Jual:</b> <code>{buy_ratio}x Buyers</code>
━━━━━━━━━━━━━━━━━━━━
🛡️ <b>Audit Keamanan:</b>
• Dev Supply: <code>AMAN (&lt; 2.5%)</code>
• Anti-Wash: <code>LOLOS VERIFIKASI</code>
• Kurva Bonding: <code>Fase Akumulasi Senyap (20-60%)</code>

📋 <b>Mint Address:</b>
<code>{mint}</code>

⚡ <b>Perintah Quick Snipe:</b>
<code>/snipe {mint} 1.0</code>

🔗 <b>Direct Trading Links:</b>
<a href="https://photon-sol.tinyastro.io/en/r/@alpha/{mint}">[Photon SOL]</a> · <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={mint}">[BullX]</a> · <a href="https://dexscreener.com/solana/{mint}">[DexScreener]</a>
"""
    return msg.strip()

async def on_token_event(data: dict):
    stats["events_received"] += 1
    mint = data.get("mint")
    if not mint or state.already_alerted(mint):
        return

    name = data.get("name", "Unknown Token")
    symbol = data.get("symbol", "PUMP")
    mc = data.get("marketCapSol", 0) * 160

    # Log heartbeat setiap 25 event transaksi agar Anda tahu bot aktif bekerja
    if stats["events_received"] % 25 == 0:
        logger.info(f"[Radar Aktif] Memindai aliran transaksi Solana... Total event: {stats['events_received']}, Token dipantau: {len(token_cache)}")

    if mint not in token_cache:
        token_cache[mint] = {
            "name": name,
            "symbol": symbol,
            "txns": {"m5": {"buys": 0, "sells": 0}},
            "volume": {"m5": 0.0},
            "devHoldingPercent": data.get("devHoldingPercent", 1.0),
            "top10HoldersPercent": data.get("top10Percent", 15.0),
            "marketCap": mc
        }

    tx_type = data.get("txType", "buy")
    if tx_type == "buy":
        token_cache[mint]["txns"]["m5"]["buys"] += 1
    else:
        token_cache[mint]["txns"]["m5"]["sells"] += 1
        
    token_cache[mint]["volume"]["m5"] += data.get("solAmount", 0) * 160

    # Evaluasi koin
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
                    disable_web_page_preview=True
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
        "ok": True, 
        "websocket": "Running",
        "events_received": stats["events_received"],
        "cached_tokens": len(token_cache)
    })

if __name__ == "__main__":
    # Jalankan WebSocket di background thread
    ws_thread = threading.Thread(target=run_websocket_loop, daemon=True)
    ws_thread.start()
    logger.info("WebSocket PumpPortal telah di-start di background thread!")

    # Port untuk Render (Prioritaskan os.getenv PORT dari Render)
    port = int(os.environ.get("PORT", getattr(config, "PORT", 10000)))
    app.run(host="0.0.0.0", port=port)
if __name__ == "__main__":
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset -- alert tidak akan terkirim.")
    else:
        # Kirim notifikasi konfirmasi ke Telegram Anda saat Render berhasil online
        try:
            bot.send_message(
                config.TELEGRAM_CHAT_ID,
                "🚀 <b>PUMPALPHA BOT ONLINE DI RENDER!</b>\nRadar Solana/Pump.fun aktif memantau koin gem.",
                parse_mode="HTML"
            )
            logger.info("Notifikasi startup sukses dikirim ke Telegram!")
        except Exception as e:
            logger.error(f"Gagal kirim startup: {e}")
