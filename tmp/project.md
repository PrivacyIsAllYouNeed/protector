# Real-time Video Privacy Infrastructure

This system provides privacy-preserving infrastructure mainly for smart glasses application developers. It offers a real-time video processing pipeline that anonymizes bystanders by default, allowing only those who have explicitly given consent to appear in the final video. Developers use our filtered stream instead of the raw camera feed, enabling them to focus on building their apps without worrying about privacy violations.

## Overview

The system is composed of three main components:

1. **Real-Time Privacy Filter**
2. **Control API Server**
3. **Example Project: Rewind**

## 1. Real-Time Privacy Filter

## 2. Control API Server

This FastAPI-based backend provides an HTTP API for managing data operations.

### Features

- Retrieve list of consenting individuals (name, face image)
- Revoke consent

Note: No database is used for now. All data is handled as files on disk.

### Tech Stack

- Python
- `FastAPI` — HTTP server framework

## 3. Example Project: Rewind

`./examples/rewind/` is a reference implementation and serves as both a usage example and an internal inspector UI.

### Features

- Web frontend (SPA) to:
  - List and manage consenting users
- Placeholder UI for future AI Chat feature (currently grayed out as coming soon)
