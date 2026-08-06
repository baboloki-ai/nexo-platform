import asyncio
import websockets


async def test():
    uri = "ws://127.0.0.1:8000/ws/driver/14"

    async with websockets.connect(uri) as websocket:
        print("✅ Connected to NEXO Driver 14 WebSocket!")

        while True:
            message = await websocket.recv()
            print("Received:", message)


asyncio.run(test())