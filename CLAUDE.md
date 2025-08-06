# Real-time Video Privacy Infrastructure

## Project Overview

This repository implements a privacy-preserving video processing system for smart glasses and similar applications. It provides real-time face anonymization with consent management, allowing developers to build applications without privacy concerns.

Impl plan available at: `./tmp/project.md`

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
- Real-time speech transcription using Silero VAD + faster-whisper
- Outputs to RTSP with preserved audio
- MediaMTX exposes WebRTC stream for consumption
- Multi-threaded architecture with queue-based communication
- Graceful shutdown and comprehensive health monitoring

**Architecture:**
```
filter/
├── main.py              # Entry point (minimal)
├── misc/                # Core infrastructure & shared components
│   ├── pipeline.py      # Pipeline orchestrator
│   ├── config.py        # Configuration with env vars
│   ├── types.py         # Shared data types
│   ├── queues.py        # Bounded queues with backpressure
│   ├── state.py         # Connection/thread state management
│   ├── metrics.py       # Performance metrics
│   ├── logging.py       # Structured logging
│   ├── shutdown.py      # Signal handling
│   └── face_detector.py # YuNet face detection module
└── threads/             # Thread implementations
    ├── base.py          # Abstract base thread
    ├── input.py         # RTMP demuxer thread
    ├── video.py         # Face detection thread
    ├── audio.py         # Audio transcoding thread
    ├── transcription.py # VAD + Whisper thread
    ├── output.py        # RTSP muxer thread
    └── monitor.py       # Health monitoring thread
```

**Threading Model:**
- **Input Thread**: Demuxes RTMP stream into video/audio queues
- **Video Thread**: Processes frames with face detection/blurring
- **Audio Thread**: Transcodes audio to Opus for WebRTC
- **Transcription Thread**: VAD + speech-to-text processing
- **Output Thread**: Muxes processed streams to RTSP
- **Monitor Thread**: Health monitoring and metrics collection

**Configuration (Environment Variables):**
- `FILTER_IN_URL`: Input RTMP URL (default: rtmp://0.0.0.0:1935/live/stream)
- `FILTER_OUT_URL`: Output RTSP URL (default: rtsp://127.0.0.1:8554/blurred)
- `ENABLE_TRANSCRIPTION`: Enable/disable transcription (default: true)
- `CPU_THREADS`: Number of CPU threads for processing
- `LOG_LEVEL`: Logging level (INFO/DEBUG/WARNING/ERROR)

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
