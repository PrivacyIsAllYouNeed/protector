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

Real-time video processing pipeline with face anonymization and transcription:

**Features:**
- Receives RTMP input streams with video and audio
- Detects and blurs faces using YuNet neural network
- Real-time speech transcription using Silero VAD + faster-whisper
- Outputs to RTSP with preserved audio
- MediaMTX exposes WebRTC stream for consumption

**Main File Structure:**
```
filter/
├── main.py           # Main relay loop and stream orchestration
├── face_detector.py  # Face detection and blurring using YuNet
├── audio_handler.py  # Audio stream detection and remuxing
├── transcription.py  # Real-time speech-to-text
└── config.py         # Configuration constants (URLs, codecs, etc.)
```

**Transcription Pipeline:**
- Voice Activity Detection (VAD) segments speech in real-time
- Transcribes utterances after X ms silence
- Outputs timestamped text to stdout

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
