"""
RTMP -> Face detection and blur using YuNet -> RTSP relay with auto-reconnect.
"""

import time
import logging
import signal
import threading
from types import FrameType
from pathlib import Path
import av
import cv2
from av.container import InputContainer, OutputContainer
from av.video.stream import VideoStream
from av.video.frame import VideoFrame
from av.error import FFmpegError, TimeoutError

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)

IN_URL = "rtmp://0.0.0.0:1935/live/stream"  # listen mode
OUT_URL = "rtsp://127.0.0.1:8554/blurred"  # push to MediaMTX
FPS = 30
FACE_BLUR_KERNEL = (51, 51)  # Stronger blur for faces
MODEL_PATH = Path(__file__).parent / "face_detection_yunet_2023mar.onnx"

# Initialize YuNet face detector
face_detector = cv2.FaceDetectorYN.create(
    model=str(MODEL_PATH),
    config="",
    input_size=(320, 320),  # Default size, will be adjusted per frame
    score_threshold=0.7,  # Lower threshold for better detection
    nms_threshold=0.3,
    top_k=5000,
    backend_id=cv2.dnn.DNN_BACKEND_OPENCV,
    target_id=cv2.dnn.DNN_TARGET_CPU,
)

STOP_EVENT = threading.Event()


def _sigint_handler(_signum: int, _frame: FrameType | None) -> None:
    STOP_EVENT.set()


_ = signal.signal(signal.SIGINT, _sigint_handler)


def blur_faces_in_frame(frame: VideoFrame) -> VideoFrame:
    """Detect and blur faces in a VideoFrame using YuNet."""
    # Convert PyAV frame to NumPy array (BGR format)
    bgr = frame.to_ndarray(format="bgr24")
    h, w = bgr.shape[:2]

    # Update detector input size to match frame dimensions
    face_detector.setInputSize((w, h))

    # Detect faces
    _, faces = face_detector.detect(bgr)

    # If no faces detected, return original frame
    if faces is None or len(faces) == 0:
        return frame

    # Apply blur to each detected face
    for face in faces:
        x, y, face_w, face_h, score = (
            float(face[0]),
            float(face[1]),
            float(face[2]),
            float(face[3]),
            float(face[4]),
        )

        # Skip low confidence detections
        if score < 0.5:
            continue

        # Calculate bounding box with some padding
        padding = int(min(face_w, face_h) * 0.1)
        x1 = int(max(0, x - padding))
        y1 = int(max(0, y - padding))
        x2 = int(min(w - 1, x + face_w + padding))
        y2 = int(min(h - 1, y + face_h + padding))

        # Extract ROI
        roi = bgr[y1:y2, x1:x2]

        # Apply Gaussian blur to ROI if it's not empty
        if roi.size > 0:
            roi_blurred = cv2.GaussianBlur(roi, FACE_BLUR_KERNEL, 0)
            # Replace original ROI with blurred version
            bgr[y1:y2, x1:x2] = roi_blurred

    # Convert back to VideoFrame
    return VideoFrame.from_ndarray(bgr, format="bgr24")


def blur_and_send(
    frame: VideoFrame,
    out_stream: VideoStream,
    out_container: OutputContainer,
) -> None:
    """Process frame with face blur and send."""
    # Apply face detection and blurring
    processed_frame = blur_faces_in_frame(frame)

    # Encode and send
    for pkt in out_stream.encode(processed_frame):
        out_container.mux(pkt)


def relay_once() -> None:
    """Handle one publishing session until EOF/disconnect or Ctrl-C."""
    logging.info("Waiting for RTMP publisher...")
    in_container: InputContainer | None = None
    out_container: OutputContainer | None = None
    try:
        in_container = av.open(
            IN_URL,
            mode="r",
            options={"listen": "1"},
            timeout=(5.0, 1.0),  # short read-timeout
        )
        decoder = in_container.decode(video=0)

        # wait for first frame / publisher
        while True:
            if STOP_EVENT.is_set():
                return
            try:
                first = next(decoder)
                break
            except TimeoutError:
                continue

        w, h = first.width, first.height
        logging.info("Publisher connected (%dx%d).", w, h)

        out_container = av.open(
            OUT_URL,
            mode="w",
            format="rtsp",
            options={"rtsp_transport": "tcp"},
            timeout=(5.0, 1.0),
        )
        out_stream: VideoStream = out_container.add_stream(  # pyright: ignore[reportUnknownMemberType]
            "libx264", rate=FPS, options={"preset": "veryfast", "tune": "zerolatency"}
        )
        out_stream.width = w
        out_stream.height = h
        out_stream.pix_fmt = "yuv420p"

        blur_and_send(first, out_stream, out_container)

        while not STOP_EVENT.is_set():
            try:
                frame = next(decoder)
            except TimeoutError:
                continue
            except StopIteration:
                break
            blur_and_send(frame, out_stream, out_container)

        # Flush encoder
        for pkt in out_stream.encode():
            out_container.mux(pkt)
        logging.info("Publisher disconnected (EOF).")
    finally:
        try:
            if out_container is not None:
                out_container.close()
        except Exception:
            pass
        try:
            if in_container is not None:
                in_container.close()
        except Exception:
            pass


if __name__ == "__main__":
    while not STOP_EVENT.is_set():
        try:
            relay_once()
        except (StopIteration, TimeoutError):
            # benign end-of-stream or poll timeout – keep silent
            if STOP_EVENT.is_set():
                break
        except (FFmpegError, OSError) as e:
            if STOP_EVENT.is_set():
                break
            # suppress the noise
            if "Immediate exit requested" in str(e):
                continue
            logging.warning("Stream ended with error: %s", str(e))
        time.sleep(1)  # brief backoff
    logging.info("Interrupted by user (Ctrl-C). Exiting.")
