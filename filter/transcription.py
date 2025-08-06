"""
Real-time transcription using Silero VAD and faster-whisper.

Overview of how it works:
-------------------------
1. Audio Stream Processing:
   - Receives audio packets from RTMP input stream via PyAV
   - Decodes packets into audio frames for processing
   - Maintains compatibility with main audio remuxing pipeline

2. Audio Resampling:
   - Automatically resamples any input audio format to target sampling rate
   - Uses PyAV's AudioResampler for efficient format conversion
   - Converts to mono PCM format optimal for VAD and speech recognition

3. Voice Activity Detection (VAD):
   - Uses Silero VAD model for robust speech detection
   - Processes audio in small chunks returning probability scores
   - Tracks speech state using configurable probability thresholds
   - Detects speech endpoints based on silence duration

4. Speech Buffering:
   - Ring buffer accumulates incoming PCM audio data
   - Speech buffer collects audio chunks during active speech
   - Automatically queues segments for transcription when speech ends

5. Speech-to-Text:
   - Uses faster-whisper for efficient CPU-based transcription
   - Runs with int8 quantization for optimal performance
   - Processes complete speech segments asynchronously
   - Returns timestamped transcription text

6. Output:
   - Prints transcribed text to stdout with timestamps
   - Logs transcription events for debugging
   - Ready for integration with WebSocket, database, or API endpoints
"""

import os
import logging
import threading
import queue
from typing import Optional, List, Tuple
import numpy as np
import torch
from av.audio.resampler import AudioResampler
from av.audio.frame import AudioFrame
from faster_whisper import WhisperModel
from silero_vad import load_silero_vad


class TranscriptionHandler:
    """Handles real-time audio transcription with VAD and Whisper."""

    def __init__(
        self,
        model_size: str = "small.en",
        start_speech_prob: float = 0.1,
        keep_speech_prob: float = 0.5,
        stop_silence_ms: int = 500,
        min_segment_ms: int = 300,
        sampling_rate: int = 16000,
        chunk_size: int = 512,
    ):
        """
        Initialize transcription handler with VAD and Whisper models.

        Args:
            model_size: Whisper model size (e.g., "small.en", "medium.en")
            start_speech_prob: Probability threshold to enter "speaking" state
            keep_speech_prob: Probability threshold to stay in "speaking" state
            stop_silence_ms: Silence duration to end speech segment
            min_segment_ms: Minimum segment duration to transcribe
            sampling_rate: Target sampling rate for transcription
            chunk_size: Size of audio chunks to feed to VAD (512 ≈ 32ms at 16kHz)
        """
        self.sampling_rate = sampling_rate
        self.chunk_size = chunk_size
        self.chunk_bytes = chunk_size * 2  # int16 = 2 bytes per sample
        self.start_speech_prob = start_speech_prob
        self.keep_speech_prob = keep_speech_prob
        self.stop_silence_samples = sampling_rate * stop_silence_ms // 1000
        self.min_segment_samples = sampling_rate * min_segment_ms // 1000

        # CPU threads for processing
        cpu_count = os.cpu_count()
        n_threads = max(4, cpu_count // 2) if cpu_count else 4

        # Initialize Silero VAD
        logging.info("Loading Silero VAD model...")
        torch.set_num_threads(n_threads)
        self.vad = load_silero_vad()

        # Initialize faster-whisper
        logging.info(f"Loading Whisper model: {model_size}")
        self.asr = WhisperModel(
            model_size_or_path=model_size,
            device="cpu",
            compute_type="int8",
            cpu_threads=n_threads,
        )

        # Audio resampler for converting to 16kHz mono
        self.resampler: Optional[AudioResampler] = None
        self.ring_buffer = bytearray()  # Accumulates raw int16 PCM
        self.speech_buffer: List[np.ndarray] = []  # List of frame chunks during speech
        self.in_speech = False  # Track if currently in speech segment
        self.silence_samples = 0  # Count of consecutive silence samples
        self.stream_time_offset = 0.0  # Track cumulative stream time in seconds
        self.speech_start_time = 0.0  # Track when current speech segment started

        # Threading for async transcription (stores tuples of (audio, start_time))
        self.transcription_queue: queue.Queue[Optional[Tuple[np.ndarray, float]]] = (
            queue.Queue()
        )
        self.stop_event = threading.Event()
        self.transcription_thread = threading.Thread(
            target=self._transcription_worker, daemon=True
        )
        self.transcription_thread.start()

        logging.info(
            "Transcription handler initialized (model=%s, start_prob=%.2f, keep_prob=%.2f, silence=%dms)",
            model_size,
            start_speech_prob,
            keep_speech_prob,
            stop_silence_ms,
        )

    def setup_resampler(
        self, input_format: str, input_layout: str, input_rate: int
    ) -> None:
        """
        Setup audio resampler based on input stream parameters.

        Args:
            input_format: Input audio format
            input_layout: Input channel layout
            input_rate: Input sample rate
        """
        self.resampler = AudioResampler(
            format="s16",
            layout="mono",
            rate=self.sampling_rate,
        )
        logging.info(
            "Audio resampler configured: %s/%s/%dHz -> s16/mono/%dHz",
            input_format,
            input_layout,
            input_rate,
            self.sampling_rate,
        )

    def process_audio_frame(self, frame: AudioFrame) -> None:
        """
        Process an audio frame for transcription.

        Args:
            frame: Audio frame from PyAV
        """
        if not self.resampler:
            # Setup resampler on first frame if not already done
            self.setup_resampler(
                str(frame.format.name), str(frame.layout.name), frame.sample_rate
            )

        # Resample to 16kHz mono
        if self.resampler:
            resampled_frames = self.resampler.resample(frame)
        else:
            return
        for resampled_frame in resampled_frames:
            mono_array = resampled_frame.to_ndarray()

            # Handle multi-dimensional arrays (channels)
            if len(mono_array.shape) > 1:
                mono_array = mono_array[0]  # Take first channel

            # Convert to int16 bytes
            if mono_array.dtype != np.int16:
                # Ensure we're in the right range for int16
                if mono_array.dtype in [np.float32, np.float64]:
                    mono_array = (mono_array * 32768).astype(np.int16)
                else:
                    mono_array = mono_array.astype(np.int16)

            self.ring_buffer.extend(mono_array.tobytes())

            # Feed chunks to VAD
            while len(self.ring_buffer) >= self.chunk_bytes:
                chunk_bytes = self.ring_buffer[: self.chunk_bytes]
                chunk = np.frombuffer(chunk_bytes, np.int16)
                self.ring_buffer = self.ring_buffer[self.chunk_bytes :]

                # Normalize to float32 [-1, 1] for VAD
                chunk_float = chunk.astype(np.float32) / 32768.0

                # Convert to torch tensor for VAD
                chunk_tensor = torch.from_numpy(chunk_float)

                # Get speech probability from VAD
                prob = self.vad(chunk_tensor, self.sampling_rate).item()

                if self.in_speech:
                    # Currently in speech - accumulate audio
                    self.speech_buffer.append(chunk)

                    if prob > self.keep_speech_prob:
                        # Still speaking, reset silence counter
                        self.silence_samples = 0
                    else:
                        # Silence detected, increment counter
                        self.silence_samples += self.chunk_size

                        # Check if enough silence to end speech segment
                        if self.silence_samples >= self.stop_silence_samples:
                            self.in_speech = False
                            logging.debug(
                                "Speech ended at %.2fs, queueing for transcription...",
                                self.stream_time_offset,
                            )
                            self._queue_speech_for_transcription()
                            self.speech_buffer.clear()
                            self.silence_samples = 0
                else:
                    # Not in speech - check if speech is starting
                    if prob > self.start_speech_prob:
                        self.in_speech = True
                        self.speech_start_time = self.stream_time_offset
                        self.speech_buffer.append(chunk)
                        self.silence_samples = 0
                        logging.debug("Speech started at %.2fs", self.speech_start_time)

                # Update stream time offset (chunk_size samples at sampling_rate Hz)
                self.stream_time_offset += self.chunk_size / self.sampling_rate

    def _queue_speech_for_transcription(self) -> None:
        """Queue the collected speech segment for async transcription."""
        if not self.speech_buffer:
            return

        # Concatenate all chunks into a single array
        audio = np.concatenate(self.speech_buffer, axis=0)

        # Check minimum segment length
        if len(audio) < self.min_segment_samples:
            logging.debug("Speech segment too short (%d samples), skipping", len(audio))
            return

        # Convert to float32 for Whisper
        audio_float = audio.astype(np.float32) / 32768.0

        # Store the start time for this speech segment
        segment_start_time = self.speech_start_time

        # Queue for async transcription with timing info (non-blocking)
        try:
            self.transcription_queue.put_nowait((audio_float, segment_start_time))
        except queue.Full:
            logging.warning("Transcription queue full, dropping audio segment")

    def _transcription_worker(self) -> None:
        """Background worker thread for processing transcriptions."""
        logging.info("Transcription worker thread started")

        while not self.stop_event.is_set():
            try:
                # Get audio from queue with timeout to check stop_event periodically
                item = self.transcription_queue.get(timeout=0.5)

                if item is None:  # Sentinel value to stop
                    break

                # Unpack audio and timing info
                audio, segment_start_time = item

                # Transcribe with Whisper
                segments, _info = self.asr.transcribe(
                    audio,
                    beam_size=5,
                    language="en",  # Force English for better accuracy with .en models
                )

                # Print transcribed segments with corrected timestamps
                for segment in segments:
                    text = segment.text.strip()
                    if text:  # Only print non-empty segments
                        # Add stream time offset to Whisper's relative timestamps
                        actual_start = segment_start_time + segment.start
                        actual_end = segment_start_time + segment.end
                        # Log at INFO level for visibility (will appear in stdout with timestamp)
                        logging.info(
                            "[Transcription] [%.2fs → %.2fs] %s",
                            actual_start,
                            actual_end,
                            text,
                        )
                        # TODO: In the future, this could be sent to a queue, WebSocket, or database

            except queue.Empty:
                continue
            except Exception as e:
                logging.error("Error in transcription worker: %s", e)

        logging.info("Transcription worker thread stopped")

    def flush(self) -> None:
        """
        Flush any remaining audio in the buffer and transcribe.
        Called when stream ends.
        """
        # Process any remaining chunks in VAD
        if len(self.ring_buffer) > 0:
            # Pad the remaining buffer to chunk size if needed
            remaining = len(self.ring_buffer)
            if remaining < self.chunk_bytes:
                self.ring_buffer.extend(bytes(self.chunk_bytes - remaining))

            # Process final chunk
            chunk_bytes = self.ring_buffer[: self.chunk_bytes]
            chunk = np.frombuffer(chunk_bytes, np.int16)
            chunk_float = chunk.astype(np.float32) / 32768.0
            chunk_tensor = torch.from_numpy(chunk_float)

            # Process with VAD and accumulate if in speech
            prob = self.vad(chunk_tensor, self.sampling_rate).item()
            if self.in_speech and prob > self.keep_speech_prob:
                self.speech_buffer.append(chunk)

        # Force transcribe any remaining speech
        if self.speech_buffer:
            self._queue_speech_for_transcription()

        # Clear buffers
        self.ring_buffer.clear()
        self.speech_buffer.clear()
        self.in_speech = False
        self.silence_samples = 0

        # Stop transcription thread gracefully
        self.stop_event.set()
        self.transcription_queue.put(None)  # Sentinel to unblock worker
        self.transcription_thread.join(timeout=5.0)

        # Process any remaining items in queue
        while not self.transcription_queue.empty():
            try:
                item = self.transcription_queue.get_nowait()
                if item is not None:
                    # Unpack audio and timing info
                    audio, segment_start_time = item
                    # Do a final synchronous transcription for remaining items
                    segments, _info = self.asr.transcribe(
                        audio,
                        beam_size=5,
                        language="en",
                    )
                    for segment in segments:
                        text = segment.text.strip()
                        if text:
                            # Add stream time offset to get actual timestamps
                            actual_start = segment_start_time + segment.start
                            actual_end = segment_start_time + segment.end
                            logging.info(
                                "[Transcription] [%.2fs → %.2fs] %s",
                                actual_start,
                                actual_end,
                                text,
                            )
            except queue.Empty:
                break

        # Reset timing for next session
        self.stream_time_offset = 0.0
        self.speech_start_time = 0.0

        logging.info("Transcription handler flushed")


# Singleton instance management
_transcription_handler: Optional[TranscriptionHandler] = None


def get_transcription_handler() -> TranscriptionHandler:
    """Get or create the singleton transcription handler instance."""
    global _transcription_handler
    if _transcription_handler is None:
        _transcription_handler = TranscriptionHandler()
    return _transcription_handler
