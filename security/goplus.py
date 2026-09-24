"""
Pengecekan keamanan token dasar via GoPlus Security API (gratis, tanpa key
untuk pemakaian wajar). Ini BUKAN jaminan token aman -- hanya heuristik
tambahan untuk menyaring honeypot/kontrak berisiko tinggi yang jelas.
Selalu lakukan verifikasi manual sebelum bertransaksi.
"""
import requests
from typing import Dict, Any, Optional

TIMEOUT = 15

# Mapping chainId DexScreener -> chain_id numerik GoPlus (EVM chains)
_EVM_CHAIN_MAP = {
    "ethereum": "1",
    "bsc": "56",
    "polygon": "137",
    "arbitrum": "42161",
    "base": "8453",
    "avalanche": "43114",
    "optimism": "10",
}


def check_token_security(chain_id: str, token_address: str) -> Optional[Dict[str, Any]]:
    chain_id = (chain_id or "").lower()
    try:
        if chain_id == "solana":
            url = "https://api.gopluslabs.io/api/v1/solana/token_security"
        elif chain_id in _EVM_CHAIN_MAP:
            url = f"https://api.gopluslabs.io/api/v1/token_security/{_EVM_CHAIN_MAP[chain_id]}"
        else:
            return None  # chain belum didukung pengecekan keamanan

        resp = requests.get(url, params={"contract_addresses": token_address}, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        result = data.get("result", {})
        return result.get(token_address.lower()) or next(iter(result.values()), None)
    except requests.RequestException as e:
        print(f"[goplus] request gagal: {e}")
        return None


def is_token_safe_enough(security_info: Optional[Dict[str, Any]], max_buy_tax: float, max_sell_tax: float) -> bool:
    """Jika data keamanan tidak tersedia, token TIDAK otomatis ditolak --
    hanya dianggap 'tidak terverifikasi' (ditampilkan di pesan alert)."""
    if not security_info:
        return True

    if str(security_info.get("is_honeypot", "0")) == "1":
        return False
    if str(security_info.get("cannot_sell_all", "0")) == "1":
        return False

    try:
        buy_tax = float(security_info.get("buy_tax", 0) or 0) * 100
        sell_tax = float(security_info.get("sell_tax", 0) or 0) * 100
    except (TypeError, ValueError):
        buy_tax = sell_tax = 0

    if buy_tax > max_buy_tax or sell_tax > max_sell_tax:
        return False

    return True


def summarize_security(security_info: Optional[Dict[str, Any]]) -> str:
    if not security_info:
        return "tidak terverifikasi"
    flags = []
    if str(security_info.get("is_honeypot", "0")) == "1":
        flags.append("HONEYPOT")
    if str(security_info.get("is_open_source", "1")) == "0":
        flags.append("kontrak tertutup")
    if str(security_info.get("is_mintable", "0")) == "1":
        flags.append("mintable")
    try:
        sell_tax = float(security_info.get("sell_tax", 0) or 0) * 100
        if sell_tax > 0:
            flags.append(f"sell tax {sell_tax:.1f}%")
    except (TypeError, ValueError):
        pass
    return ", ".join(flags) if flags else "tidak ada red flag mencolok"
