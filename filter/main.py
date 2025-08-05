#!/usr/bin/env python3
"""
RTMP -> Gaussian blur -> RTSP relay with auto-reconnect.
"""

import time
import logging
import av
import cv2

# Try to use the canonical PyAV error; fall back if missing.
try:
    from av.error import FFmpegError  # type: ignore
except Exception:  # pragma: no cover

    class FFmpegError(Exception):  # minimal fallback
        pass


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)

IN_URL = "rtmp://0.0.0.0:1935/live/stream"  # listen mode
OUT_URL = "rtsp://127.0.0.1:8554/blurred"  # push to MediaMTX
FPS = 30
BLUR_KERNEL = (21, 21)


def blur_and_send(
    frame: av.VideoFrame,
    out_stream: av.video.stream.VideoStream,
    out_container: av.container.OutputContainer,
) -> None:
    """Apply blur and send one frame."""
    img = frame.to_ndarray(format="bgr24")
    blurred = cv2.GaussianBlur(img, BLUR_KERNEL, 0)
    new_frame = av.VideoFrame.from_ndarray(blurred, format="bgr24")
    for pkt in out_stream.encode(new_frame):
        out_container.mux(pkt)


def relay_once() -> None:
    """Handle one publishing session until EOF/disconnect."""
    logging.info("Waiting for RTMP publisher...")
    in_container = None
    out_container = None
    try:
        in_container = av.open(IN_URL, mode="r", options={"listen": "1"})
        decoder = in_container.decode(video=0)
        first = next(decoder)  # blocks until first frame
        w, h = first.width, first.height
        logging.info("Publisher connected (%dx%d).", w, h)

        out_container = av.open(
            OUT_URL, mode="w", format="rtsp", options={"rtsp_transport": "tcp"}
        )
        out_stream = out_container.add_stream("libx264", rate=FPS)
        out_stream.width = w
        out_stream.height = h
        out_stream.pix_fmt = "yuv420p"
        out_stream.options = {"preset": "veryfast", "tune": "zerolatency"}

        # Process the first frame via the same path.
        blur_and_send(first, out_stream, out_container)

        # Process the rest.
        for frame in decoder:
            blur_and_send(frame, out_stream, out_container)

        # Flush encoder
        for pkt in out_stream.encode():
            out_container.mux(pkt)
        logging.info("Publisher disconnected (EOF).")
    finally:
        # Always close containers to free sockets/handles.
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
    while True:
        try:
            relay_once()
        except (StopIteration, FFmpegError, OSError) as e:
            logging.warning("Stream ended with error: %s", e)
        time.sleep(1)  # brief backoff
