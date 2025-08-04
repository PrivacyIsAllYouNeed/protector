# Real-time Video Privacy Infrastructure

## Project Overview
This repository implements a privacy-preserving video processing system for smart glasses and similar applications. It provides real-time face anonymization with consent management, allowing developers to build applications without privacy concerns.

## Project Structure
- `./filter/` - Real-time privacy filter implementation (Python)
- `./api/` - Control API server (FastAPI)
- `./examples/rewind/` - Reference implementation and inspector UI (React/TypeScript)

## Key Components

### 1. Privacy Filter (`./filter/`)
Real-time video processing pipeline that:
- Receives RTMP streams
- Detects and blurs faces by default
- Listens for verbal consent
- Re-identifies consenting individuals
- Outputs WebRTC stream + local storage

### 2. Control API (`./api/`)
FastAPI backend for:
- Managing consent records
- Accessing recorded videos
- Data operations (no database, file-based)

### 3. Example App (`./examples/rewind/`)
Web application demonstrating:
- Real-time filtered video display
- Consent management UI
- Recording management

## Development Guidelines
- The privacy filter is the core component - changes here affect the entire system
- All face data is processed locally, no external APIs
- Consent is detected through voice commands processed by local LLM
- File-based storage for simplicity (no database setup required)