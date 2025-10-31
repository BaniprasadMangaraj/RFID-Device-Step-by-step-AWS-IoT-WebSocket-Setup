import asyncio
import websockets
import json

WS_URL = "wss://8b85tilj50.execute-api.ap-south-1.amazonaws.com/prod_multi/"
DEVICE_ID = "RFID-Device-01"

async def main():
    try:
        print(f"🔹 Connecting to {WS_URL}")
        async with websockets.connect(WS_URL) as ws:
            print("✅ Connected to WebSocket API Gateway")

            # Subscribe to a specific device
            subscribe_msg = {
                "action": "subscribeDevice",
                "device_id": DEVICE_ID
            }
            await ws.send(json.dumps(subscribe_msg))
            print(f"📡 Subscribed to device: {DEVICE_ID}")

            # Wait for messages
            async for msg in ws:
                print("📥 Received:", msg)

    except Exception as e:
        print(f"❌ Error: {e}")

# For Python 3.13 / Windows compatibility:
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
