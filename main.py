from flask import Flask, Response, send_from_directory, request, session, redirect, jsonify
from flask_socketio import SocketIO
import cv2
import threading
import time
import os
import numpy as np
import firebase_admin
from firebase_admin import auth, credentials
import json

app = Flask(__name__, static_folder="../frontend")
app.secret_key = os.urandom(24).hex()  # Secure random key
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize Firebase Admin SDK
cred = credentials.Certificate("motiondetection-52cba-firebase-adminsdk-fbsvc-11ac127790.json")
firebase_admin.initialize_app(cred)

# Load or initialize camera URLs from JSON file
CAMERAS_FILE = "cameras.json"


def load_cameras():
    if os.path.exists(CAMERAS_FILE):
        with open(CAMERAS_FILE, 'r') as f:
            return json.load(f)
    return {
        "0": "http://192.168.137.66:8080/video",
        "1": "video1.mp4",
        "2": "video2.mp4",
        "3": "video3.mp4",
        "4": "video4.mp4",
        "5": "video5.mp4",
        "6": "video6.mp4",
        "7": "video7.mp4",
        "8": "video8.mp4",
        "9": "video9.mp4",
        "10": "video10.mp4",
        "11": "video11.mp4",
        "12": "video12.mp4",
        "13": "video13.mp4",
        "14": "video14.mp4",
        "15": "video15.mp4"
    }


def save_cameras(cameras):
    with open(CAMERAS_FILE, 'w') as f:
        json.dump(cameras, f)


camera_urls = load_cameras()

# Initialize VideoCapture objects
caps = {}
for i, url in camera_urls.items():
    cap = cv2.VideoCapture(url)
    if cap.isOpened():
        caps[i] = cap
        print(f"[OK] Camera {i} loaded: {url}")
    else:
        print(f"[ERROR] Camera {i} failed to open: {url}")

# For cameras that don't have video files, create dummy black frames
for i in range(16):
    if str(i) not in caps:
        print(f"[INFO] Creating dummy camera {i}")
        caps[str(i)] = None

main_camera_id = 0
lock = threading.Lock()
motion_detection_active = True


def create_dummy_frame(cam_id):
    """Create a dummy frame for cameras without video files"""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(frame, f"Camera {cam_id}", (200, 200),
                cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
    cv2.putText(frame, "No Video Source", (150, 300),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (128, 128, 128), 2)
    return frame


def detect_motion(cam_id):
    """Motion detection thread function"""
    global main_camera_id, motion_detection_active

    cap = caps.get(cam_id)
    if cap is None:
        print(f"[INFO] Camera {cam_id} is dummy - no motion detection")
        return

    print(f"[INFO] Starting motion detection for camera {cam_id}")

    ret1, frame1 = cap.read()
    if not ret1:
        print(f"[ERROR] Could not read initial frame from camera {cam_id}")
        return

    ret2, frame2 = cap.read()
    if not ret2:
        print(f"[ERROR] Could not read second frame from camera {cam_id}")
        return

    frame_count = 0

    while motion_detection_active:
        try:
            if not cap.isOpened():
                print(f"[ERROR] Camera {cam_id} is not opened")
                break

            diff = cv2.absdiff(frame1, frame2)
            gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
            count = cv2.countNonZero(thresh)

            if count > 5000:
                with lock:
                    main_camera_id = cam_id
                print(f"[MOTION] Detected on camera {cam_id} - pixels changed: {count}")
                socketio.emit("motion_detected", str(cam_id))
                time.sleep(2)

            frame1 = frame2.copy()
            ret, frame2 = cap.read()

            if not ret or frame2 is None:
                print(f"[RESET] Camera {cam_id} reached end, restarting...")
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret1, frame1 = cap.read()
                ret2, frame2 = cap.read()
                if not ret1 or not ret2:
                    print(f"[ERROR] Could not reset camera {cam_id}")
                    break

            frame_count += 1
            if frame_count % 100 == 0:
                print(f"[DEBUG] Camera {cam_id} processed {frame_count} frames")

            time.sleep(0.1)

        except Exception as e:
            print(f"[ERROR] Motion detection error for camera {cam_id}: {e}")
            time.sleep(1)
            continue


def gen_frames(cam_id):
    """Stream generator for each camera"""
    print(f"[INFO] gen_frames started for cam {cam_id}")

    cap = caps.get(cam_id)

    while True:
        try:
            if cap is None:
                frame = create_dummy_frame(cam_id)
                success = True
            else:
                success, frame = cap.read()

                if not success or frame is None:
                    print(f"[WARNING] Failed to read from camera {cam_id}. Resetting...")
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if buffer is None:
                print(f"[ERROR] Failed to encode frame for camera {cam_id}")
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

        except Exception as e:
            print(f"[ERROR] Exception in gen_frames for camera {cam_id}: {e}")
            time.sleep(1)
            continue


def login_required(f):
    """Decorator to protect routes"""
    def wrap(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap


def admin_required(f):
    """Decorator to protect admin routes"""
    def wrap(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect('/login')
        if session.get('role') != 'admin':
            return jsonify({'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap


@app.route("/login")
def login_page():
    if 'logged_in' in session:
        # Redirect based on existing role
        if session.get('role') == 'admin':
            return redirect('/admin-dashboard')
        else:
            return redirect('/user-dashboard')
    return send_from_directory(app.static_folder, "login.html")


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    id_token = data.get('idToken')
    role = data.get('role', 'user')  # Get role from request
    
    try:
        decoded_token = auth.verify_id_token(id_token)
        session['logged_in'] = True
        session['uid'] = decoded_token['uid']
        session['email'] = decoded_token.get('email', 'Unknown')
        session['role'] = role  # Store the role in session
        
        print(f"[LOGIN] User logged in: UID={decoded_token['uid']}, Email={decoded_token.get('email', 'Unknown')}, Role={role}")
        return jsonify({'message': 'Login successful', 'role': role}), 200
    except Exception as e:
        print(f"[LOGIN ERROR] Authentication failed: {str(e)}")
        return jsonify({'message': 'Authentication failed: ' + str(e)}), 401


@app.route("/logout")
@login_required
def logout():
    session.pop('logged_in', None)
    session.pop('uid', None)
    session.pop('email', None)
    session.pop('role', None)
    return redirect('/login')


# Main dashboard route (original route)
@app.route("/")
@login_required
def index():
    print(f"[ACCESS] Dashboard accessed by UID={session.get('uid', 'Unknown')}, Email={session.get('email', 'Unknown')}")
    return send_from_directory(app.static_folder, "index.html")


# User dashboard route
@app.route("/user-dashboard")
@login_required
def user_dashboard():
    print(f"[ACCESS] User Dashboard accessed by UID={session.get('uid', 'Unknown')}, Email={session.get('email', 'Unknown')}")
    # You can serve a different HTML file for users if needed, or the same one
    return send_from_directory(app.static_folder, "index.html")


# Admin dashboard route
@app.route("/admin-dashboard")
@login_required
def admin_dashboard():
    print(f"[ACCESS] Admin Dashboard accessed by UID={session.get('uid', 'Unknown')}, Email={session.get('email', 'Unknown')}")
    # You can serve a different HTML file for admins if needed, or the same one
    return send_from_directory(app.static_folder, "index.html")


@app.route("/stream/<cam_id>")
@login_required
def stream(cam_id):
    print(f"[ACCESS] Stream {cam_id} accessed by UID={session.get('uid', 'Unknown')}, Email={session.get('email', 'Unknown')}")
    if cam_id not in caps:
        print(f"[ERROR] Invalid camera ID: {cam_id}")
        return f"Camera {cam_id} not found", 404
    try:
        return Response(gen_frames(cam_id),
                        mimetype='multipart/x-mixed-replace; boundary=frame')
    except Exception as e:
        print(f"[ERROR] Exception in stream({cam_id}): {e}")
        return f"Internal Server Error: {str(e)}", 500


@app.route("/add-camera", methods=["POST"])
@admin_required  # Only admins can add cameras
def add_camera():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'message': 'URL is required'}), 400
    cam_id = str(len(camera_urls))
    camera_urls[cam_id] = url
    cap = cv2.VideoCapture(url)
    if cap.isOpened():
        caps[cam_id] = cap
        save_cameras(camera_urls)
        threading.Thread(target=detect_motion, args=(cam_id,), daemon=True).start()
        print(f"[ADD] Camera {cam_id} added: {url}")
        return jsonify({'message': 'Camera added', 'cam_id': cam_id}), 200
    else:
        print(f"[ERROR] Failed to add camera {cam_id}: {url}")
        return jsonify({'message': 'Invalid camera URL'}), 400


@app.route("/remove-camera/<cam_id>", methods=["POST"])
@admin_required  # Only admins can remove cameras
def remove_camera(cam_id):
    if cam_id in camera_urls:
        if caps.get(cam_id):
            caps[cam_id].release()
        del camera_urls[cam_id]
        del caps[cam_id]
        save_cameras(camera_urls)
        print(f"[REMOVE] Camera {cam_id} removed")
        return jsonify({'message': 'Camera removed'}), 200
    return jsonify({'message': 'Camera not found'}), 404


@app.route("/cameras")
@login_required
def get_cameras():
    return jsonify(camera_urls)


# API route to get user info including role
@app.route("/user-info")
@login_required
def user_info():
    return jsonify({
        'uid': session.get('uid'),
        'email': session.get('email'),
        'role': session.get('role', 'user')
    })


@socketio.on("connect")
def handle_connect():
    if 'logged_in' not in session:
        return False
    print(f"[SOCKET] Client connected: UID={session.get('uid', 'Unknown')}, Email={session.get('email', 'Unknown')}, Role={session.get('role', 'user')}")
    socketio.emit('cameras', camera_urls)


@socketio.on("disconnect")
def handle_disconnect():
    print(f"[SOCKET] Client disconnected: UID={session.get('uid', 'Unknown')}, Email={session.get('email', 'Unknown')}")


@socketio.on("test_motion")
def handle_test_motion(data):
    if 'logged_in' not in session:
        return
    cam_id = str(data.get('cam_id', 0))
    print(f"[TEST] Simulating motion on camera {cam_id} by UID={session.get('uid', 'Unknown')}")
    socketio.emit("motion_detected", cam_id)


def cleanup():
    """Cleanup function to properly close all video captures"""
    global motion_detection_active
    motion_detection_active = False
    for i, cap in caps.items():
        if cap is not None:
            cap.release()
    print("[INFO] All cameras released")


if __name__ == "__main__":
    try:
        for i in camera_urls.keys():
            if caps.get(i) is not None:
                threading.Thread(target=detect_motion, args=(i,), daemon=True).start()
                print(f"[INFO] Motion detection thread started for camera {i}")

        print("[INFO] Starting Flask-SocketIO server...")
        socketio.run(app, host="localhost", port=5000, debug=True)

    except KeyboardInterrupt:
        print("[INFO] Shutting down...")
        cleanup()
    except Exception as e:
        print(f"[ERROR] Server error: {e}")
        cleanup()
