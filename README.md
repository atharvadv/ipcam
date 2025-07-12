# ipcam
# ipcam

A lightweight, real-time multi-IP camera monitoring and motion detection dashboard.

## Overview

This project provides a web-based dashboard for viewing up to 16 IP cameras or video sources simultaneously, with built-in real-time motion detection. It's designed for home/lab monitoring, security, or any application where you want a live grid of camera feeds and want to be notified visually when motion is detected.

Frontend is a single-page web app (HTML/JS) that shows:
- A grid of all cameras (live MJPEG streams)
- A "motion detected" area that highlights which cameras detected motion in the last 10 seconds

Backend is a Python Flask server with Flask-SocketIO for real-time events, OpenCV for video processing, and simple motion detection.

## Features

- **Supports up to 16 cameras** (IP streams or local video files for testing)
- **Live grid** with all cameras
- **Motion detection** for each camera (OpenCV-based, per-frame difference)
- **Real-time UI updates** via WebSockets (Socket.IO)
- **Visual highlights** for cameras with recent motion
- **Dummy feeds** for missing camera sources (so grid always stays full)
- **Lightweight, no DB, easy to deploy/extend**

## Quick Start

### Requirements

- Python 3.8+
- pip (for dependencies)
- Node.js (optional, only if running custom frontend build)

### Install dependencies

```sh
pip install flask flask-socketio opencv-python numpy
```

### Configure camera sources

Edit the `camera_urls` dictionary in `main.py` to set your IP camera URLs or local video files:

```python
camera_urls = {
    0: "http://<your-ip-cam-1>/video",
    1: "video1.mp4",
    # ...
}
```

If a camera index does not have a video source, a dummy feed will be shown.

### Run the server

```sh
python main.py
```

By default, it starts on `http://localhost:5000/`

### Open the dashboard

Go to [http://localhost:5000](http://localhost:5000) in your browser.

## How It Works

- Each camera stream is read using OpenCV in Python (`main.py`)
- Motion is detected by comparing frames (counting changed pixels)
- When motion is detected, a Socket.IO event is broadcast
- The frontend (`index.html`) listens for those events and visually highlights the affected camera(s)
- If a video file ends or fails, the code resets it for continuous looping

## Customization

- Change the motion threshold in `main.py` (`if count > 5000:`) as needed for your setup
- Adjust frontend display, grid, or styles in `index.html`
- Add or remove cameras by editing the `camera_urls` dict

## Troubleshooting

- Make sure your camera streams are reachable from the server
- Use video files for testing if you do not have IP cameras
- Check terminal logs for errors (camera not found, etc.)

## Credits

- Author: Pratik Halkunde (see `index.html` for reference)
- Maintained by: [atharvadv](https://github.com/atharvadv)

## License

MIT License. See [LICENSE](LICENSE) for details.

---

**Contributions welcome!**
