"""
data_sources/pumpportal_stream.py - Sub-Second Early Detection Engine
Menggantikan polling DexScreener yang lambat dengan WebSocket langsung dari PumpPortal/Solana
Menangkap koin saat bonding curve masih 20% - 60% ($15K - $40K MC) seperti kasus $WODL
"""

import json
import asyncio
import websockets
from typing import Callable

PUMPPORTAL_WS_URL = "wss://pumpportal.fun/api/data"

class PumpPortalStreamer:
    def __init__(self, on_token_trade_callback: Callable):
        self.callback = on_token_trade_callback
        self.is_running = False

    async def start(self):
        self.is_running = True
        print("[PumpAlpha] Menghubungkan ke WebSocket PumpPortal...")
        
        while self.is_running:
            try:
                async with websockets.connect(PUMPPORTAL_WS_URL) as ws:
                    print("[PumpAlpha] Terhubung ke real-time stream Solana/Pump.fun!")
                    
                    # Berlangganan koin baru dan transaksi whale > 1 SOL
                    payload = {
                        "method": "subscribeNewToken"
                    }
                    await ws.send(json.dumps(payload))
                    
                    while self.is_running:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        await self.callback(data)
                        
            except Exception as e:
                print(f"[PumpAlpha] Koneksi terputus: {e}. Reconnecting dalam 3 detik...")
                await asyncio.sleep(3)

    def stop(self):
        self.is_running = False
