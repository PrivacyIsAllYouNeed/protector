# Backend

## Privacy Filter

Real-time video stream processing with face anonymization and consent management.

### Setup

Download required models:

```bash
# Face detection model
wget -P ./filter https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx

# Face recognition model
wget -P ./filter https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx

# LLM for consent detection
hf download lmstudio-community/Phi-3.1-mini-4k-instruct-GGUF Phi-3.1-mini-4k-instruct-Q4_K_M.gguf --local-dir ./filter
```

### Run

1. Start MediaMTX server:
   ```bash
   mediamtx
   ```

2. Start the privacy filter:
   ```bash
   uv run filter/main.py
   ```

3. Stream a test source:
   ```bash
   # Test pattern
   ffmpeg -re -f lavfi -i testsrc=size=1280x720:rate=30 -c:v libx264 -preset ultrafast -tune zerolatency -loglevel warning -f flv rtmp://127.0.0.1:1935/live/stream

   # Or use your video file (loops continuously)
   ffmpeg -re -stream_loop -1 -i yourvideo.flv -vf "scale=1280:720,fps=30" -c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p -profile:v baseline -c:a aac -ar 44100 -b:a 128k -f flv rtmp://127.0.0.1:1935/live/stream
   ```

4. View the filtered output:
   ```bash
   ffplay -loglevel error rtsp://127.0.0.1:8554/filtered
   ```

## Control API

REST API for consent management and system control.

### Run

```bash
uv run fastapi dev api/main.py
```

API will be available at http://localhost:8000
