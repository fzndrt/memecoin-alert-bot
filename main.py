"""
Entry point aplikasi.

Menjalankan:
1. Flask web server kecil dengan endpoint "/" untuk health check
   (dipakai UptimeRobot agar Render Web Service tidak "tidur").
2. APScheduler background job yang secara berkala menjalankan pipeline
   deteksi akumulasi narasi/volume dan mengirim alert Telegram.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify

import config
import state
from analyzer import find_accumulation_candidates
from telegram_alert import send_alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("memecoin-alert-bot")

app = Flask(__name__)

_last_run_summary = {"status": "belum pernah dijalankan"}


def run_pipeline():
    global _last_run_summary
    logger.info("Menjalankan pipeline deteksi akumulasi...")
    try:
        candidates = find_accumulation_candidates()
        sent = 0
        for pair in candidates:
            address = (pair.get("baseToken") or {}).get("address", "")
            if not address or state.already_alerted(address):
                continue
            if send_alert(pair):
                state.mark_alerted(address)
                sent += 1
        _last_run_summary = {
            "status": "ok",
            "kandidat_ditemukan": len(candidates),
            "alert_terkirim": sent,
        }
        logger.info(f"Selesai: {len(candidates)} kandidat, {sent} alert terkirim.")
    except Exception as e:
        logger.exception("Pipeline gagal")
        _last_run_summary = {"status": "error", "detail": str(e)}


@app.route("/")
def health():
    """Endpoint untuk UptimeRobot / health check Render."""
    return jsonify({"service": "memecoin-alert-bot", "ok": True, "last_run": _last_run_summary})


@app.route("/run-now")
def run_now():
    """Trigger manual (opsional) untuk testing tanpa menunggu jadwal scheduler."""
    run_pipeline()
    return jsonify(_last_run_summary)


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_pipeline, "interval", minutes=config.POLL_INTERVAL_MINUTES)
    scheduler.start()
    logger.info(f"Scheduler aktif, polling setiap {config.POLL_INTERVAL_MINUTES} menit.")


if __name__ == "__main__":
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diset -- alert tidak akan terkirim.")

    run_pipeline()  # jalankan sekali saat start agar langsung ada aktivitas
    start_scheduler()
    app.run(host="0.0.0.0", port=config.PORT)
