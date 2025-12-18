import asyncio
import websockets

# Global variable to store the latest image in memory
latest_frame = None

def is_valid_image(image_bytes):
    """Optional minimal validation: check JPEG SOI marker"""
    return image_bytes[:2] == b'\xff\xd8' and image_bytes[-2:] == b'\xff\xd9'

async def handle_connection(websocket):
    global latest_frame
    try:
        async for message in websocket:
            # Only process binary messages
            if not isinstance(message, (bytes, bytearray)):
                continue

            # Ignore too-small frames
            if len(message) < 5000:
                continue

            # Optional minimal validation
            if not is_valid_image(message):
                continue

            # Store the latest frame in memory
            latest_frame = message

            # Debug: print size
            print(f"Received {len(message)} bytes")
    except websockets.exceptions.ConnectionClosed:
        print("WebSocket connection closed")

async def main():
    async with websockets.serve(handle_connection, "0.0.0.0", 3001):
        print("WebSocket server listening on port 3001")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
