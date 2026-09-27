"""
analyzer.py - Mesin Analisis Akumulasi & Sentimen PumpAlpha v2.0
Menggantikan analisis volume lama dengan Cumulative Volume Delta (CVD),
Rasio Pembeli Unik, dan Audit Dev Supply < 2.5%
"""

import math
from typing import Dict, Any, Tuple

class MemecoinAccumulationAnalyzer:
    def __init__(self, 
                 min_cvd_ratio: float = 30.0,
                 min_buy_sell_ratio: float = 2.0,
                 max_dev_holding: float = 3.0,
                 max_top10_holding: float = 25.0):
        self.min_cvd_ratio = min_cvd_ratio
        self.min_buy_sell_ratio = min_buy_sell_ratio
        self.max_dev_holding = max_dev_holding
        self.max_top10_holding = max_top10_holding

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

    def detect_wash_trading(self, txns_m5: Dict[str, int], vol_m5: float, unique_buyers: int) -> bool:
        """
        Deteksi Wash Trading: Jika transaksi sangat tinggi tapi rasio beli:jual persis 50:50,
        atau unique buyers sangat rendah dibandingkan total transaksi.
        """
        buys = txns_m5.get("buys", 0)
        sells = txns_m5.get("sells", 0)
        total = buys + sells

        if total > 50:
            ratio = buys / max(1, sells)
            # Jika rasio berada di antara 0.95 dan 1.05 pada volume besar -> indikasi wash bot
            if 0.95 <= ratio <= 1.05 and unique_buyers < (total * 0.2):
                return True
        return False

    def evaluate_token(self, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluasi multi-faktor untuk sinyal Early Snipe (9000% Gem Filter)
        """
        txns_m5 = token_data.get("txns", {}).get("m5", {"buys": 0, "sells": 0})
        vol_m5 = token_data.get("volume", {}).get("m5", 0.0)
        market_cap = token_data.get("marketCap", token_data.get("fdv", 0.0))
        dev_holding = token_data.get("devHoldingPercent", 0.0)
        top10_holding = token_data.get("top10HoldersPercent", 0.0)
        unique_buyers = token_data.get("uniqueBuyersCount", txns_m5.get("buys", 0))

        # 1. Hitung CVD
        cvd_usd, cvd_ratio = self.calculate_cvd_delta(txns_m5, vol_m5)

        # 2. Hitung rasio beli / jual
        buys = txns_m5.get("buys", 0)
        sells = max(1, txns_m5.get("sells", 1))
        buy_sell_ratio = round(buys / sells, 2)

        # 3. Cek wash trading
        is_wash = self.detect_wash_trading(txns_m5, vol_m5, unique_buyers)

        # 4. Kriteria Kelulusan Sinyal Akumulasi
        reasons = []
        is_passed = True

        if cvd_ratio < self.min_cvd_ratio:
            is_passed = False
            reasons.append(f"CVD Ratio {cvd_ratio}% di bawah minimal +{self.min_cvd_ratio}%")

        if buy_sell_ratio < self.min_buy_sell_ratio:
            is_passed = False
            reasons.append(f"Rasio Beli:Jual {buy_sell_ratio}x di bawah minimal {self.min_buy_sell_ratio}x")

        if dev_holding > self.max_dev_holding:
            is_passed = False
            reasons.append(f"Dev holding {dev_holding}% terlalu beresiko (max {self.max_dev_holding}%)")

        if top10_holding > self.max_top10_holding:
            is_passed = False
            reasons.append(f"Top 10 memegang {top10_holding}% (konsentrasi whale berbahaya)")

        if is_wash:
            is_passed = False
            reasons.append("Pola wash-trading terdeteksi")

        # Skor 0 - 100
        score = 50
        if cvd_ratio >= 40: score += 20
        if buy_sell_ratio >= 2.5: score += 15
        if dev_holding <= 2.0: score += 15
        if is_wash: score -= 40

        score = max(5, min(99, score))

        return {
            "is_approved": is_passed,
            "score": score,
            "cvd_usd": cvd_usd,
            "cvd_ratio": cvd_ratio,
            "buy_sell_ratio": buy_sell_ratio,
            "is_wash_trading": is_wash,
            "reasons": reasons,
            "action": "SNIPE_ENTRY" if is_passed and score >= 75 else "SKIP"
        }
