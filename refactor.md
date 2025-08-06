# Filter Service Refactoring Plan

## Executive Summary

This document outlines a comprehensive refactoring plan for the `./filter` service to transform it from a single-threaded, blocking architecture to a high-performance, multi-threaded pipeline with proper separation of concerns. The refactoring will improve performance, reliability, and maintainability while ensuring clean shutdown behavior and real-time processing capabilities.

## Current Architecture Problems

### Performance Issues
1. **Single-threaded processing**: All video/audio processing happens sequentially on main thread
2. **Blocking I/O**: Even though RTMP/RTSP are local, PyAV's demux/mux operations block the entire pipeline - if the RTMP publisher pauses or RTSP consumer slows down, everything stops

### Architectural Issues
1. **Monolithic design**: main.py handles everything (mixed concerns)
2. **Poor separation**: Audio handler mixes transcoding with transcription concerns
3. **Global singletons**: Not thread-safe, prevent proper cleanup
4. **No error recovery**: Connection failures restart entire pipeline

### Operational Issues
1. **Poor signal handling**: Ctrl-C doesn't cleanly interrupt blocking operations
2. **Memory leaks**: Unbounded buffers in transcription, no cleanup of singletons
3. **No monitoring**: Can't track performance metrics or bottlenecks

## Target Architecture

### Core Design Principles
1. **Thread-per-concern**: Separate threads for input, video processing, audio processing, output muxing
2. **Queue-based communication**: Bounded queues between pipeline stages
3. **Non-blocking I/O**: Async operations where possible, timeouts on blocking calls
4. **Clean abstractions**: Clear separation of responsibilities
5. **Graceful shutdown**: Proper signal handling and cleanup

### Threading Model

```
┌─────────────┐
│ Main Thread │ (Orchestrator + Signal Handler)
└──────┬──────┘
       │
       ├─── Health Monitor Thread
       │      └── Monitors all threads below
       │
       ├─── Input Thread (RTMP Demuxer)
       │      ├── Video Queue → Video Processing Thread
       │      ├── Audio Queue → Audio Processing Thread
       │      └── Transcription Queue → Transcription Thread
       │
       ├─── Video Processing Thread
       │      └── Face Detection Pipeline
       │
       ├─── Audio Processing Thread
       │      └── Transcoding Pipeline (to Opus)
       │
       ├─── Transcription Thread
       │      └── VAD + Whisper Pipeline
       │
       └─── Output Muxer Thread (RTSP)
              ├── Reads from Processed Video Queue
              └── Reads from Processed Audio Queue
```


**Notes**:
- Initially implementing with single video processing thread. Can be upgraded to thread pool in future based on performance analysis.
- Make sure to maintain A/V sync
- Clean Shutdown: Ensure all threads stop gracefully on Ctrl-C

## New File Structure (Example)

```
filter/
├── misc/
│   ├── __init__.py
│   ├── pipeline.py      # Main Pipeline orchestrator class
│   ├── config.py        # All configuration
│   ├── state.py         # Connection state management
│   ├── types.py         # Shared types
│   ├── queues.py        # Bounded queue (with backpressure strategies)
│   ├── metrics.py       # Performance monitoring
│   ├── logging.py       # Structured logging
│   ├── shutdown.py      # Signal handling and graceful shutdown
│   └── etc.
│
├── threads/
│   ├── __init__.py
│   ├── monitor.py       # Health Monitor Thread
│   ├── input.py         # Input Thread (RTMP demuxer)
│   ├── video.py         # Video Processing Thread (face detection)
│   ├── audio.py         # Audio Processing Thread (Opus transcoding)
│   ├── transcription.py # Transcription Thread (VAD + Whisper)
│   └── output.py        # Output Muxer Thread (RTSP writer)
│
└── main.py              # Entry point (minimal, just launches pipeline)
```

## Notes

- This product is not deployed to production, so no worry about migration/backward-compatibility.
