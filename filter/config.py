"""
Configuration settings for the privacy filter.
"""

from pathlib import Path

# Stream settings
IN_URL = "rtmp://0.0.0.0:1935/live/stream"  # RTMP listen mode
OUT_URL = "rtsp://127.0.0.1:8554/blurred"  # Push to MediaMTX
FPS = 30

# Face detection settings
FACE_BLUR_KERNEL = (51, 51)  # Gaussian blur kernel size for faces
FACE_SCORE_THRESHOLD = 0.7  # YuNet detection threshold
FACE_NMS_THRESHOLD = 0.3  # Non-maximum suppression threshold
FACE_TOP_K = 5000  # Maximum number of faces to detect
FACE_MIN_CONFIDENCE = 0.5  # Minimum confidence to blur a face
FACE_PADDING_RATIO = 0.1  # Padding around detected faces (10% of face size)

# Model settings
MODEL_PATH = Path(__file__).parent / "face_detection_yunet_2023mar.onnx"

# Stream timeout settings
CONNECTION_TIMEOUT = (5.0, 1.0)  # (open_timeout, read_timeout) in seconds

# Video encoder settings
VIDEO_CODEC = "libx264"
VIDEO_PRESET = "veryfast"
VIDEO_TUNE = "zerolatency"
VIDEO_PIX_FMT = "yuv420p"

# Transport settings
RTSP_TRANSPORT = "tcp"
