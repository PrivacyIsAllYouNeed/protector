"""
RTMP -> Face detection and blur using YuNet -> RTSP relay with auto-reconnect.
"""

import time
import logging
import signal
import threading
from types import FrameType
from pathlib import Path
from typing import Any, cast
import numpy as np
from numpy.typing import NDArray
import av
import cv2
from av.container import InputContainer, OutputContainer
from av.video.stream import VideoStream
from av.audio.stream import AudioStream
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
# Type as Any since cv2.FaceDetectorYN is not fully typed
face_detector: Any = cv2.FaceDetectorYN.create(  # pyright: ignore[reportExplicitAny]
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
    face_detector.setInputSize((w, h))  # pyright: ignore[reportAny]

    # Detect faces - returns tuple of (retval, faces)
    # faces can be None (when no faces) or np.ndarray
    _, faces_result = face_detector.detect(bgr)  # pyright: ignore[reportAny]

    # Cast faces_result to handle the union type properly
    faces: NDArray[np.float32] | None = cast(NDArray[np.float32] | None, faces_result)

    # If no faces detected, return original frame
    if faces is None or len(faces) == 0:
        return frame

    # Apply blur to each detected face
    for i in range(len(faces)):
        face_row = faces[i]  # pyright: ignore[reportAny]
        x: float = float(face_row[0])  # pyright: ignore[reportAny]
        y: float = float(face_row[1])  # pyright: ignore[reportAny]
        face_w: float = float(face_row[2])  # pyright: ignore[reportAny]
        face_h: float = float(face_row[3])  # pyright: ignore[reportAny]
        score: float = float(face_row[4])  # pyright: ignore[reportAny]

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

    # Convert back to VideoFrame, preserving timing information
    new_frame = VideoFrame.from_ndarray(bgr, format="bgr24")
    new_frame.pts = frame.pts
    new_frame.time_base = frame.time_base
    return new_frame


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

        # Check for audio stream
        audio_stream = None
        out_audio_stream = None
        if in_container.streams.audio:
            audio_stream = in_container.streams.audio[0]
            logging.info("Audio stream detected: %s", audio_stream.codec_context.name)

        # Setup video decoder
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

        # Add video stream
        out_stream: VideoStream = out_container.add_stream(  # pyright: ignore[reportUnknownMemberType]
            "libx264", rate=FPS, options={"preset": "veryfast", "tune": "zerolatency"}
        )
        out_stream.width = w
        out_stream.height = h
        out_stream.pix_fmt = "yuv420p"

        # Add audio stream if present in input
        if audio_stream:
            # Copy audio codec from input
            codec_name = audio_stream.codec_context.name
            audio_out = out_container.add_stream(codec_name, rate=audio_stream.rate)  # pyright: ignore[reportUnknownMemberType]
            # Type check to ensure we have an AudioStream
            if isinstance(audio_out, AudioStream):
                out_audio_stream = audio_out
                # Copy codec context parameters
                out_audio_stream.codec_context.layout = (
                    audio_stream.codec_context.layout
                )
                out_audio_stream.codec_context.sample_rate = (
                    audio_stream.codec_context.sample_rate
                )
                logging.info(
                    "Audio stream added to output: %s at %dHz with %d channels",
                    codec_name,
                    audio_stream.rate,
                    audio_stream.codec_context.channels,
                )

        # Process first video frame
        blur_and_send(first, out_stream, out_container)

        # Process both audio and video packets
        while not STOP_EVENT.is_set():
            try:
                # Demux packets from input
                for packet in in_container.demux():
                    if STOP_EVENT.is_set():
                        break

                    if packet.stream.type == "video":
                        # Decode video frames and process them
                        frames = packet.decode()
                        for frame in frames:
                            if isinstance(frame, VideoFrame):
                                blur_and_send(frame, out_stream, out_container)
                    elif packet.stream.type == "audio" and out_audio_stream:
                        # Remux audio packets directly without decoding
                        packet.stream = out_audio_stream
                        out_container.mux(packet)

            except TimeoutError:
                continue
            except StopIteration:
                break

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
