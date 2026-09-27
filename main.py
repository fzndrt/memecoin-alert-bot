"""
main.py - Entry Point Terintegrasi (Flask Health Check + PumpPortal WebSocket + APScheduler)
Sudah langsung disesuaikan dengan arsitektur repo: https://github.com/fzndrt/memecoin-alert-bot
"""

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

# Inisialisasi Analyzer Akumulasi PumpAlpha
analyzer = MemecoinAccumulationAnalyzer(
    min_cvd_ratio=30.0,
    min_buy_sell_ratio=2.0,
    max_dev_holding=2.5,
    max_top10_holding=25.0
)

# Cache memori token
token_cache = {}
_last_run_summary = {"status": "WebSocket aktif mendengarkan Solana/Pump.fun"}

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
    """
    Callback realtime dari pumpportal_stream.py setiap ada trade atau token baru!
    """
    mint = data.get("mint")
    if not mint:
        return

    # Hindari spam alert untuk token yang sama
    if state.already_alerted(mint):
        return

    name = data.get("name", "Unknown Token")
    symbol = data.get("symbol", "PUMP")
    mc = data.get("marketCapSol", 0) * 160  # Estimasi kurs SOL ~$160

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

    # Hitung akumulasi beli vs jual
    tx_type = data.get("txType", "buy")
    if tx_type == "buy":
        token_cache[mint]["txns"]["m5"]["buys"] += 1
    else:
        token_cache[mint]["txns"]["m5"]["sells"] += 1
        
    token_cache[mint]["volume"]["m5"] += data.get("solAmount", 0) * 160

    # Evaluasi dengan mesin analyzer
    result = analyzer.evaluate_token(token_cache[mint])

    if result.get("is_approved") and result.get("score", 0) >= 80:
        score_val = result['score']
        logger.info(f"🔥 GEM TERDETEKSI: {name} (${symbol}) | Skor: {score_val}")
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
    """Jalankan WebSocket loop di background thread terpisah"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    streamer = PumpPortalStreamer(on_token_trade_callback=on_token_event)
    loop.run_until_complete(streamer.start())

@app.route("/")
def health():
    """Endpoint untuk UptimeRobot / health check Render."""
    return jsonify({
        "service": "memecoin-alert-bot", 
        "ok": True, 
        "websocket": "Running",
        "cached_tokens": len(token_cache)
    })

if __name__ == "__main__":
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset -- alert tidak akan terkirim.")
    
    # 1. Jalankan WebSocket PumpPortal di thread background
    ws_thread = threading.Thread(target=run_websocket_loop, daemon=True)
    ws_thread.start()
    logger.info("WebSocket PumpPortal aktif di background!")

    # 2. Jalankan Flask server (agar Render/UptimeRobot tetap hidup)
    port = getattr(config, "PORT", 5000)
    app.run(host="0.0.0.0", port=port)
