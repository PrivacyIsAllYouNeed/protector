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
- Face recognition for consented users using SFace neural network
- Real-time speech transcription using separated VAD and Whisper threads for non-blocking processing
- Automatic consent detection from transcribed speech using local LLM
- Consent-triggered head image capture and face feature extraction
- File-based consent management with real-time monitoring using watchfiles
- Automatic loading of existing consent files on startup
- Dynamic consent addition/revocation through file system changes
- Selective face blurring - consented faces remain unblurred with name labels
- Outputs to RTSP with preserved audio
- MediaMTX exposes WebRTC stream for consumption and records video
- Multi-threaded architecture with queue-based communication
- Graceful shutdown and comprehensive health monitoring

**Architecture:**
```
filter/
├─ main.py                  # Entry point
├─ misc/
│  ├─ pipeline.py           # Pipeline orchestrator
│  ├─ config.py             # Configuration with env vars
│  ├─ types.py              # Shared data types
│  ├─ queues.py             # Bounded queues with backpressure
│  ├─ state.py              # Connection/thread state management
│  ├─ metrics.py            # Performance metrics
│  ├─ logging.py            # Structured logging
│  ├─ shutdown.py           # Signal handling
│  ├─ face_detector.py      # Face detection module
│  ├─ face_recognizer.py    # Face recognition module
│  ├─ consent_detector.py   # LLM-based consent detection
│  ├─ consent_capture.py    # Head image capture utility for consent
│  ├─ consent_manager.py    # File-based consent management with monitoring
│  └─ consent_file_utils.py # Consent file naming and parsing utilities
└─ threads/
    ├─ base.py              # Abstract base thread
    ├─ input.py             # RTMP demuxer thread
    ├─ video.py             # Face detection/recognition thread
    ├─ audio.py             # Audio transcoding thread
    ├─ vad.py               # Real-time VAD processing thread
    ├─ speech_worker.py     # Background Whisper transcription thread
    ├─ output.py            # RTSP muxer thread
    └─ monitor.py           # Health monitoring thread
```

**Threading Model:**
- **Input Thread**: Demuxes RTMP stream into video/audio queues
- **Video Thread**: Processes frames with face detection/recognition, selective blurring, and consent captures
- **Audio Thread**: Transcodes audio to Opus for WebRTC
- **VAD Thread**: Real-time Voice Activity Detection (non-blocking)
- **Speech Worker Thread(s)**: Background Whisper transcription and consent detection
- **Output Thread**: Muxes processed streams to RTSP
- **Monitor Thread**: Health monitoring and metrics collection
- **Consent Monitor Thread**: Watches consent_captures/ directory for real-time file changes (runs via watchfiles)

**Transcription & Consent Detection:**
The transcription system uses a non-blocking architecture to prevent real-time degradation:
- VAD Thread continuously processes audio in real-time, detecting speech boundaries
- When speech ends, complete segments are queued for transcription
- Speech Worker Thread(s) consume segments and run Whisper inference in the background
- Transcribed text is analyzed by a local LLM to detect explicit consent phrases
- Consent detection identifies both the consent status and speaker's name when available
- This separation ensures VAD never waits for transcription, maintaining real-time performance

**Face Recognition & Consent Management:**
- When consent is detected via speech, the system captures a head image of the largest face (assumed to be the speaker)
- Head images are saved to `./consent_captures/` with format `YYYYMMDDHHMMSS_[name].jpg`
- On startup, all existing consent files are loaded and face features extracted
- File system monitoring via watchfiles detects real-time consent changes:
  - Adding a file grants consent for that person
  - Deleting a file revokes consent for that person
- Face features are extracted using SFace model and stored in an in-memory database
- Multiple captures per person are supported for improved recognition accuracy
- In subsequent frames, all detected faces are matched against the consented faces database
- Recognized consented faces remain unblurred with green name labels displayed above them
- Unrecognized faces continue to be blurred for privacy protection

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

- You can run Python like: `uv run python foo.py`
