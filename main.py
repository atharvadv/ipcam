from flask import Flask, Response, send_from_directory
from flask_socketio import SocketIO
import cv2
import threading
import time
import os
import numpy as np

app = Flask(__name__, static_folder="../frontend")
socketio = SocketIO(app, cors_allowed_origins="*")

# Camera/video file sources
camera_urls = {
    0: "http://192.168.137.66:8080/video",  # Replace with IP stream or keep local video for testing
    1: "video1.mp4",
    2: "video2.mp4",  # Add more cameras as needed
    3: "video3.mp4",
    4: "video4.mp4",
    5: "video5.mp4",
    6: "video6.mp4",
    7: "video7.mp4",
    8: "video8.mp4",
    9: "video9.mp4",
    10: "video10.mp4",
    11: "video11.mp4",
    12: "video12.mp4",
    13: "video13.mp4",
    14: "video14.mp4",
    15: "video15.mp4"
}

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
    if i not in caps:
        print(f"[INFO] Creating dummy camera {i}")
        # Create a simple dummy frame generator
        caps[i] = None

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
    
    # Initialize frames for motion detection
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
            
            # Calculate difference between frames
            diff = cv2.absdiff(frame1, frame2)
            gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            
            # Apply threshold - Fixed the syntax error here
            _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
            
            # Count non-zero pixels
            count = cv2.countNonZero(thresh)
            
            # Motion detection threshold
            if count > 5000:
                with lock:
                    main_camera_id = cam_id
                print(f"[MOTION] Detected on camera {cam_id} - pixels changed: {count}")
                
                # Emit to all connected clients
                socketio.emit("motion_detected", str(cam_id))
                
                # Add a small delay to avoid too frequent notifications
                time.sleep(2)
            
            # Update frames
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
            
            time.sleep(0.1)  # Reduced sleep time for better responsiveness
            
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
                # Generate dummy frame for cameras without video
                frame = create_dummy_frame(cam_id)
                success = True
            else:
                success, frame = cap.read()
                
                if not success or frame is None:
                    print(f"[WARNING] Failed to read from camera {cam_id}. Resetting...")
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
            
            # Encode frame as JPEG
            try:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if buffer is None:
                    print(f"[ERROR] Failed to encode frame for camera {cam_id}")
                    continue
            except Exception as e:
                print(f"[ERROR] Frame encoding failed for camera {cam_id}: {e}")
                continue
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            
        except Exception as e:
            print(f"[ERROR] Exception in gen_frames for camera {cam_id}: {e}")
            time.sleep(1)
            continue

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/stream/<int:cam_id>")
def stream(cam_id):
    print(f"[INFO] /stream/{cam_id} requested")
    
    if cam_id < 0 or cam_id >= 16:
        print(f"[ERROR] Invalid camera ID: {cam_id}")
        return f"Camera {cam_id} not found", 404
    
    try:
        return Response(gen_frames(cam_id), 
                       mimetype='multipart/x-mixed-replace; boundary=frame')
    except Exception as e:
        print(f"[ERROR] Exception in stream({cam_id}): {e}")
        return f"Internal Server Error: {str(e)}", 500

@socketio.on("connect")
def handle_connect():
    print("[SOCKET] Client connected")

@socketio.on("disconnect")
def handle_disconnect():
    print("[SOCKET] Client disconnected")

@socketio.on("test_motion")
def handle_test_motion(data):
    """Test endpoint to simulate motion detection"""
    cam_id = int(data.get('cam_id', 0))
    print(f"[TEST] Simulating motion on camera {cam_id}")
    socketio.emit("motion_detected", str(cam_id))

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
        # Start motion detection threads only for cameras with actual video files
        for i in camera_urls.keys():
            if caps.get(i) is not None:
                threading.Thread(target=detect_motion, args=(i,), daemon=True).start()
                print(f"[INFO] Motion detection thread started for camera {i}")
        
        print("[INFO] Starting Flask-SocketIO server...")
        socketio.run(app, host="0.0.0.0", port=5000, debug=True)
        
    except KeyboardInterrupt:
        print("[INFO] Shutting down...")
        cleanup()
    except Exception as e:
        print(f"[ERROR] Server error: {e}")
        cleanup()