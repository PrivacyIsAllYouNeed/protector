import av
import time
import threading
from av.container import InputContainer
from av.video.frame import VideoFrame
from av.audio.frame import AudioFrame
from av.error import TimeoutError, FFmpegError
from typing import Optional, Any
from misc.state import ThreadStateManager, ConnectionState, ThreadState
from misc.types import VideoData, AudioData
from misc.queues import BoundedQueue
from misc.config import IN_URL, CONNECTION_TIMEOUT, ENABLE_TRANSCRIPTION
from misc.logging import ThreadLogger
from misc.shutdown import is_shutting_down
from misc.metrics import get_metrics_collector


class InputThread(threading.Thread):
    """Standalone input thread with custom lifecycle management for streaming I/O."""

    def __init__(
        self,
        state_manager: ThreadStateManager,
        connection_state: ConnectionState,
        video_queue: BoundedQueue[VideoData],
        audio_queue: BoundedQueue[AudioData],
        vad_queue: Optional[BoundedQueue[AudioData]] = None,
    ):
        super().__init__(name="InputDemuxer", daemon=False)
        self.state_manager = state_manager
        self.connection_state = connection_state
        self.video_queue = video_queue
        self.audio_queue = audio_queue
        self.vad_queue = vad_queue
        self.in_container: Optional[InputContainer] = None
        self.has_audio = False
        self.has_video = False
        self.frame_sequence = 0
        self.audio_sequence = 0
        self.stream_time = 0.0
        self.waiting_logged = False
        self._stop_event = threading.Event()
        self.logger = ThreadLogger("InputDemuxer")
        self.metrics = get_metrics_collector()

    def run(self):
        """Custom run loop designed for blocking I/O operations."""
        self.state_manager.register_thread(self.name)
        self.state_manager.update_state(self.name, ThreadState.RUNNING)
        self.logger.info(f"Starting input thread, listening on {IN_URL}")

        try:
            while not self._should_stop():
                if not self.in_container:
                    # Connection loop - returns False if should stop
                    if not self._connection_loop():
                        break
                else:
                    # Demux loop - returns False if stream ended
                    if not self._demux_loop():
                        self._disconnect()

        except Exception as e:
            self.logger.error(f"Fatal error in thread: {e}")
            self.state_manager.update_state(self.name, ThreadState.ERROR)
        finally:
            self._cleanup()

    def _connection_loop(self) -> bool:
        """Handle connection attempts with proper health signaling.
        Returns False if should stop, True if connected."""
        while not self._should_stop():
            # Send heartbeat before connection attempt
            self._send_heartbeat()

            # Try connection with chunked timeout for responsiveness
            if self._try_connect():
                return True

            # Wait before retry, checking for stop signal
            if self._stop_event.wait(timeout=0.5):
                return False

        return False

    def _try_connect(self) -> bool:
        """Attempt connection with chunked timeout for responsiveness."""
        # Use shorter timeout chunks for better shutdown responsiveness
        chunk_size = 1.0  # 1 second chunks
        max_chunks = int(CONNECTION_TIMEOUT[0] / chunk_size)

        for chunk in range(max_chunks):
            if self._should_stop():
                return False

            try:
                if not self.waiting_logged:
                    self.logger.info("Waiting for RTMP publisher...")
                    self.waiting_logged = True

                # Try connection with short timeout
                self.in_container = av.open(
                    IN_URL,
                    mode="r",
                    options={"listen": "1"},
                    timeout=(chunk_size, chunk_size),
                )

                # Connection successful - gather metadata
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

                # Reset counters
                self.frame_sequence = 0
                self.audio_sequence = 0
                self.stream_time = 0.0
                self.waiting_logged = False

                return True

            except TimeoutError:
                # Timeout is expected, continue with next chunk
                continue

            except (FFmpegError, OSError) as e:
                if "Immediate exit requested" in str(e):
                    return False
                # Only log real errors, not timeouts
                if chunk == 0:  # Only log error once per connection attempt cycle
                    self.logger.debug(f"Connection attempt failed: {e}")
                return False

            except Exception as e:
                self.logger.error(f"Unexpected connection error: {e}")
                return False

        return False

    def _demux_loop(self) -> bool:
        """Process packets with periodic health updates.
        Returns False if stream ended, True if stopped by signal."""
        if not self.in_container:
            return False

        last_heartbeat = time.time()
        packets_since_heartbeat = 0

        try:
            for packet in self.in_container.demux():
                # Process the packet
                if packet.stream.type == "video" and self.has_video:
                    frames = packet.decode()
                    for frame in frames:
                        if isinstance(frame, VideoFrame):
                            self._process_video_frame(frame)
                            packets_since_heartbeat += 1

                elif packet.stream.type == "audio" and self.has_audio:
                    frames = packet.decode()
                    for frame in frames:
                        if isinstance(frame, AudioFrame):
                            self._process_audio_frame(frame)
                            packets_since_heartbeat += 1

                # Periodic health check and heartbeat
                current_time = time.time()
                if current_time - last_heartbeat > 1.0:
                    self._send_heartbeat()
                    self._report_throughput(packets_since_heartbeat)
                    last_heartbeat = current_time
                    packets_since_heartbeat = 0

                # Check for shutdown
                if self._should_stop():
                    return True

        except (StopIteration, FFmpegError, OSError) as e:
            if "Immediate exit requested" not in str(e):
                self.logger.debug(f"Stream ended: {e}")
            return False

        return False

    def _process_video_frame(self, frame: VideoFrame):
        """Process a single video frame."""
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
        """Process a single audio frame."""
        timestamp = float(frame.time) if frame.time else self.stream_time

        audio_data = AudioData(
            frame=frame, timestamp=timestamp, sequence=self.audio_sequence
        )

        # Put audio in main queue
        self.audio_queue.put(audio_data, timeout=0.001)

        # Also put in VAD queue if transcription is enabled
        if ENABLE_TRANSCRIPTION and self.vad_queue:
            self.vad_queue.put(audio_data, timeout=0.001)

        self.audio_sequence += 1

    def _disconnect(self):
        """Handle disconnection and cleanup."""
        if self.in_container:
            try:
                self.in_container.close()
            except Exception:
                pass
            self.in_container = None

        self.connection_state.set_input_connected(False)
        self.logger.info("Publisher disconnected")
        self.waiting_logged = False

        # Clear all queues when input disconnects
        self.logger.debug("Clearing queues after disconnect")
        self.video_queue.clear()
        self.audio_queue.clear()
        if self.vad_queue:
            self.vad_queue.clear()

    def _cleanup(self):
        """Final cleanup when thread is stopping."""
        self._disconnect()
        self.state_manager.update_state(self.name, ThreadState.STOPPED)
        self.state_manager.unregister_thread(self.name)
        self.logger.info("Input thread cleanup complete")

    def stop(self):
        """Request thread to stop."""
        self.logger.info("Stop requested")
        self.state_manager.update_state(self.name, ThreadState.STOPPING)
        self._stop_event.set()

    def wait_stop(self, timeout: Optional[float] = None) -> bool:
        """Wait for thread to stop."""
        return self._stop_event.wait(timeout)

    def _should_stop(self) -> bool:
        """Check if thread should stop."""
        return self._stop_event.is_set() or is_shutting_down()

    def _send_heartbeat(self):
        """Send heartbeat directly to state manager."""
        self.state_manager.heartbeat(self.name)

    def _report_throughput(self, packet_count: int):
        """Report processing metrics."""
        # Can extend this to report more detailed metrics
        if packet_count > 0:
            self.logger.debug(f"Processed {packet_count} packets in last second")
