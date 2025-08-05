"""
RTMP -> Face detection and blur using YuNet -> RTSP relay with auto-reconnect.
"""

import time
import logging
import signal
import threading
from types import FrameType
import av
from av.container import InputContainer, OutputContainer
from av.video.stream import VideoStream
from av.audio.stream import AudioStream
from av.video.frame import VideoFrame
from av.error import FFmpegError, TimeoutError

from config import (
    IN_URL,
    OUT_URL,
    FPS,
    CONNECTION_TIMEOUT,
    VIDEO_CODEC,
    VIDEO_PRESET,
    VIDEO_TUNE,
    VIDEO_PIX_FMT,
    RTSP_TRANSPORT,
)
from face_detector import get_face_detector

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)

STOP_EVENT = threading.Event()


def _sigint_handler(_signum: int, _frame: FrameType | None) -> None:
    STOP_EVENT.set()


_ = signal.signal(signal.SIGINT, _sigint_handler)


def blur_and_send(
    frame: VideoFrame,
    out_stream: VideoStream,
    out_container: OutputContainer,
) -> None:
    """Process frame with face blur and send."""
    # Apply face detection and blurring
    face_detector = get_face_detector()
    processed_frame = face_detector.blur_faces_in_frame(frame)

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
            timeout=CONNECTION_TIMEOUT,  # short read-timeout
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
            options={"rtsp_transport": RTSP_TRANSPORT},
            timeout=CONNECTION_TIMEOUT,
        )

        # Add video stream
        out_stream: VideoStream = out_container.add_stream(  # pyright: ignore[reportUnknownMemberType]
            VIDEO_CODEC, rate=FPS, options={"preset": VIDEO_PRESET, "tune": VIDEO_TUNE}
        )
        out_stream.width = w
        out_stream.height = h
        out_stream.pix_fmt = VIDEO_PIX_FMT

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
