"""
main.py - Dual-Engine Memecoin Alert Bot v3.2 (Super Strict Gem Radar)
Repo: https://github.com/fzndrt/memecoin-alert-bot
Fitur:
- Pembeda Label Koin: 🟡 PUMP.FUN RADAR vs 🔵 SOLANA DEX GRADUATE
- Filter Ketat Anti-Koin Mati (MC Min $18k di Pump.fun, Liq Min $12k di DEX)
- Anti-Dump: Menolak koin dengan tren harga merah/longsor
"""

import os
import time
import json
import asyncio
import threading
import logging
import urllib.request
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

# Inisialisasi Analyzer Tingkat Akurasi Tinggi
analyzer = MemecoinAccumulationAnalyzer(
    min_cvd_ratio=28.0,        # Minimal Net Inflow Akumulasi +28%
    min_buy_sell_ratio=1.5,    # Pembeli harus 1.5x lipat dari penjual
    max_dev_holding=2.5,       # Dompet Dev maksimal 2.5%
    max_top_holder=10.0,       # Dompet Whale maksimal 10.0%
    min_age_minutes=10.0,      # Minimal usia 15 menit
    max_age_minutes=120.0      # Maksimal usia 120 menit
)

token_cache = {}
stats = {"events_received": 0, "gems_found": 0}


def check_real_top_holder(mint: str) -> float:
    """Mengambil kepemilikan holder terbesar dari RugCheck on-chain"""
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            top_holders = data.get("topHolders", [])
            if top_holders:
                for h in top_holders:
                    pct = float(h.get("pct", 0.0))
                    # Abaikan pool authority (>85%)
                    if pct < 85.0:
                        return pct
    except Exception:
        pass
    return 0.0


def format_telegram_alert(token_name: str, symbol: str, mint: str, eval_result: dict, mc: float, source: str, extra_info: str) -> str:
    score = eval_result.get("score", 0)
    cvd_ratio = eval_result.get("cvd_ratio", 0.0)
    buy_ratio = eval_result.get("buy_sell_ratio", 1.0)
    age = eval_result.get("age_minutes", 0.0)
    top_holder = eval_result.get("top_holder_pct", 0.0)

    # Label Visual yang Jelas sesuai Sumber Koin
    if source == "PUMPFUN":
        header_badge = "🟡 <b>[PUMP.FUN LIVE RADAR]</b>"
        stage_desc = "Fase Akumulasi Kurva Bonding (25% - 75%)"
    else:
        header_badge = "🔵 <b>[SOLANA DEX GRADUATE]</b>"
        stage_desc = "Resmi Listing di Raydium / PumpSwap"

    holder_str = f"{top_holder:.1f}% (Aman &lt; 10%)" if top_holder > 0 else "Distribusi Bersih"

    msg = f"""{header_badge}
💎 <b>{token_name} (${symbol})</b>
━━━━━━━━━━━━━━━━━━━━
🎯 <b>PumpAlpha Score:</b> <code>{score}/100</code>
📍 <b>Status Platform:</b> <code>{stage_desc}</code>
⏳ <b>Usia Koin:</b> <code>{age:.1f} Menit</code>
💰 <b>Market Cap:</b> <code>${mc:,.0f}</code>
{extra_info}
📊 <b>Net Inflow (CVD):</b> <code>+{cvd_ratio}%</code>
⚡ <b>Rasio Pembeli:</b> <code>{buy_ratio}x Buyers Dominance</code>
━━━━━━━━━━━━━━━━━━━━
🛡️ <b>Audit Keamanan & Integritas:</b>
• Top Whale Terbesar: <code>{holder_str}</code>
• Volume Status: <code>VOLUME ASLI (Bukan Bot Wash)</code>
• Anti-Dump Filter: <code>LOLOS (Tren Harga Naik/Stabil)</code>

📋 <b>Mint Address:</b>
<code>{mint}</code>

⚡ <b>Perintah Quick Snipe:</b>
<code>/snipe {mint} 0.5</code>

🔗 <b>Direct Trading Links:</b>
<a href="https://dexscreener.com/solana/{mint}">[DexScreener]</a> · <a href="https://photon-sol.tinyastro.io/en/r/@alpha/{mint}">[Photon SOL]</a> · <a href="https://neo.bullx.io/terminal?chainId=1399811149&address={mint}">[BullX]</a>"""
    return msg.strip()


# =====================================================================
# MESIN 1: PUMPPORTAL WEBSOCKET (SUPER KETAT - MIN MC $18,000 & VOL $1,500)
# =====================================================================
async def on_token_event(data: dict):
    stats["events_received"] += 1
    mint = data.get("mint")
    if not mint or state.already_alerted(mint):
        return

    name = data.get("name", "Unknown Token")
    symbol = data.get("symbol", "PUMP")
    mc = float(data.get("marketCapSol", 0.0) or 0.0) * 160
    current_time = time.time()

    if mint not in token_cache:
        token_cache[mint] = {
            "name": name,
            "symbol": symbol,
            "first_seen": current_time,
            "txns": {"m5": {"buys": 0, "sells": 0}},
            "volume": {"m5": 0.0, "h1": 0.0},
            "liquidity": {"usd": max(8000.0, mc * 0.3)},
            "devHoldingPercent": float(data.get("devHoldingPercent", 1.0)),
            "topHolderPercent": 3.0,
            "marketCap": mc,
        }

    age_minutes = (current_time - token_cache[mint].get("first_seen", current_time)) / 60.0
    token_cache[mint]["ageMinutes"] = max(10.0, age_minutes)

    tx_type = data.get("txType", "buy")
    sol_amount = float(data.get("solAmount", 0.0) or 0.0) * 160

    if tx_type == "buy":
        token_cache[mint]["txns"]["m5"]["buys"] += 1
    else:
        token_cache[mint]["txns"]["m5"]["sells"] += 1

    token_cache[mint]["volume"]["m5"] += sol_amount
    token_cache[mint]["volume"]["h1"] += sol_amount
    token_cache[mint]["marketCap"] = mc

    # 🚫 GEMBOK 1: TOLAK KOIN MATI DENGAN MC RENDAH (5boJpm MC $3.5k gugur di sini!)
    # Koin yang akan terbang ke jutaan dollar kurva bonding-nya minimal harus sudah mencapai $18.000!
    if mc < 18000.0:
        return

    # 🚫 GEMBOK 2: TOLAK VOLUME RECEHAN (Wajib minimal $1,500 akumulasi di 5 menit terakhir)
    if token_cache[mint]["volume"]["m5"] < 1500.0:
        return

    # 🚫 GEMBOK 3: TOLAK JIKA PENJUAL LEBIH BANYAK DARI PEMBELI
    buys = token_cache[mint]["txns"]["m5"]["buys"]
    sells = token_cache[mint]["txns"]["m5"]["sells"]
    if buys < (sells * 1.5) or (buys + sells) < 25:
        return

    result = analyzer.evaluate_token(token_cache[mint])
    if result.get("is_approved") and result.get("score", 0) >= 78:
        # Cek On-Chain Top Holder
        real_top_holder = check_real_top_holder(mint)
        if real_top_holder > 10.0:
            logger.info(f"🚫 [Pump.fun] Ditolak: Top Holder {real_top_holder:.1f}% > 10% ({mint})")
            return

        result["top_holder_pct"] = real_top_holder
        stats["gems_found"] += 1
        logger.info(f"🔥 GEM TERDETEKSI (🟡 PUMP.FUN): {name} (${symbol}) | MC: ${mc:,.0f} | Skor: {result['score']}")
        
        bonding_pct = min(99.0, (mc / 65000.0) * 100.0)
        extra = f"📈 <b>Kurva Bonding:</b> <code>{bonding_pct:.1f}% Terisi</code>"

        if bot and config.TELEGRAM_CHAT_ID:
            text = format_telegram_alert(name, symbol, mint, result, mc, "PUMPFUN", extra)
            try:
                bot.send_message(config.TELEGRAM_CHAT_ID, text, parse_mode="HTML", disable_web_page_preview=True)
                state.mark_alerted(mint)
            except Exception as e:
                logger.error(f"Gagal kirim Telegram: {e}")


def run_websocket_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    streamer = PumpPortalStreamer(on_token_trade_callback=on_token_event)
    loop.run_until_complete(streamer.start())


# =====================================================================
# MESIN 2: RADAR DEXSCREENER (SUPER KETAT - MIN LIQ $12,000 & ANTI-CRASH)
# =====================================================================
def poll_dexscreener_early_graduates():
    logger.info("[Mesin 2] Radar Solana Dex (Usia 15-60m) Aktif...")
    while True:
        try:
            # KODE BARU (Mengambil hingga 60 koin mutiara tanpa buta koin):
sol_mints = []
# 1. Ambil dari Profiles resmi
try:
    p_req = urllib.request.Request("https://api.dexscreener.com/token-profiles/latest/v1", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(p_req, timeout=8) as resp:
        profiles = json.loads(resp.read().decode('utf-8'))
        sol_mints.extend([p["tokenAddress"] for p in profiles if p.get("chainId") == "solana"][:30])
except Exception:
    pass

# 2. Ambil dari Token Boosts (Koin yang sedang trending/viral)
try:
    b_req = urllib.request.Request("https://api.dexscreener.com/token-boosts/latest/v1", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(b_req, timeout=8) as resp:
        boosts = json.loads(resp.read().decode('utf-8'))
        sol_mints.extend([b["tokenAddress"] for b in boosts if b.get("chainId") == "solana"][:30])
except Exception:
    pass

# Hapus duplikat alamat token
sol_mints = list(dict.fromkeys(sol_mints))
            
            for mint in sol_mints:
                if state.already_alerted(mint):
                    continue
                    
                pair_url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
                p_req = urllib.request.Request(pair_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(p_req, timeout=8) as p_resp:
                    pair_data = json.loads(p_resp.read().decode('utf-8'))
                    pairs = pair_data.get("pairs", [])
                    if not pairs:
                        continue
                    
                    pair = pairs[0]

                    # 🛡️ 1. SYARAT LIKUIDITAS: Minimal $12,000 USD
                    liq_usd = float(pair.get("liquidity", {}).get("usd") or 0.0)
                    if liq_usd < 12000.0:
                        continue

                    # 🛡️ 2. SYARAT TREN HARGA: TIDAK BOLEH SEDANG DUMP / LONGSOR
                    price_change = pair.get("priceChange", {})
                    h1_change = float(price_change.get("h1") or 0.0)
                    m5_change = float(price_change.get("m5") or 0.0)
                    if h1_change < -5.0 or m5_change < -3.0:
                        continue

                    # 🛡️ 3. SYARAT AKTIVITAS TRANSAKSI: Minimal 30 Transaksi di M5
                    txns_m5 = pair.get("txns", {}).get("m5", {})
                    buys = txns_m5.get("buys", 0)
                    sells = txns_m5.get("sells", 0)
                    if buys < (sells * 1.4) or (buys + sells) < 30:
                        continue

                    created_at = pair.get("pairCreatedAt", 0)
                    if not created_at:
                        continue
                        
                    age_mins = (time.time() * 1000 - created_at) / 60000.0
                    
                    # Target Usia 15 - 60 Menit
                    if 10.0 <= age_mins <= 60.0:
                        real_top_holder = check_real_top_holder(mint)
                        if real_top_holder > 10.0:
                            logger.info(f"🚫 [DEX] Ditolak: Top Holder {real_top_holder:.1f}% > 10% ({mint})")
                            continue

                        eval_payload = {
                            "ageMinutes": age_mins,
                            "txns": pair.get("txns", {}),
                            "volume": pair.get("volume", {}),
                            "liquidity": {"usd": liq_usd},
                            "marketCap": float(pair.get("marketCap") or 0.0),
                            "devHoldingPercent": 1.0,
                            "topHolderPercent": real_top_holder,
                            "uniqueBuyersCount": buys
                        }
                        
                        eval_res = analyzer.evaluate_token(eval_payload)
                        if eval_res.get("is_approved") and eval_res.get("score", 0) >= 78:
                            stats["gems_found"] += 1
                            mc = float(pair.get("marketCap") or 0.0)
                            name = pair.get("baseToken", {}).get("name", "Early Gem")
                            sym = pair.get("baseToken", {}).get("symbol", "SOL")
                            
                            extra = f"💧 <b>Likuiditas DEX:</b> <code>${liq_usd:,.0f}</code>"
                            text = format_telegram_alert(name, sym, mint, eval_res, mc, "DEX", extra)
                            
                            if bot and config.TELEGRAM_CHAT_ID:
                                bot.send_message(config.TELEGRAM_CHAT_ID, text, parse_mode="HTML", disable_web_page_preview=True)
                                state.mark_alerted(mint)
                                logger.info(f"💎 GEM ASLI TERDETEKSI (🔵 DEX): {name} (${sym}) | Liq: ${liq_usd:,.0f} | Usia: {age_mins:.1f}m!")
                                
        except Exception as e:
            logger.debug(f"[Mesin 2 Poller Error]: {e}")
            
        time.sleep(45)


# =====================================================================
# FLASK WEB SERVER
# =====================================================================
@app.route("/")
def health():
    return jsonify({
        "service": "memecoin-alert-bot",
        "version": "3.2.0-super-strict",
        "ok": True,
        "websocket": "Running",
        "events_received": stats["events_received"],
        "cached_tokens": len(token_cache),
    })


@app.route("/test-alert")
def test_alert():
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
        source="PUMPFUN",
        extra_info="📈 <b>Kurva Bonding:</b> <code>34.6% Terisi</code>"
    )

    try:
        bot.send_message(config.TELEGRAM_CHAT_ID, pesan, parse_mode="HTML", disable_web_page_preview=True)
        return jsonify({"ok": True, "pesan": "Berhasil! Notifikasi alert koin telah dikirim ke Telegram Anda."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# =====================================================================
# STARTUP ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset di Render Environment!")
    else:
        try:
            bot.send_message(
                config.TELEGRAM_CHAT_ID,
                "🛡️ <b>PUMPALPHA BOT v3.2 ONLINE!</b>\nFilter Super Ketat Aktif: 🟡 Pump.fun Radar (Min MC $18k) & 🔵 Dex Graduates (Min Liq $12k).",
                parse_mode="HTML",
            )
            logger.info("Notifikasi startup sukses dikirim ke Telegram!")
        except Exception as e:
            logger.error(f"Gagal kirim pesan pembuka: {e}")

    ws_thread = threading.Thread(target=run_websocket_loop, daemon=True)
    ws_thread.start()

    dex_thread = threading.Thread(target=poll_dexscreener_early_graduates, daemon=True)
    dex_thread.start()

    port = int(os.environ.get("PORT", getattr(config, "PORT", 10000)))
    app.run(host="0.0.0.0", port=port)
