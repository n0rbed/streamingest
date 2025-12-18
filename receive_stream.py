import asyncio
import websockets
from flask import Flask, Response
import threading
import time

# -----------------------------
# Global memory buffer with frame counter
# -----------------------------
latest_frame = None
frame_lock = threading.Lock()
frame_event = threading.Event()
frame_counter = 0

# Load placeholder image
with open("placeholder.jpg", "rb") as f:
    PLACEHOLDER = f.read()

# -----------------------------
# WebSocket server: receive frames from ESP
# -----------------------------
def is_valid_image(image_bytes):
    """Minimal JPEG validation"""
    return len(image_bytes) > 100 and image_bytes[:2] == b'\xff\xd8' and image_bytes[-2:] == b'\xff\xd9'

async def handle_connection(websocket):
    global latest_frame, frame_counter
    try:
        async for message in websocket:
            if not isinstance(message, (bytes, bytearray)):
                continue
            if len(message) < 5000:
                continue
            if not is_valid_image(message):
                continue
            
            # Update frame atomically
            with frame_lock:
                latest_frame = message
                frame_counter += 1
            
            # Notify all waiting clients
            frame_event.set()
            frame_event.clear()
            
            print(f"Frame {frame_counter}: {len(message)} bytes")
    except websockets.exceptions.ConnectionClosed:
        print("WebSocket connection closed")
    except Exception as e:
        print(f"WebSocket error: {e}")

async def websocket_server():
    async with websockets.serve(
        handle_connection, 
        "0.0.0.0", 
        3001,
        max_size=2_000_000,  # Allow 2MB frames
        ping_interval=20,
        ping_timeout=10
    ):
        print("WebSocket server listening on port 3001")
        await asyncio.Future()  # run forever

# -----------------------------
# Flask server: serve MJPEG stream
# -----------------------------
app = Flask(__name__)

@app.route("/")
def index():
    def gen():
        global latest_frame, frame_counter
        last_counter = -1
        
        while True:
            # Wait for new frame with timeout
            frame_event.wait(timeout=1.0)
            
            with frame_lock:
                current_counter = frame_counter
                frame = latest_frame if latest_frame else PLACEHOLDER
            
            # Only send if frame is new
            if current_counter != last_counter:
                last_counter = current_counter
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                # No new frame, send keepalive or sleep briefly
                time.sleep(0.033)  # ~30fps max
    
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route("/stats")
def stats():
    """Endpoint to check stream status"""
    with frame_lock:
        has_frame = latest_frame is not None
        frame_size = len(latest_frame) if latest_frame else 0
    return {
        "frames_received": frame_counter,
        "has_frame": has_frame,
        "frame_size": frame_size
    }

def run_flask():
    from werkzeug.serving import make_server
    server = make_server("0.0.0.0", 5000, app, threaded=True)
    print("Flask MJPEG server listening on port 5000")
    server.serve_forever()

# -----------------------------
# Run both servers
# -----------------------------
if __name__ == "__main__":
    # Run Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Run WebSocket server in asyncio main thread
    try:
        asyncio.run(websocket_server())
    except KeyboardInterrupt:
        print("\nShutting down...")
