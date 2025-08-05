"""
RTMP -> Face detection & blur -> RTSP relay with auto-reconnect.
"""

import time
import logging
import signal
import threading
from types import FrameType
from typing import Any
import av
import cv2
import mediapipe as mp  # type: ignore[import-untyped]
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
BLUR_RATIO = 0.45  # Face blur intensity
MARGIN_RATIO = 0.3  # Face bounding box margin

STOP_EVENT = threading.Event()
_face_detector: Any | None = None  # MediaPipe FaceDetection instance


def _sigint_handler(_signum: int, _frame: FrameType | None) -> None:
    STOP_EVENT.set()


_ = signal.signal(signal.SIGINT, _sigint_handler)


def _get_detector(model_sel: int = 1, min_conf: float = 0.75) -> Any:
    global _face_detector
    if _face_detector is None:
        # Create MediaPipe face detector
        face_detection = getattr(mp.solutions, "face_detection", None)
        if face_detection is None:
            raise RuntimeError("MediaPipe face_detection not available")
        _face_detector = face_detection.FaceDetection(
            model_selection=model_sel, min_detection_confidence=min_conf
        )
    return _face_detector


def blur_faces_videoframe_strict(
    frame: VideoFrame, blur_ratio: float = 0.45, margin_ratio: float = 0.3
) -> VideoFrame:
    """Apply blur to detected face regions only."""
    detector = _get_detector()
    img_bgr = frame.to_ndarray(format="bgr24")
    h, w = img_bgr.shape[:2]

    # Process image with MediaPipe
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    results = detector.process(img_rgb)  # type: ignore[attr-defined]
    
    if hasattr(results, "detections") and results.detections:  # type: ignore[attr-defined]
        for det in results.detections:  # type: ignore[attr-defined]
            # Access bounding box with type ignores
            bbox = det.location_data.relative_bounding_box  # type: ignore[attr-defined]
            x1 = int((bbox.xmin - margin_ratio) * w)  # type: ignore[attr-defined]
            y1 = int((bbox.ymin - margin_ratio) * h)  # type: ignore[attr-defined]
            x2 = int((bbox.xmin + bbox.width + margin_ratio) * w)  # type: ignore[attr-defined]
            y2 = int((bbox.ymin + bbox.height + margin_ratio) * h)  # type: ignore[attr-defined]

            # Clip to image boundaries
            x1 = max(x1, 0)
            y1 = max(y1, 0)
            x2 = min(x2, w)
            y2 = min(y2, h)

            roi = img_bgr[y1:y2, x1:x2]
            bw, bh = x2 - x1, y2 - y1
            k = int(max(bw, bh) * blur_ratio) | 1  # Force odd number
            if roi.size > 0 and k > 1:
                img_bgr[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (k, k), 0)

    out = VideoFrame.from_ndarray(img_bgr, format="bgr24")
    out.pts = frame.pts
    out.time_base = frame.time_base
    return out


def blur_and_send(
    frame: VideoFrame,
    out_stream: VideoStream,
    out_container: OutputContainer,
) -> None:
    """Apply face blur and send one frame."""
    blurred_frame = blur_faces_videoframe_strict(frame, BLUR_RATIO, MARGIN_RATIO)
    for pkt in out_stream.encode(blurred_frame):
        out_container.mux(pkt)


def release_detector() -> None:
    global _face_detector
    if _face_detector:
        _face_detector.close()  # type: ignore[attr-defined]
        _face_detector = None


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
    release_detector()
