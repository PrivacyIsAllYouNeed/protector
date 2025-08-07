# Real-time Video Privacy Infrastructure

## Project Overview

This repository implements a privacy-preserving video processing system for smart glasses and similar applications. It provides real-time face anonymization with consent management, allowing developers to build applications without privacy concerns.

## Project Structure

- `./filter/` - Real-time privacy filter implementation (Python)
- `./api/` - Control API server (FastAPI)
- `./examples/rewind/` - Reference implementation and inspector UI (React/TypeScript)

## Key Components

### 1. Privacy Filter (`./filter/`)

High-performance multi-threaded video processing pipeline with face anonymization and transcription:

**Features:**
- Receives RTMP input streams with video and audio
- Detects and blurs faces using YuNet neural network
- Real-time speech transcription using separated VAD and Whisper threads for non-blocking processing
- Automatic consent detection from transcribed speech using local LLM
- Outputs to RTSP with preserved audio
- MediaMTX exposes WebRTC stream for consumption
- Multi-threaded architecture with queue-based communication
- Graceful shutdown and comprehensive health monitoring

**Architecture:**
```
filter/
├── main.py                 # Entry point (minimal)
├── misc/                   # Core infrastructure & shared components
│   ├── pipeline.py         # Pipeline orchestrator
│   ├── config.py           # Configuration with env vars
│   ├── types.py            # Shared data types
│   ├── queues.py           # Bounded queues with backpressure
│   ├── state.py            # Connection/thread state management
│   ├── metrics.py          # Performance metrics
│   ├── logging.py          # Structured logging
│   ├── shutdown.py         # Signal handling
│   ├── face_detector.py    # YuNet face detection module
│   └── consent_detector.py # LLM-based consent detection
└── threads/                # Thread implementations
    ├── base.py             # Abstract base thread
    ├── input.py            # RTMP demuxer thread
    ├── video.py            # Face detection thread
    ├── audio.py            # Audio transcoding thread
    ├── vad.py              # Real-time VAD processing thread
    ├── speech_worker.py    # Background Whisper transcription thread
    ├── output.py           # RTSP muxer thread
    └── monitor.py          # Health monitoring thread
```

**Threading Model:**
- **Input Thread**: Demuxes RTMP stream into video/audio queues
- **Video Thread**: Processes frames with face detection/blurring
- **Audio Thread**: Transcodes audio to Opus for WebRTC
- **VAD Thread**: Real-time Voice Activity Detection (non-blocking)
- **Speech Worker Thread(s)**: Background Whisper transcription (can block)
- **Output Thread**: Muxes processed streams to RTSP
- **Monitor Thread**: Health monitoring and metrics collection

**Transcription & Consent Detection:**
The transcription system uses a non-blocking architecture to prevent real-time degradation:
- VAD Thread continuously processes audio in real-time, detecting speech boundaries
- When speech ends, complete segments are queued for transcription
- Speech Worker Thread(s) consume segments and run Whisper inference in the background
- Transcribed text is analyzed by a local LLM to detect explicit consent phrases
- Consent detection identifies both the consent status and speaker's name when available
- This separation ensures VAD never waits for transcription, maintaining real-time performance

Run these commands before committing changes:

```bash
# Run tests (currently no tests, skip this)
# uv run pytest

# Type checking
uv run basedpyright

# Linting & Formatting
uv run ruff check --fix && uv run ruff format
```

### 2. Control API (`./api/`)

TODO

### 3. Example App (`./examples/rewind/`)

React/TypeScript application showcasing the privacy infrastructure:

- Real-time WHEP video streaming display
- Connection status monitoring
- Privacy-first UI with consent management panels
- Recording management interface (planned)
- AI chat integration (planned)

Run these commands before committing changes:

```bash
# Build the application
npm run build

# Run linting
npm run lint
```

## Tips

- You can use `uv run foo.py` to run a Python script
