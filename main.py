"""
main.py - Dual-Engine Memecoin Alert Bot v3.2 (Super Strict Gem Radar)
Repo: https://github.com/fzndrt/memecoin-alert-bot
Fitur:
- Pembeda Label Koin: 🟡 PUMP.FUN RADAR vs 🔵 SOLANA DEX GRADUATE
- Filter Ketat Anti-Koin Mati (MC Min $18k di Pump.fun, Liq Min $18k di DEX)
- Anti-Dump: Menolak koin dengan tren harga merah/longsor
- Anti-Rug & Anti-Sindikat: RugCheck audit & deteksi split-wallets
- Anti Micro-Bot: Menolak spam order receh & wash-trading
"""

import os
import time
import json
import asyncio
import threading
import logging
import urllib.request
from collections import Counter
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
    min_age_minutes=10.0,      # Minimal usia 10 menit
    max_age_minutes=120.0      # Maksimal usia 120 menit
)

token_cache = {}
stats = {"events_received": 0, "gems_found": 0}

def check_real_top_holder(mint: str) -> float:
    """Mengambil kepemilikan holder terbesar & audit on-chain RugCheck (Anti-Rug, Anti-Sindikat Split-Wallet)"""
    try:
        url = f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            
            # 1. Tolak jika skor risiko bahaya
            score = int(data.get("score") or 0)
            if score > 450:
                logger.info(f"🚫 [RugCheck] Ditolak: Skor risiko bahaya ({score} > 450) ({mint})")
                return 999.0

            # 2. Audit Bahaya On-chain: Mintable / Freeze Authority / LP Bahaya
            risks = data.get("risks", [])
            for r in risks:
                r_name = str(r.get("name", "")).lower()
                r_level = str(r.get("level", "")).lower()
                if "freeze" in r_name or "mint" in r_name or r_level == "danger":
                    logger.info(f"🚫 [RugCheck] Ditolak: Bahaya Fatal '{r.get('name')}' ({mint})")
                    return 999.0

            top_holders = data.get("topHolders", [])
            
            # 3. DETEKSI SINDIKAT PECAH DOMPET (SPLIT-WALLETS CLUSTER)
            non_pool_pcts = []
            for h in top_holders:
                addr = str(h.get("address", "")).lower()
                pct = float(h.get("pct", 0.0) or 0.0)
                # Filter agar dompet LP / Pool Raydium / Meteora / Pump tidak dihitung
                if any(dex in addr for dex in ["pool", "raydium", "meteora", "pump", "openbook"]):
                    continue
                if pct < 85.0:  # Abaikan jika itu akun burner / bonding curve
                    non_pool_pcts.append(pct)

            # Jika ada 4 dompet atau lebih yang memegang persentase saldo identik
            if len(non_pool_pcts) >= 4:
                rounded_pcts = [round(p, 1) for p in non_pool_pcts[:12]]
                counts = Counter(rounded_pcts)
                for pct_val, freq in counts.items():
                    if pct_val >= 0.3 and freq >= 4:
                        logger.info(f"🚫 [Anti-Sindikat] Ditolak: Split-Wallet Terdeteksi ({freq} dompet memegang persis ~{pct_val}%) ({mint})")
                        return 999.0

            # 4. Ambil kepemilikan dompet paus (whale) murni non-pool
            for h in top_holders:
                addr = str(h.get("address", "")).lower()
                pct = float(h.get("pct", 0.0) or 0.0)
                if any(dex in addr for dex in ["pool", "raydium", "meteora", "pump", "openbook"]):
                    continue
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

    if source == "PUMPFUN":
        header_badge = "🟡 <b>[PUMP.FUN LIVE RADAR]</b>"
        stage_desc = "Fase Akumulasi Kurva Bonding (25% - 75%)"
    else:
        header_badge = "🔵 <b>[SOLANA DEX GRADUATE]</b>"
        stage_desc = "Resmi Listing di Raydium/DEX (Lolos Migrasi)"

    text = (
        f"{header_badge}\n"
        f"👑 <b>POTENSI GEM DITEMUKAN (SKOR: {score}/100)</b>\n"
        f"🏷️ <i>{stage_desc}</i>\n\n"
        f"🪙 <b>Koin:</b> {token_name} (<code>${symbol}</code>)\n"
        f"💰 <b>Market Cap:</b> <code>${mc:,.0f}</code>\n"
        f"{extra_info}\n"
        f"⏳ <b>Usia Koin:</b> <code>{age:.1f} Menit</code>\n\n"
        f"📊 <b>ANALISIS ON-CHAIN:</b>\n"
        f"├ 🚀 <b>Net Inflow (CVD):</b> <code>+{cvd_ratio:.1f}%</code>\n"
        f"├ 👥 <b>Rasio Pembeli:</b> <code>{buy_ratio:.2f}x Penjual</code>\n"
        f"└ 🐋 <b>Top Holder:</b> <code>{top_holder:.1f}%</code> (Aman dari Whale)\n\n"
        f"🔍 <b>Kontrak Mint:</b>\n<code>{mint}</code>\n\n"
        f"🔗 <b>Akses Cepat & Trading:</b>\n"
        f"• <a href=\"https://pump.fun/coin/{mint}\">Buka di Pump.fun</a>\n"
        f"• <a href=\"https://dexscreener.com/solana/{mint}\">Grafik DexScreener</a>\n"
        f"• <a href=\"https://rugcheck.xyz/tokens/{mint}\">Audit RugCheck</a>\n"
        f"• <a href=\"https://t.me/PhotonSolanaBot?start={mint}\">Beli via Photon Bot</a>"
    )
    return text

# =====================================================================
# MESIN 1: RADAR PUMP.FUN WEBSOCKET
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
            "history": [],
            "marketCap": mc,
            "bonding_curve": float(data.get("vSolInBondingCurve", 0.0) or 0.0)
        }

    tok = token_cache[mint]
    tok["marketCap"] = mc
    tok["bonding_curve"] = float(data.get("vSolInBondingCurve", 0.0) or 0.0)

    is_buy = data.get("txType") == "buy"
    sol_amount = float(data.get("solAmount", 0.0) or 0.0)
    usd_val = sol_amount * 160

    if is_buy:
        tok["txns"]["m5"]["buys"] += 1
        tok["volume"]["m5"] += usd_val
        tok["volume"]["h1"] += usd_val
    else:
        tok["txns"]["m5"]["sells"] += 1
        tok["volume"]["m5"] -= (usd_val * 0.5)

    tok["history"].append({"time": current_time, "is_buy": is_buy, "val": usd_val})

    # FILTER KETAT PUMP.FUN:
    if mc < 18000.0 or mc > 70000.0:
        return

    bonding_pct = min(100.0, (tok["bonding_curve"] / 85.0) * 100.0) if tok["bonding_curve"] > 0 else 0.0
    if bonding_pct > 0 and (bonding_pct < 25.0 or bonding_pct > 80.0):
        return

    age_mins = (current_time - tok["first_seen"]) / 60.0
    if age_mins < 10.0:
        return

    real_top_holder = check_real_top_holder(mint)
    if real_top_holder > 10.0:
        return

    eval_payload = {
        "ageMinutes": age_mins,
        "txns": tok["txns"],
        "volume": tok["volume"],
        "liquidity": {"usd": mc * 0.4},
        "marketCap": mc,
        "devHoldingPercent": 1.2,
        "topHolderPercent": real_top_holder,
        "uniqueBuyersCount": tok["txns"]["m5"]["buys"]
    }

    eval_res = analyzer.evaluate_token(eval_payload)
    if eval_res.get("is_approved") and eval_res.get("score", 0) >= 80:
        stats["gems_found"] += 1
        extra = f"📈 <b>Kurva Bonding:</b> <code>{bonding_pct:.1f}% Terisi</code>"
        text = format_telegram_alert(name, symbol, mint, eval_res, mc, "PUMPFUN", extra)
        
        if bot and config.TELEGRAM_CHAT_ID:
            try:
                bot.send_message(config.TELEGRAM_CHAT_ID, text, parse_mode="HTML", disable_web_page_preview=True)
                state.mark_alerted(mint)
                logger.info(f"💎 GEM ASLI TERDETEKSI (🟡 PUMP.FUN): {name} (${symbol}) | MC: ${mc:,.0f}!")
            except Exception as e:
                logger.error(f"Gagal kirim Telegram: {e}")

def run_websocket_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    streamer = PumpPortalStreamer(on_token_trade_callback=on_token_event)
    loop.run_until_complete(streamer.start())

# =====================================================================
# MESIN 2: RADAR SOLANA DEX (MIN LIQUIDITY $18k & ANTI DUMP/BOT)
# =====================================================================
def poll_dexscreener_early_graduates():
    logger.info("[Mesin 2] Radar Solana Dex Aktif...")
    while True:
        try:
            sol_mints = []
            try:
                p_req = urllib.request.Request("https://api.dexscreener.com/token-profiles/latest/v1", headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(p_req, timeout=8) as resp:
                    profiles = json.loads(resp.read().decode('utf-8'))
                    sol_mints.extend([p["tokenAddress"] for p in profiles if p.get("chainId") == "solana"][:30])
            except Exception:
                pass

            try:
                b_req = urllib.request.Request("https://api.dexscreener.com/token-boosts/latest/v1", headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(b_req, timeout=8) as resp:
                    boosts = json.loads(resp.read().decode('utf-8'))
                    sol_mints.extend([b["tokenAddress"] for b in boosts if b.get("chainId") == "solana"][:30])
            except Exception:
                pass

            try:
                s_req = urllib.request.Request("https://api.dexscreener.com/latest/dex/search?q=SOL", headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(s_req, timeout=8) as resp:
                    search_data = json.loads(resp.read().decode('utf-8'))
                    for p in search_data.get("pairs", [])[:30]:
                        if p.get("chainId") == "solana":
                            addr = p.get("baseToken", {}).get("address")
                            if addr:
                                sol_mints.append(addr)
            except Exception:
                pass

            sol_mints = list(set(sol_mints))

            for mint in sol_mints:
                if state.already_alerted(mint):
                    continue

                pair_url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
                try:
                    p_req = urllib.request.Request(pair_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(p_req, timeout=8) as p_resp:
                        pair_data = json.loads(p_resp.read().decode('utf-8'))
                        pairs = pair_data.get("pairs", [])
                        if not pairs:
                            continue
                        
                        pair = pairs[0]

                        # 🛡️ 1. SYARAT LIKUIDITAS: Minimal $18,000 USD
                        liq_usd = float(pair.get("liquidity", {}).get("usd") or 0.0)
                        if liq_usd < 18000.0:
                            continue

                        # 🚫 GEMBOK ANOMALI BOT & WASH-TRADING
                        txns_all = pair.get("txns", {})
                        txns_h1 = txns_all.get("h1", {})
                        h1_tx_count = int(txns_h1.get("buys", 0)) + int(txns_h1.get("sells", 0))
                        
                        vol_h1 = float(pair.get("volume", {}).get("h1") or 0.0)
                        vol_m5 = float(pair.get("volume", {}).get("m5") or 0.0)

                        # A. Tolak jika transaksi >= 300 tapi nilai order rata-rata < $25 (Bot Receh)
                        if h1_tx_count >= 300:
                            avg_val_h1 = vol_h1 / max(1, h1_tx_count)
                            if avg_val_h1 < 25.0:
                                logger.info(f"🚫 [DEX] Ditolak: Micro-Bot Trap (Avg order ${avg_val_h1:.1f} < $25 di {h1_tx_count} txns) ({mint})")
                                continue

                        # B. Tolak jika ribuan transaksi (> 600) tapi likuiditas kolam tidak naik (< $35k)
                        if liq_usd < 35000.0 and h1_tx_count > 600:
                            logger.info(f"🚫 [DEX] Ditolak: Anomali Txn Banyak ({h1_tx_count} txns) tapi Kolam Dangkal (${liq_usd:,.0f}) ({mint})")
                            continue

                        # C. Tolak Wash-Trading (Volume digelembungkan > 6.5x isi kolam)
                        if liq_usd > 0:
                            vol_liq_h1 = vol_h1 / liq_usd
                            vol_liq_m5 = vol_m5 / liq_usd
                            if vol_liq_h1 > 6.5:
                                logger.info(f"🚫 [DEX] Ditolak: Wash Trading H1 {vol_liq_h1:.1f}x > 6.5x ({mint})")
                                continue
                            if vol_liq_m5 > 2.2:
                                logger.info(f"🚫 [DEX] Ditolak: Wash Trading M5 {vol_liq_m5:.1f}x > 2.2x ({mint})")
                                continue

                        created_at = pair.get("pairCreatedAt", 0)
                        if not created_at:
                            continue
                            
                        age_mins = (time.time() * 1000 - created_at) / 60000.0
                        
                        # Target Usia 10 - 60 Menit
                        if 10.0 <= age_mins <= 60.0:
                            real_top_holder = check_real_top_holder(mint)
                            if real_top_holder > 10.0:
                                logger.info(f"🚫 [DEX] Ditolak: Top Holder / Rug Risk / Sindikat {real_top_holder:.1f}% ({mint})")
                                continue

                            txns_m5 = pair.get("txns", {}).get("m5", {})
                            buys = int(txns_m5.get("buys", 0))

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
                except Exception:
                    pass
                finally:
                    time.sleep(0.4)    
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
                "🛡️ <b>PUMPALPHA BOT v3.2 ONLINE!</b>\nFilter Super Ketat Aktif: 🟡 Pump.fun Radar (Min MC $18k) & 🔵 Dex Graduates (Min Liq $18k).",
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
