#!/usr/bin/env python3
"""
Simple test script for Whisper transcription without VAD.
Directly transcribes the entire audio file.
"""

import sys
import wave
import logging
import numpy as np
from faster_whisper import WhisperModel

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def transcribe_simple(audio_file: str, model_size: str = "small.en"):
    """
    Simple transcription of an audio file using only Whisper (no VAD).

    Args:
        audio_file: Path to audio file (WAV format recommended)
        model_size: Whisper model size (e.g., "small.en", "medium.en", "large-v2")
    """

    # Initialize faster-whisper
    logging.info(f"Loading Whisper model: {model_size}")
    model = WhisperModel(
        model_size_or_path=model_size,
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
    )

    # Read audio file
    logging.info(f"Reading audio file: {audio_file}")
    try:
        with wave.open(audio_file, "rb") as wav:
            # Get audio info
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            n_frames = wav.getnframes()
            duration = n_frames / sample_rate

            logging.info(
                f"Audio info: {channels} channel(s), {sample_rate}Hz, {duration:.2f} seconds"
            )

            # Read all audio data
            frames = wav.readframes(n_frames)
            audio_data = np.frombuffer(frames, dtype=np.int16)

            # Convert to mono if stereo
            if channels > 1:
                logging.info("Converting stereo to mono...")
                audio_data = audio_data.reshape(-1, channels)
                audio_data = audio_data.mean(axis=1).astype(np.int16)

            # Convert to float32 normalized [-1, 1]
            audio_float = audio_data.astype(np.float32) / 32768.0

    except Exception as e:
        logging.error(f"Failed to read audio file: {e}")
        return

    # Transcribe the entire audio
    logging.info("Transcribing audio...")
    logging.info("-" * 50)

    try:
        # Transcribe with various settings
        segments, info = model.transcribe(
            audio_float,
            beam_size=5,
            language="en",  # Force English, or set to None for auto-detect
            vad_filter=True,  # Enable Whisper's built-in VAD
            vad_parameters=dict(
                threshold=0.6,
                min_silence_duration_ms=2500,
                speech_pad_ms=400,
            ),
        )

        # Print language info
        logging.info(
            f"Detected language: {info.language} (probability: {info.language_probability:.2%})"
        )
        logging.info("-" * 50)

        # Print all segments
        all_text = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                print(f"[{segment.start:.2f}s → {segment.end:.2f}s] {text}")
                all_text.append(text)

        # Print full transcript
        logging.info("-" * 50)
        logging.info("Full transcript:")
        print("\n".join(all_text))

    except Exception as e:
        logging.error(f"Transcription failed: {e}")
        return

    logging.info("-" * 50)
    logging.info("Transcription complete")


def transcribe_simple_no_vad(audio_file: str, model_size: str = "small.en"):
    """
    Even simpler transcription without any VAD at all.

    Args:
        audio_file: Path to audio file (WAV format recommended)
        model_size: Whisper model size
    """

    # Initialize faster-whisper
    logging.info(f"Loading Whisper model: {model_size}")
    model = WhisperModel(
        model_size_or_path=model_size,
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
    )

    # Read audio file
    logging.info(f"Reading audio file: {audio_file}")
    try:
        with wave.open(audio_file, "rb") as wav:
            _sample_rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
            audio_data = np.frombuffer(frames, dtype=np.int16)

            # Convert to float32
            audio_float = audio_data.astype(np.float32) / 32768.0

    except Exception as e:
        logging.error(f"Failed to read audio file: {e}")
        return

    # Transcribe without any VAD
    logging.info("Transcribing audio (no VAD)...")
    segments, info = model.transcribe(
        audio_float,
        beam_size=5,
        language=None,  # Auto-detect language
        vad_filter=False,  # Disable VAD completely
    )

    logging.info(f"Detected language: {info.language}")
    logging.info("-" * 50)

    for segment in segments:
        text = segment.text.strip()
        if text:
            print(f"[{segment.start:.2f}s → {segment.end:.2f}s] {text}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python test_whisper_simple.py <audio_file.wav> [model_size] [--no-vad]"
        )
        print("Examples:")
        print("  python test_whisper_simple.py test_audio.wav")
        print("  python test_whisper_simple.py test_audio.wav medium.en")
        print("  python test_whisper_simple.py test_audio.wav small.en --no-vad")
        sys.exit(1)

    audio_file = sys.argv[1]
    model_size = "small.en"
    use_vad = True

    # Parse arguments
    if len(sys.argv) > 2:
        if sys.argv[2] != "--no-vad":
            model_size = sys.argv[2]
        else:
            use_vad = False

    if len(sys.argv) > 3 and sys.argv[3] == "--no-vad":
        use_vad = False

    if use_vad:
        transcribe_simple(audio_file, model_size)
    else:
        transcribe_simple_no_vad(audio_file, model_size)
