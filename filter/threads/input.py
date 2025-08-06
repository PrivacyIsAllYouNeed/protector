import av
from av.container import InputContainer
from av.video.frame import VideoFrame
from av.audio.frame import AudioFrame
from av.error import TimeoutError, FFmpegError
from typing import Optional, Any
from threads.base import BaseThread
from misc.state import ThreadStateManager, ConnectionState
from misc.types import VideoData, AudioData
from misc.queues import BoundedQueue
from misc.config import IN_URL, CONNECTION_TIMEOUT, ENABLE_TRANSCRIPTION


class InputThread(BaseThread):
    def __init__(
        self,
        state_manager: ThreadStateManager,
        connection_state: ConnectionState,
        video_queue: BoundedQueue[VideoData],
        audio_queue: BoundedQueue[AudioData],
        transcription_queue: Optional[BoundedQueue[AudioData]] = None,
    ):
        super().__init__(
            name="InputDemuxer", state_manager=state_manager, heartbeat_interval=1.0
        )
        self.connection_state = connection_state
        self.video_queue = video_queue
        self.audio_queue = audio_queue
        self.transcription_queue = transcription_queue
        self.in_container: Optional[InputContainer] = None
        self.has_audio = False
        self.has_video = False
        self.frame_sequence = 0
        self.audio_sequence = 0
        self.stream_time = 0.0

    def setup(self):
        self.logger.info(f"Starting input thread, listening on {IN_URL}")

    def process_iteration(self) -> bool:
        if not self.in_container:
            if not self._connect():
                return False

        try:
            return self._process_packets()
        except (TimeoutError, StopIteration):
            return False
        except (FFmpegError, OSError) as e:
            if "Immediate exit requested" not in str(e):
                self.logger.warning(f"Stream error: {e}")
            self._disconnect()
            return False

    def _connect(self) -> bool:
        try:
            self.logger.info("Waiting for RTMP publisher...")
            self.in_container = av.open(
                IN_URL, mode="r", options={"listen": "1"}, timeout=CONNECTION_TIMEOUT
            )

            self.has_video = len(self.in_container.streams.video) > 0
            self.has_audio = len(self.in_container.streams.audio) > 0

            metadata: dict[str, Any] = {
                "has_video": self.has_video,
                "has_audio": self.has_audio,
            }

            if self.has_video:
                video_stream = self.in_container.streams.video[0]
                metadata["video_codec"] = video_stream.codec_context.name
                metadata["video_width"] = video_stream.codec_context.width
                metadata["video_height"] = video_stream.codec_context.height
                metadata["video_fps"] = float(video_stream.average_rate or 0)

            if self.has_audio:
                audio_stream = self.in_container.streams.audio[0]
                metadata["audio_codec"] = audio_stream.codec_context.name
                metadata["audio_rate"] = audio_stream.codec_context.sample_rate
                metadata["audio_channels"] = audio_stream.codec_context.channels

            self.connection_state.set_input_connected(True, metadata)
            self.logger.info(f"Publisher connected: {metadata}")

            self.frame_sequence = 0
            self.audio_sequence = 0
            self.stream_time = 0.0

            return True

        except TimeoutError:
            return False
        except Exception as e:
            self.logger.error(f"Connection error: {e}")
            return False

    def _disconnect(self):
        if self.in_container:
            try:
                self.in_container.close()
            except Exception:
                pass
            self.in_container = None

        self.connection_state.set_input_connected(False)
        self.logger.info("Publisher disconnected")

    def _process_packets(self) -> bool:
        if not self.in_container:
            return False

        processed_any = False

        try:
            for packet in self.in_container.demux():
                if self.should_stop():
                    break

                if packet.stream.type == "video" and self.has_video:
                    frames = packet.decode()
                    for frame in frames:
                        if isinstance(frame, VideoFrame):
                            self._process_video_frame(frame)
                            processed_any = True

                elif packet.stream.type == "audio" and self.has_audio:
                    frames = packet.decode()
                    for frame in frames:
                        if isinstance(frame, AudioFrame):
                            self._process_audio_frame(frame)
                            processed_any = True

        except TimeoutError:
            return processed_any
        except StopIteration:
            self._disconnect()
            raise

        return processed_any

    def _process_video_frame(self, frame: VideoFrame):
        timestamp = float(frame.time) if frame.time else self.stream_time

        video_data = VideoData(
            frame=frame, timestamp=timestamp, sequence=self.frame_sequence
        )

        if not self.video_queue.put(video_data, timeout=0.001):
            self.metrics.record_dropped_frame()
            self.logger.debug(f"Dropped video frame {self.frame_sequence}")

        self.frame_sequence += 1
        self.stream_time = timestamp

    def _process_audio_frame(self, frame: AudioFrame):
        timestamp = float(frame.time) if frame.time else self.stream_time

        audio_data = AudioData(
            frame=frame, timestamp=timestamp, sequence=self.audio_sequence
        )

        self.audio_queue.put(audio_data, timeout=0.001)

        if ENABLE_TRANSCRIPTION and self.transcription_queue:
            self.transcription_queue.put(audio_data, timeout=0.001)

        self.audio_sequence += 1

    def cleanup(self):
        self._disconnect()
        self.logger.info("Input thread cleanup complete")
