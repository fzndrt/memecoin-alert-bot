"""
pumpportal_stream.py - Sub-Second Early Detection Engine (Solana / Pump.fun)
"""
import json
import asyncio
import logging
import websockets
from typing import Callable

logger = logging.getLogger("memecoin-alert-bot")
PUMPPORTAL_WS_URL = "wss://pumpportal.fun/api/data"

class PumpPortalStreamer:
    def __init__(self, on_token_trade_callback: Callable):
        self.callback = on_token_trade_callback
        self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info("[PumpAlpha] Menghubungkan ke WebSocket PumpPortal...")
        
        while self.is_running:
            try:
                async with websockets.connect(PUMPPORTAL_WS_URL, ping_interval=20, ping_timeout=20) as ws:
                    logger.info("[PumpAlpha] TERHUBUNG KE REAL-TIME STREAM SOLANA / PUMP.FUN!")
                    
                    # 1. Langganan koin baru diluncurkan
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    logger.info("[PumpAlpha] Berlangganan feed token baru aktif.")

                    # 2. Langganan transaksi trade langsung di bonding curve
                    await ws.send(json.dumps({"method": "subscribeAccountTrade", "keys": ["all"]}))
                    
                    while self.is_running:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        if self.callback:
                            await self.callback(data)
                            
            except Exception as e:
                logger.warning(f"[PumpAlpha] Koneksi WebSocket terputus: {e}. Reconnecting dalam 3 detik...")
                await asyncio.sleep(3)

    def stop(self):
        self.is_running = False
