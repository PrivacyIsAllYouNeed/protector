"""
RTMP -> Gaussian blur -> RTSP relay with auto-reconnect.
"""

import time
import logging
import signal
import threading
import av
import cv2
import numpy as np
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
BLUR_KERNEL = (21, 21)

STOP_EVENT = threading.Event()


def _sigint_handler(signum, frame):
    STOP_EVENT.set()


signal.signal(signal.SIGINT, _sigint_handler)


def blur_and_send(
    frame: VideoFrame,
    out_stream: VideoStream,
    out_container: OutputContainer,
) -> None:
    """Apply blur and send one frame."""
    img = frame.to_ndarray(format="bgr24")
    blurred = cv2.GaussianBlur(img, BLUR_KERNEL, 0)
    new_frame = VideoFrame.from_ndarray(blurred.astype(np.uint8), format="bgr24")
    for pkt in out_stream.encode(new_frame):
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
