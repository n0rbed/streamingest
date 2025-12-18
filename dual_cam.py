import asyncio
import websockets
from flask import Flask, Response
import threading
import time
from werkzeug.serving import make_server

# -----------------------------
# Global memory buffers (per camera)
# -----------------------------
latest_frame_cam1 = None
latest_frame_cam2 = None

frame_lock_cam1 = threading.Lock()
frame_lock_cam2 = threading.Lock()

frame_event_cam1 = threading.Event()
frame_event_cam2 = threading.Event()

frame_counter_cam1 = 0
frame_counter_cam2 = 0

# Load placeholder image
with open("placeholder.jpg", "rb") as f:
    PLACEHOLDER = f.read()

# -----------------------------
# Helpers
# -----------------------------
def is_valid_image(image_bytes):
    """Minimal JPEG validation"""
    return (
        len(image_bytes) > 100
        and image_bytes[:2] == b"\xff\xd8"
        and image_bytes[-2:] == b"\xff\xd9"
    )

# -----------------------------
# WebSocket server: receive frames from ESPs
# -----------------------------
async def handle_connection_factory(cam_id):
    async def handle_connection(websocket):
        global latest_frame_cam1, latest_frame_cam2
        global frame_counter_cam1, frame_counter_cam2

        try:
            async for message in websocket:
                if not isinstance(message, (bytes, bytearray)):
                    continue
                if len(message) < 5000:
                    continue
                if not is_valid_image(message):
                    continue

                if cam_id == 1:
                    with frame_lock_cam1:
                        latest_frame_cam1 = message
                        frame_counter_cam1 += 1
                        frame_event_cam1.set()
                        frame_event_cam1.clear()
                        print(f"[CAM1] Frame {frame_counter_cam1}: {len(message)} bytes")
                else:
                    with frame_lock_cam2:
                        latest_frame_cam2 = message
                        frame_counter_cam2 += 1
                        frame_event_cam2.set()
                        frame_event_cam2.clear()
                        print(f"[CAM2] Frame {frame_counter_cam2}: {len(message)} bytes")

        except websockets.exceptions.ConnectionClosed:
            print(f"WebSocket connection closed (cam {cam_id})")
        except Exception as e:
            print(f"WebSocket error (cam {cam_id}): {e}")

    return handle_connection

async def websocket_servers():
    # cam1 on 3001, cam2 on 3002
    server_cam1 = websockets.serve(
        await handle_connection_factory(1),
        "0.0.0.0",
        3001,
        max_size=2_000_000,
        ping_interval=20,
        ping_timeout=10,
    )
    server_cam2 = websockets.serve(
        await handle_connection_factory(2),
        "0.0.0.0",
        3002,
        max_size=2_000_000,
        ping_interval=20,
        ping_timeout=10,
    )

    # Start both servers
    await asyncio.gather(server_cam1, server_cam2)
    print("WebSocket servers listening on ports 3001 (cam1) and 3002 (cam2)")
    await asyncio.Future()  # run forever

# -----------------------------
# Flask servers: one app per camera / port
# -----------------------------
app_cam1 = Flask("cam1_app")
app_cam2 = Flask("cam2_app")

def mjpeg_gen_cam1():
    global latest_frame_cam1, frame_counter_cam1
    last_counter = -1
    while True:
        frame_event_cam1.wait(timeout=1.0)
        with frame_lock_cam1:
            current_counter = frame_counter_cam1
            frame = latest_frame_cam1 if latest_frame_cam1 else PLACEHOLDER

        if current_counter != last_counter:
            last_counter = current_counter
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        else:
            time.sleep(0.025)  # ~40fps cap

def mjpeg_gen_cam2():
    global latest_frame_cam2, frame_counter_cam2
    last_counter = -1
    while True:
        frame_event_cam2.wait(timeout=1.0)
        with frame_lock_cam2:
            current_counter = frame_counter_cam2
            frame = latest_frame_cam2 if latest_frame_cam2 else PLACEHOLDER

        if current_counter != last_counter:
            last_counter = current_counter
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        else:
            time.sleep(0.025)

@app_cam1.route("/")
def cam1_root():
    return Response(
        mjpeg_gen_cam1(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )

@app_cam2.route("/")
def cam2_root():
    return Response(
        mjpeg_gen_cam2(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )

# Optional: small stats endpoints per cam
@app_cam1.route("/stats")
def cam1_stats():
    with frame_lock_cam1:
        has_frame = latest_frame_cam1 is not None
        frame_size = len(latest_frame_cam1) if latest_frame_cam1 else 0
        return {
            "camera": 1,
            "frames_received": frame_counter_cam1,
            "has_frame": has_frame,
            "frame_size": frame_size,
        }

@app_cam2.route("/stats")
def cam2_stats():
    with frame_lock_cam2:
        has_frame = latest_frame_cam2 is not None
        frame_size = len(latest_frame_cam2) if latest_frame_cam2 else 0
        return {
            "camera": 2,
            "frames_received": frame_counter_cam2,
            "has_frame": has_frame,
            "frame_size": frame_size,
        }

def run_flask_on_port(app, port):
    server = make_server("0.0.0.0", port, app, threaded=True)
    print(f"Flask MJPEG server for {'cam1' if port == 5000 else 'cam2'} on port {port}")
    server.serve_forever()

# -----------------------------
# Run everything
# -----------------------------
if __name__ == "__main__":
    # HTTP: cam1 -> 5000, cam2 -> 5001
    t1 = threading.Thread(target=run_flask_on_port, args=(app_cam1, 5000), daemon=True)
    t2 = threading.Thread(target=run_flask_on_port, args=(app_cam2, 5001), daemon=True)
    t1.start()
    t2.start()

    # WebSockets: cam1 -> 3001, cam2 -> 3002
    try:
        asyncio.run(websocket_servers())
    except KeyboardInterrupt:
        print("\nShutting down...")

