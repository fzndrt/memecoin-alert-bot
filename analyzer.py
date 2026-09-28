"""
analyzer.py - Mesin Analisis Akumulasi & Anti-Bot PumpAlpha v3.0
Dilengkapi:
- Radar Koin Early Organik (Usia 15 - 60 Menit)
- Filter Wash Trading Berdasarkan Volume Velocity (Vol/Liq Cap)
- Anti-Sniper Bot War & Anti-Dump M5 Real-Time
- Verifikasi Konsentrasi Whale / Top Holder < 10.0%
"""
import math
from typing import Dict, Any, Tuple

class MemecoinAccumulationAnalyzer:
    def __init__(self, 
                 min_cvd_ratio: float = 25.0,
                 min_buy_sell_ratio: float = 1.35,
                 max_dev_holding: float = 3.0,
                 max_top_holder: float = 10.0,
                 min_age_minutes: float = 15.0,
                 max_age_minutes: float = 120.0):
        self.min_cvd_ratio = min_cvd_ratio
        self.min_buy_sell_ratio = min_buy_sell_ratio
        self.max_dev_holding = max_dev_holding
        self.max_top_holder = max_top_holder
        self.min_age_minutes = min_age_minutes
        self.max_age_minutes = max_age_minutes

    def calculate_cvd_delta(self, txns_m5: Dict[str, int], vol_m5: float) -> Tuple[float, float]:
        """
        Menghitung Cumulative Volume Delta (CVD) dari transaksi 5 menit terakhir.
        CVD Ratio = (Buys - Sells) / Total Txns * 100
        """
        buys = txns_m5.get("buys", 0)
        sells = txns_m5.get("sells", 0)
        total = buys + sells
        if total == 0:
            return 0.0, 0.0

        buy_ratio = buys / total
        cvd_ratio = (buy_ratio - (1.0 - buy_ratio)) * 100.0
        cvd_usd = vol_m5 * (buy_ratio - (1.0 - buy_ratio))
        return round(cvd_usd, 2), round(cvd_ratio, 1)

    def detect_wash_or_bot_trap(self, 
                                txns_m5: Dict[str, int], 
                                vol_m5: float, 
                                vol_h1: float, 
                                liquidity_usd: float,
                                unique_buyers: int) -> Tuple[bool, str]:
        """
        Mendeteksi Jebakan Bot Sniper & Volume Palsu:
        1. Volume Cuci Piring (M5 Vol > 3x Liq atau H1 Vol > 8x Liq)
        2. Perang Sniper Bot (> 600 transaksi dalam 5 menit di kolam kecil)
        3. Real-Time Dump (Sells > Buys di candle M5)
        4. Fake Volume (Unique Wallets terlalu sedikit)
        """
        buys = txns_m5.get("buys", 0)
        sells = txns_m5.get("sells", 0)
        total_m5 = buys + sells

        # 1. Pintu Anti-Wash Volume (Rasio Volume vs Kolam)
        if liquidity_usd > 0:
            if (vol_h1 / liquidity_usd) > 8.0:
                return True, f"Wash Trading H1 ({vol_h1/liquidity_usd:.1f}x Liq)"
            if (vol_m5 / liquidity_usd) > 3.0:
                return True, f"Wash Trading M5 ({vol_m5/liquidity_usd:.1f}x Liq)"

        # 2. Pintu Perang Bot Sniper
        if total_m5 > 600 and liquidity_usd < 50000:
            return True, "Sniper Bot War (> 600 txns M5 di Kolam Rendah)"

        # 3. Pintu Real-Time Dump M5 (Whale mulai jualan)
        if total_m5 >= 20 and sells > (buys * 1.1):
            return True, f"Sell Dump Dimulai ({sells} Sells > {buys} Buys)"

        # 4. Pintu Dompet Unik Rendah
        if total_m5 > 50 and unique_buyers < (total_m5 * 0.2):
            return True, "Volume Semu (Sedikit Dompet Mengulang Transaksi)"

        return False, "ORGANIC"

    def evaluate_token(self, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluasi Koin Early Multi-Lapisan
        """
        txns_m5 = token_data.get("txns", {}).get("m5", {"buys": 0, "sells": 0})
        vol_m5 = float(token_data.get("volume", {}).get("m5", 0.0))
        vol_h1 = float(token_data.get("volume", {}).get("h1", vol_m5 * 2.0))
        liquidity_usd = float(token_data.get("liquidity", {}).get("usd", 0.0) or 0.0)
        market_cap = float(token_data.get("marketCap", token_data.get("fdv", 0.0)) or 0.0)
        
        age_minutes = float(token_data.get("ageMinutes", 30.0))
        dev_holding = float(token_data.get("devHoldingPercent", 0.0))
        top_holder = float(token_data.get("topHolderPercent", 0.0))
        unique_buyers = int(token_data.get("uniqueBuyersCount", txns_m5.get("buys", 0)))

        # 1. Pintu Filter Usia Early (Gentoo masuk di sini!)
        reasons = []
        is_passed = True

        if age_minutes < self.min_age_minutes:
            is_passed = False
            reasons.append(f"Usia koin {age_minutes:.1f}m < minimal {self.min_age_minutes}m (Menghindari sniper detik pertama)")

        if age_minutes > self.max_age_minutes:
            is_passed = False
            reasons.append(f"Usia koin {age_minutes:.1f}m > maksimal {self.max_age_minutes}m (Bukan koin early)")

        # 2. Hitung CVD & Rasio Beli
        cvd_usd, cvd_ratio = self.calculate_cvd_delta(txns_m5, vol_m5)
        buys = txns_m5.get("buys", 0)
        sells = max(1, txns_m5.get("sells", 1))
        buy_sell_ratio = round(buys / sells, 2)

        # 3. Audit Perisai Anti-Bot & Wash Trading
        is_bot, bot_reason = self.detect_wash_or_bot_trap(
            txns_m5=txns_m5,
            vol_m5=vol_m5,
            vol_h1=vol_h1,
            liquidity_usd=liquidity_usd,
            unique_buyers=unique_buyers
        )
        if is_bot:
            is_passed = False
            reasons.append(f"Ditolak Bot Radar: {bot_reason}")

        # 4. Audit Konsentrasi Whale / Dev
        if top_holder > self.max_top_holder and top_holder < 90.0:
            is_passed = False
            reasons.append(f"Top Holder {top_holder:.1f}% menguasai > {self.max_top_holder}% suplai (Bahaya Dump)")

        if dev_holding > self.max_dev_holding:
            is_passed = False
            reasons.append(f"Dev Holding {dev_holding}% terlalu besar")

        if cvd_ratio < self.min_cvd_ratio:
            is_passed = False
            reasons.append(f"CVD Ratio {cvd_ratio}% di bawah minimal +{self.min_cvd_ratio}%")

        if buy_sell_ratio < self.min_buy_sell_ratio:
            is_passed = False
            reasons.append(f"Rasio Beli:Jual {buy_sell_ratio}x < {self.min_buy_sell_ratio}x")

        # 5. Skoring Dinamis (0 - 100)
        score = 50
        if cvd_ratio >= 40: score += 20
        elif cvd_ratio >= 25: score += 12

        if buy_sell_ratio >= 2.0: score += 15
        elif buy_sell_ratio >= 1.4: score += 10

        if top_holder <= 5.0 and top_holder > 0: score += 15

        if is_bot: score -= 50
        score = max(5, min(99, score))

        return {
            "is_approved": is_passed,
            "score": score,
            "age_minutes": age_minutes,
            "cvd_usd": cvd_usd,
            "cvd_ratio": cvd_ratio,
            "buy_sell_ratio": buy_sell_ratio,
            "top_holder_pct": top_holder,
            "is_wash_trading": is_bot,
            "reasons": reasons,
            "action": "EARLY_GEM_ENTRY" if is_passed and score >= 75 else "REJECTED"
        }
