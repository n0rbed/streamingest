import asyncio
import websockets
from io import BytesIO
from PIL import Image, UnidentifiedImageError
import os
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(BASE_DIR, "image.jpg")

def is_valid_image(image_bytes):
    try:
        Image.open(BytesIO(image_bytes))
        return True
    except UnidentifiedImageError:
        print("image invalid")
        return False

# 🔧 FIX: new websockets API → only ONE argument
async def handle_connection(websocket):
    try:
        async for message in websocket:
            if not isinstance(message, (bytes, bytearray)):
                continue

            print(f"received {len(message)} bytes")

            if len(message) < 5000:
                continue

            if not is_valid_image(message):
                continue

            # ✅ Atomic write (prevents Flask reading partial file)
            with tempfile.NamedTemporaryFile(dir=BASE_DIR, delete=False) as tmp:
                tmp.write(message)
                tmp.flush()
                os.fsync(tmp.fileno())
                tmp_name = tmp.name

            os.replace(tmp_name, IMAGE_PATH)

    except websockets.exceptions.ConnectionClosed:
        print("connection closed")

async def main():
    async with websockets.serve(handle_connection, "0.0.0.0", 3001):
        print("WebSocket server listening on port 3001")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
