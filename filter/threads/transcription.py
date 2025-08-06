import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import queue
import numpy as np
import torch
from typing import Optional, List
from av.audio.resampler import AudioResampler
from av.audio.frame import AudioFrame
from faster_whisper import WhisperModel
from silero_vad import load_silero_vad
from threads.base import BaseThread
from misc.state import ThreadStateManager
from misc.types import AudioData, TranscriptionData
from misc.queues import BoundedQueue
from misc.config import QUEUE_TIMEOUT, CPU_THREADS, WHISPER_MODEL


class TranscriptionThread(BaseThread):
    def __init__(
        self,
        state_manager: ThreadStateManager,
        input_queue: BoundedQueue[AudioData],
        start_speech_prob: float = 0.1,
        keep_speech_prob: float = 0.5,
        stop_silence_ms: int = 500,
        min_segment_ms: int = 300,
        sampling_rate: int = 16000,
        chunk_size: int = 512,
    ):
        super().__init__(
            name="Transcription", state_manager=state_manager, heartbeat_interval=2.0
        )
        self.input_queue = input_queue
        self.sampling_rate = sampling_rate
        self.chunk_size = chunk_size
        self.chunk_bytes = chunk_size * 2
        self.start_speech_prob = start_speech_prob
        self.keep_speech_prob = keep_speech_prob
        self.stop_silence_samples = sampling_rate * stop_silence_ms // 1000
        self.min_segment_samples = sampling_rate * min_segment_ms // 1000

        self.vad: Optional[torch.nn.Module] = None
        self.asr: Optional[WhisperModel] = None
        self.resampler: Optional[AudioResampler] = None

        self.ring_buffer = bytearray()
        self.speech_buffer: List[np.ndarray] = []
        self.in_speech = False
        self.silence_samples = 0
        self.stream_time_offset = 0.0
        self.speech_start_time = 0.0

        # Bounded queue to prevent memory growth
        self.transcription_queue: queue.Queue[Optional[TranscriptionData]] = (
            queue.Queue(maxsize=10)
        )
        self.transcriptions_completed = 0

    def setup(self):
        self.logger.info("Loading Silero VAD model...")
        torch.set_num_threads(CPU_THREADS)
        vad_model = load_silero_vad()
        if isinstance(vad_model, torch.nn.Module):
            self.vad = vad_model

        self.logger.info(f"Loading Whisper model: {WHISPER_MODEL}")
        self.asr = WhisperModel(
            model_size_or_path=WHISPER_MODEL,
            device="cpu",
            compute_type="int8",
            cpu_threads=CPU_THREADS,
        )

        self.logger.info(
            f"Transcription initialized (model={WHISPER_MODEL}, "
            f"start_prob={self.start_speech_prob:.2f}, "
            f"keep_prob={self.keep_speech_prob:.2f}, "
            f"silence={self.stop_silence_samples}ms)"
        )

    def process_iteration(self) -> bool:
        if self._process_transcription_queue():
            return True

        audio_data = self.input_queue.get(timeout=QUEUE_TIMEOUT)

        if audio_data is None:
            return False

        try:
            self._process_audio_frame(audio_data.frame)
            return True
        except Exception as e:
            self.logger.error(f"Error processing audio frame: {e}")
            return False

    def _setup_resampler_if_needed(self, frame: AudioFrame):
        if self.resampler is not None:
            return

        self.resampler = AudioResampler(
            format="s16", layout="mono", rate=self.sampling_rate
        )

        self.logger.info(
            f"Resampler configured: {frame.format.name}/{frame.layout.name}/{frame.sample_rate}Hz -> "
            f"s16/mono/{self.sampling_rate}Hz"
        )

    def _process_audio_frame(self, frame: AudioFrame):
        self._setup_resampler_if_needed(frame)

        if not self.resampler:
            return

        resampled_frames = self.resampler.resample(frame)

        for resampled_frame in resampled_frames:
            mono_array = resampled_frame.to_ndarray()

            if len(mono_array.shape) > 1:
                mono_array = mono_array[0]

            if mono_array.dtype != np.int16:
                if mono_array.dtype in [np.float32, np.float64]:
                    mono_array = (mono_array * 32768).astype(np.int16)
                else:
                    mono_array = mono_array.astype(np.int16)

            self.ring_buffer.extend(mono_array.tobytes())

            while len(self.ring_buffer) >= self.chunk_bytes:
                chunk_bytes = self.ring_buffer[: self.chunk_bytes]
                chunk = np.frombuffer(chunk_bytes, np.int16)
                self.ring_buffer = self.ring_buffer[self.chunk_bytes :]

                self._process_vad_chunk(chunk)

    def _process_vad_chunk(self, chunk: np.ndarray):
        if not self.vad:
            return

        chunk_float = chunk.astype(np.float32) / 32768.0
        chunk_tensor = torch.from_numpy(chunk_float)

        prob = self.vad(chunk_tensor, self.sampling_rate).item()

        if self.in_speech:
            self.speech_buffer.append(chunk)

            if prob > self.keep_speech_prob:
                self.silence_samples = 0
            else:
                self.silence_samples += self.chunk_size

                if self.silence_samples >= self.stop_silence_samples:
                    self.in_speech = False
                    self.logger.debug(
                        f"Speech ended at {self.stream_time_offset:.2f}s, queueing for transcription..."
                    )
                    self._queue_speech_for_transcription()
                    self.speech_buffer.clear()
                    self.silence_samples = 0
        else:
            if prob > self.start_speech_prob:
                self.in_speech = True
                self.speech_start_time = self.stream_time_offset
                self.speech_buffer.append(chunk)
                self.silence_samples = 0
                self.logger.debug(f"Speech started at {self.speech_start_time:.2f}s")

        self.stream_time_offset += self.chunk_size / self.sampling_rate

    def _queue_speech_for_transcription(self):
        if not self.speech_buffer:
            return

        audio = np.concatenate(self.speech_buffer, axis=0)

        if len(audio) < self.min_segment_samples:
            self.logger.debug(
                f"Speech segment too short ({len(audio)} samples), skipping"
            )
            return

        audio_float = audio.astype(np.float32) / 32768.0

        transcription_data = TranscriptionData(
            audio=audio_float,
            start_time=self.speech_start_time,
            end_time=self.stream_time_offset,
        )

        try:
            self.transcription_queue.put_nowait(transcription_data)
        except queue.Full:
            self.logger.warning("Transcription queue full, dropping audio segment")

    def _process_transcription_queue(self) -> bool:
        if not self.asr:
            return False

        try:
            transcription_data = self.transcription_queue.get_nowait()

            if transcription_data is None:
                return False

            segments, _info = self.asr.transcribe(
                transcription_data.audio, beam_size=5, language="en"
            )

            for segment in segments:
                text = segment.text.strip()
                if text:
                    actual_start = transcription_data.start_time + segment.start
                    actual_end = transcription_data.start_time + segment.end
                    self.logger.info(
                        f"[Transcription] [{actual_start:.2f}s → {actual_end:.2f}s] {text}"
                    )

            self.transcriptions_completed += 1
            self.metrics.record_transcription()

            return True

        except queue.Empty:
            return False
        except Exception as e:
            self.logger.error(f"Error transcribing: {e}")
            return False

    def cleanup(self):
        if self.speech_buffer:
            self._queue_speech_for_transcription()

        while not self.transcription_queue.empty():
            try:
                self._process_transcription_queue()
            except Exception:
                break

        self.logger.info(
            f"Transcription cleanup - completed {self.transcriptions_completed} transcriptions"
        )

        self.ring_buffer.clear()
        self.speech_buffer.clear()
        self.vad = None
        self.asr = None
        self.resampler = None
