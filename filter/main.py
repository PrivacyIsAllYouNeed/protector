#!/usr/bin/env python3
"""
RTMP -> Gaussian blur -> RTSP relay with auto-reconnect.
"""

import time
import logging
from collections.abc import Iterator
import av
import cv2
import numpy as np
from av.container import InputContainer, OutputContainer
from av.video.stream import VideoStream
from av.video.frame import VideoFrame
from av.packet import Packet
from av.error import FFmpegError


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)

IN_URL = "rtmp://0.0.0.0:1935/live/stream"  # listen mode
OUT_URL = "rtsp://127.0.0.1:8554/blurred"  # push to MediaMTX
FPS = 30
BLUR_KERNEL = (21, 21)


def blur_and_send(
    frame: VideoFrame,
    out_stream: VideoStream,
    out_container: OutputContainer,
) -> None:
    """Apply blur and send one frame."""
    img = frame.to_ndarray(format="bgr24")
    blurred = cv2.GaussianBlur(img, BLUR_KERNEL, 0)
    # Ensure proper type for from_ndarray
    new_frame = VideoFrame.from_ndarray(blurred.astype(np.uint8), format="bgr24")
    packets: list[Packet] = out_stream.encode(new_frame)
    for pkt in packets:
        out_container.mux(pkt)


def relay_once() -> None:
    """Handle one publishing session until EOF/disconnect."""
    logging.info("Waiting for RTMP publisher...")
    in_container: InputContainer | None = None
    out_container: OutputContainer | None = None
    try:
        in_container = av.open(IN_URL, mode="r", options={"listen": "1"})
        decoder: Iterator[VideoFrame] = in_container.decode(video=0)
        first: VideoFrame = next(decoder)  # blocks until first frame
        w, h = first.width, first.height
        logging.info("Publisher connected (%dx%d).", w, h)

        out_container = av.open(
            OUT_URL, mode="w", format="rtsp", options={"rtsp_transport": "tcp"}
        )
        out_stream: VideoStream = out_container.add_stream(  # pyright: ignore[reportUnknownMemberType]
            "libx264", rate=FPS, options={"preset": "veryfast", "tune": "zerolatency"}
        )
        out_stream.width = w
        out_stream.height = h
        out_stream.pix_fmt = "yuv420p"

        # Process the first frame via the same path.
        blur_and_send(first, out_stream, out_container)

        # Process the rest.
        for frame in decoder:
            blur_and_send(frame, out_stream, out_container)

        # Flush encoder
        flush_packets: list[Packet] = out_stream.encode()
        for pkt in flush_packets:
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
            logging.warning("Stream ended with error: %s", str(e))
        time.sleep(1)  # brief backoff
