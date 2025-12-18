from flask import Flask, Response
from receive_stream import latest_frame  # Import the memory buffer from receive_stream.py

# Load a placeholder image for when no frame is available
with open("placeholder.jpg", "rb") as f:
    PLACEHOLDER = f.read()

app = Flask(__name__)

@app.route("/")
def index():
    def gen():
        global latest_frame
        while True:
            # Use latest_frame if available, else placeholder
            frame = latest_frame if latest_frame else PLACEHOLDER
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    # threaded=True allows multiple clients
    app.run(host="0.0.0.0", port=5000, threaded=True)
