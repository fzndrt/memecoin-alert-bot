"""
Konfigurasi aplikasi -- dibaca dari environment variables.
Untuk development lokal, buat file .env (lihat .env.example) dan
python-dotenv akan otomatis memuatnya.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_float(key: str, default: float) -> float:
    val = os.getenv(key)
    try:
        return float(val) if val is not None else default
    except ValueError:
        return default


def _get_int(key: str, default: int) -> int:
    val = os.getenv(key)
    try:
        return int(val) if val is not None else default
    except ValueError:
        return default


# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Polling ---
POLL_INTERVAL_MINUTES = _get_int("POLL_INTERVAL_MINUTES", 15)

# --- Chain yang dipantau (dipisah koma), contoh: solana,ethereum,bsc ---
CHAINS = [c.strip().lower() for c in os.getenv("CHAINS", "solana,ethereum,bsc").split(",") if c.strip()]

# --- Filter kriteria akumulasi ---
MIN_LIQUIDITY_USD = _get_float("MIN_LIQUIDITY_USD", 5000)
MIN_VOLUME_H1_USD = _get_float("MIN_VOLUME_H1_USD", 3000)
MIN_VOLUME_SPIKE_RATIO = _get_float("MIN_VOLUME_SPIKE_RATIO", 3.0)  # vol_h1 vs rata2 vol/jam 24h
MAX_PRICE_CHANGE_H24 = _get_float("MAX_PRICE_CHANGE_H24", 60.0)     # hindari koin yg SUDAH pump duluan
MIN_PRICE_CHANGE_H1 = _get_float("MIN_PRICE_CHANGE_H1", 1.0)
MAX_PRICE_CHANGE_H1 = _get_float("MAX_PRICE_CHANGE_H1", 50.0)
MIN_BUY_SELL_RATIO_H1 = _get_float("MIN_BUY_SELL_RATIO_H1", 1.3)

# --- Kekuatan narasi/identitas proyek (lihat narrative.py) ---
# Token harus mencapai skor narasi minimum ini untuk dialert -- ini yang
# membuat sistem MENITIKBERATKAN token dengan tujuan/identitas jelas &
# yang mulai dibicarakan, bukan sekadar token yang volumenya naik.
MIN_NARRATIVE_SCORE = _get_float("MIN_NARRATIVE_SCORE", 2.5)
# Jeda antar-request ke CoinGecko contract-lookup agar tidak kena rate limit
# publik (~10-30 req/menit) saat mengevaluasi banyak kandidat sekaligus.
CG_REQUEST_DELAY_SECONDS = _get_float("CG_REQUEST_DELAY_SECONDS", 1.5)

# --- Keamanan token (GoPlus) ---
ENABLE_SECURITY_CHECK = _get_bool("ENABLE_SECURITY_CHECK", True)
MAX_SELL_TAX_PCT = _get_float("MAX_SELL_TAX_PCT", 15.0)
MAX_BUY_TAX_PCT = _get_float("MAX_BUY_TAX_PCT", 15.0)

# --- Sosial media (opsional, umumnya butuh API berbayar) ---
ENABLE_TWITTER = _get_bool("ENABLE_TWITTER", False)
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")

# --- Anti-duplikat alert ---
ALERT_COOLDOWN_HOURS = _get_int("ALERT_COOLDOWN_HOURS", 24)
STATE_FILE = os.getenv("STATE_FILE", "alerted_tokens.json")

# --- Web server (untuk Render + UptimeRobot) ---
PORT = _get_int("PORT", 10000)
