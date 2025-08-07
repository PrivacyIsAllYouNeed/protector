# Real-time Video Privacy Infrastructure

This system provides privacy-preserving infrastructure mainly for smart glasses application developers. It offers a real-time video processing pipeline that anonymizes bystanders by default, allowing only those who have explicitly given consent to appear in the final video. Developers use our filtered stream instead of the raw camera feed, enabling them to focus on building their apps without worrying about privacy violations.

## Overview

The system is composed of three main components:

1. **Real-Time Privacy Filter**
2. **Control API Server**
3. **Example Project: Rewind**

## 1. Real-Time Privacy Filter

This is the core engine that processes video streams in real-time. It receives RTMP streams, anonymizes faces by default, listens for verbal consent to be recorded, and re-identifies consenting individuals in the video feed with optional name labels.

### Features

- **Face Processing**:
  - Blur non-consenting faces.
  - Face matching using `face_recognition`.
  - Display name label next to consenting faces (if provided).
- **Verbal Consent Detection**:
  - Update face matching registry based on recognized consent.
- **Storage**:
  - Processed video is stored locally using `MediaRecorder` from `aiortc`.

## 2. Control API Server

This FastAPI-based backend provides an HTTP API for managing data operations.

### Features

- Retrieve list of consenting individuals (name, face image)
- Revoke consent
- View list of recorded videos
- Access and delete recorded videos

Note: No database is used for now. All data is handled as files on disk.

### Tech Stack

- Python
- `FastAPI` — HTTP server framework

## 3. Example Project: Rewind

`./examples/rewind/` is a reference implementation and serves as both a usage example and an internal inspector UI.

### Features

- Web frontend (SPA) to:
  - Display real-time processed video via WebRTC
  - List and manage consenting users
  - List and manage/view recordings
- Placeholder UI for future AI Chat feature (currently grayed out as coming soon)
